"""Deterministic V7-Lite readiness gate for G0-G6 promotion evidence.

Replaces hand-typed ``v7_lite_readiness_percent`` values in
``reports/accp/v7_lite_checkpoint_*.yaml`` with a score computed from
per-gate evidence against the LOCKED_INITIAL_BASELINE thresholds in
``v7/docs/pipeline/evaluation.md``.

``gate_completion_pct`` means exactly one thing: "would
:func:`v7.lite.candidate_gate.evaluate_frozen_candidate` accept a manifest
whose ``gate_statuses`` reflect these G0-G6 results." It does not evaluate
G7-G10 (shadow/paper/tiny-live/live), which require live observation and
cannot be computed from static evidence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

REQUIRED_GATES: tuple[str, ...] = ("G0", "G1", "G2", "G3", "G4", "G5", "G6")
FORMULA_VERSION = "readiness-gate-1.0"

# Canonical scope = the v0.30B "Binance UM Data Lake Bootstrap" real-data
# baseline (v7/docs/roadmap.md, LOCKED 2026-07-02): exactly these 5 symbols,
# real (non-synthetic) Binance data, 2022-present.
#
# NOTE: alphaforge.data.scalp_manifest.SCALP_SYMBOLS /
# aggressive_manifest.AGGRESSIVE_SCALP_SYMBOLS list a 20-symbol *target*
# universe, but roadmap.md's "20-symbol expansion gate" explicitly keeps that
# HOLD/DEFERRED until the 5-symbol P0 baseline is stable. Gating readiness on
# 20 symbols before that expansion gate opens would score against a universe
# the project has not yet unlocked. Canonical scope here therefore tracks the
# 5-symbol LOCKED baseline, not the eventual 20-symbol target.
CANONICAL_SYMBOLS: frozenset[str] = frozenset(
    {"BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"}
)
CANONICAL_SYMBOL_COUNT = len(CANONICAL_SYMBOLS)

# There is no single fixed "full feature count" in this codebase — the
# `--features all` flag on alphaforge.train enables 9 feature groups
# (returns, volatility, atr, momentum, volume, breakout, orderbook, regime,
# candle_pattern) whose combined column count has varied across runs (39,
# 54, 61 all observed in reports/training_scalp_*.json as of 2026-07-13,
# depending on which feature-group set and normalization were active).
# DataScope therefore does NOT gate on a fixed feature count — only on
# exact symbol-set membership and the caller's own attestation that
# `--features all` was used (see DataScope.uses_all_feature_groups).
CANONICAL_FEATURE_COUNT = None

_MODES = ("SWING", "SCALP", "AGGRESSIVE_SCALP")

# Transcribed once from the Mode-Specific Promotion Thresholds table in
# v7/docs/pipeline/evaluation.md. A pinned-value test cross-checks a subset
# of these against the doc so the two cannot silently diverge.
MODE_THRESHOLDS: dict[str, dict[str, float | int]] = {
    "SWING": {
        "min_oos_months": 12,
        "min_folds": 6,
        "min_trades": 200,
        "min_expectancy_r": 0.15,
        "max_drawdown_pct": 25.0,
        "min_correct_no_trade_pct": 60.0,
        "min_saved_loss_r": 0.20,
        "max_calibration_error_pct": 10.0,
        "cost_stress_multiplier": 1.5,
        "min_cost_adjusted_expectancy_r": 0.0,  # no explicit floor beyond survival for SWING
        "max_symbol_contribution_pct": 40.0,
        "max_cluster_contribution_pct": 60.0,
    },
    "SCALP": {
        "min_oos_months": 12,
        "min_folds": 6,
        "min_trades": 500,
        "min_expectancy_r": 0.05,
        "max_drawdown_pct": 15.0,
        "min_correct_no_trade_pct": 55.0,
        "min_saved_loss_r": 0.10,
        "max_calibration_error_pct": 10.0,
        "cost_stress_multiplier": 2.0,
        "min_cost_adjusted_expectancy_r": 0.10,
        "max_symbol_contribution_pct": 40.0,
        "max_cluster_contribution_pct": 60.0,
    },
    "AGGRESSIVE_SCALP": {
        "min_oos_months": 6,
        "min_folds": 6,
        "min_trades": 300,
        "min_expectancy_r": 0.03,
        "max_drawdown_pct": 10.0,
        "min_correct_no_trade_pct": 50.0,
        "min_saved_loss_r": 0.05,
        "max_calibration_error_pct": 15.0,
        "cost_stress_multiplier": 2.5,
        "min_cost_adjusted_expectancy_r": 0.0,
        "max_symbol_contribution_pct": 40.0,
        "max_cluster_contribution_pct": 60.0,
    },
}


class ReadinessGateError(ValueError):
    """Raised for invalid scope, mode, or evidence input."""


@dataclass(frozen=True)
class DataScope:
    """The dataset a readiness score was computed against.

    ``compute_readiness`` refuses non-canonical scope unless the caller
    explicitly opts out with a reason — this is what stops a synthetic or
    partial-feature run from ever producing a number that looks like a real
    promotion-readiness score.
    """

    symbols: frozenset[str]
    feature_count: int
    start_ts: int
    end_ts: int
    uses_all_feature_groups: bool = False

    def is_canonical(self) -> bool:
        return self.symbols == CANONICAL_SYMBOLS and self.uses_all_feature_groups


@dataclass(frozen=True)
class GateEvidence:
    """Raw evidence for one gate. Unused fields for a given gate are ignored."""

    oos_months: float = 0.0
    folds: int | float = 0
    trades: int | float = 0
    expectancy_r: float = 0.0
    max_drawdown_pct: float = 100.0
    correct_no_trade_pct: float = 0.0
    saved_loss_r: float = 0.0
    calibration_error_pct: float = 100.0
    cost_stress_multiplier_survived: float = 0.0
    cost_adjusted_expectancy_r: float = 0.0
    max_symbol_contribution_pct: float = 100.0
    max_cluster_contribution_pct: float = 100.0
    catastrophic_regime_loss: bool = True
    mht_computed_real: bool = False
    pbo_risk: str = "HIGH"
    deflated_sharpe: float = -1.0
    regression_sign_correct_pct: float = 0.0


@dataclass(frozen=True)
class GateResult:
    gate_id: str
    passed: bool
    reasons: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ReadinessScore:
    mode: str
    scope: DataScope
    gate_completion_pct: float
    quality_subscore_pct: float
    per_gate: Mapping[str, GateResult]
    formula_version: str = FORMULA_VERSION


def _require_mode(mode: str) -> str:
    mode_u = mode.upper()
    if mode_u not in _MODES:
        raise ReadinessGateError(f"Unsupported mode: {mode!r}. Must be one of {_MODES}.")
    return mode_u


def evaluate_gate(gate_id: str, evidence: GateEvidence, mode: str) -> GateResult:
    """Evaluate one G0-G6 gate's exit criteria deterministically.

    Thresholds come from MODE_THRESHOLDS (transcribed from
    v7/docs/pipeline/evaluation.md). No partial credit: a gate either meets
    every listed exit criterion or it fails with the specific reasons.
    """
    mode_u = _require_mode(mode)
    if gate_id not in REQUIRED_GATES:
        raise ReadinessGateError(f"Unknown gate: {gate_id!r}. Must be one of {REQUIRED_GATES}.")
    t = MODE_THRESHOLDS[mode_u]
    reasons: list[str] = []

    if gate_id == "G0":
        # DOC_READY has no numeric evidence — evidence.folds >= 1 is used as
        # a proxy "docs+contracts+labels+model outputs exist" signal from the
        # caller; callers must not fabricate this.
        if evidence.folds < 1:
            reasons.append("no_evidence_supplied")

    elif gate_id == "G1":
        if evidence.expectancy_r <= 0:
            reasons.append("non_positive_expectancy_r")
        if evidence.correct_no_trade_pct < t["min_correct_no_trade_pct"]:
            reasons.append("no_trade_quality_below_threshold")
        if evidence.pbo_risk not in ("LOW", "MEDIUM"):
            reasons.append("pbo_risk_not_low_or_medium")
        if evidence.deflated_sharpe <= 0:
            reasons.append("deflated_sharpe_not_positive")
        if not evidence.mht_computed_real:
            reasons.append("mht_fallback_identity_not_real_computation")

    elif gate_id == "G2":
        if evidence.folds < t["min_folds"]:
            reasons.append("insufficient_folds")
        if evidence.oos_months < t["min_oos_months"]:
            reasons.append("insufficient_oos_window")
        if evidence.expectancy_r <= 0:
            reasons.append("median_fold_expectancy_not_positive")

    elif gate_id == "G3":
        if evidence.cost_stress_multiplier_survived < t["cost_stress_multiplier"]:
            reasons.append("edge_does_not_survive_cost_stress")
        if evidence.cost_adjusted_expectancy_r < t["min_cost_adjusted_expectancy_r"]:
            reasons.append("cost_adjusted_expectancy_below_threshold")

    elif gate_id == "G4":
        if evidence.catastrophic_regime_loss:
            reasons.append("catastrophic_loss_in_a_regime")

    elif gate_id == "G5":
        if evidence.trades < t["min_trades"]:
            reasons.append("insufficient_trades")
        if evidence.max_symbol_contribution_pct > t["max_symbol_contribution_pct"]:
            reasons.append("single_symbol_dominates_edge")
        if evidence.max_cluster_contribution_pct > t["max_cluster_contribution_pct"]:
            reasons.append("single_cluster_dominates_edge")

    elif gate_id == "G6":
        if evidence.calibration_error_pct > t["max_calibration_error_pct"]:
            reasons.append("calibration_reliability_error_too_high")
        if evidence.max_drawdown_pct > t["max_drawdown_pct"]:
            reasons.append("max_drawdown_exceeds_limit")
        if evidence.saved_loss_r < t["min_saved_loss_r"]:
            reasons.append("saved_loss_below_threshold")

    return GateResult(gate_id=gate_id, passed=not reasons, reasons=tuple(reasons))


def _quality_ratio(numerator: float, threshold: float, higher_is_better: bool = True) -> float:
    if threshold <= 0:
        return 1.0
    ratio = numerator / threshold if higher_is_better else threshold / max(numerator, 1e-9)
    return max(0.0, min(ratio, 1.0))


def _gate_quality(gate_id: str, evidence: GateEvidence, mode: str) -> float:
    """Advisory-only distance-to-threshold for a single not-yet-passed gate."""
    t = MODE_THRESHOLDS[_require_mode(mode)]
    if gate_id == "G1":
        return _quality_ratio(evidence.correct_no_trade_pct, t["min_correct_no_trade_pct"])
    if gate_id == "G2":
        return _quality_ratio(evidence.folds, t["min_folds"])
    if gate_id == "G3":
        return _quality_ratio(evidence.cost_adjusted_expectancy_r, t["min_cost_adjusted_expectancy_r"] or 0.01)
    if gate_id == "G4":
        return 0.0 if evidence.catastrophic_regime_loss else 1.0
    if gate_id == "G5":
        return _quality_ratio(evidence.trades, t["min_trades"])
    if gate_id == "G6":
        calibration_ratio = _quality_ratio(
            evidence.calibration_error_pct, t["max_calibration_error_pct"], higher_is_better=False
        )
        drawdown_ratio = _quality_ratio(
            evidence.max_drawdown_pct, t["max_drawdown_pct"], higher_is_better=False
        )
        saved_loss_ratio = _quality_ratio(evidence.saved_loss_r, t["min_saved_loss_r"])
        return (calibration_ratio + drawdown_ratio + saved_loss_ratio) / 3.0
    return 0.0


def compute_readiness(
    mode: str,
    gate_evidences: Mapping[str, GateEvidence],
    scope: DataScope,
    *,
    allow_partial_scope: bool = False,
    partial_scope_reason: str | None = None,
) -> ReadinessScore:
    """Compute the deterministic V7-Lite readiness score for one mode.

    ``gate_completion_pct`` is the authoritative, binary score: 100 * (number
    of G0-G6 gates that PASS) / 7. ``quality_subscore_pct`` is advisory only
    and must never be used to claim a gate has passed.
    """
    mode_u = _require_mode(mode)
    if not scope.is_canonical() and not allow_partial_scope:
        raise ReadinessGateError(
            f"DataScope is not canonical (need exactly {sorted(CANONICAL_SYMBOLS)} "
            f"with uses_all_feature_groups=True; got {sorted(scope.symbols)}, "
            f"uses_all_feature_groups={scope.uses_all_feature_groups}, "
            f"feature_count={scope.feature_count}). Pass allow_partial_scope=True "
            "with partial_scope_reason to compute a non-authoritative score anyway."
        )
    if allow_partial_scope and not partial_scope_reason:
        raise ReadinessGateError("partial_scope_reason is required when allow_partial_scope=True")

    missing = [g for g in REQUIRED_GATES if g not in gate_evidences]
    if missing:
        raise ReadinessGateError(f"Missing evidence for gates: {missing}")

    per_gate: dict[str, GateResult] = {
        gate_id: evaluate_gate(gate_id, gate_evidences[gate_id], mode_u)
        for gate_id in REQUIRED_GATES
    }
    passed_count = sum(1 for r in per_gate.values() if r.passed)
    gate_completion_pct = 100.0 * passed_count / len(REQUIRED_GATES)

    not_passed = [gid for gid, r in per_gate.items() if not r.passed]
    if not_passed:
        quality_subscore_pct = 100.0 * sum(
            _gate_quality(gid, gate_evidences[gid], mode_u) for gid in not_passed
        ) / len(not_passed)
    else:
        quality_subscore_pct = 100.0

    return ReadinessScore(
        mode=mode_u,
        scope=scope,
        gate_completion_pct=gate_completion_pct,
        quality_subscore_pct=quality_subscore_pct,
        per_gate=per_gate,
    )


_CHECKPOINT_PATTERN = re.compile(r"^v7_lite_checkpoint_(\d+)")


def _next_checkpoint_id(checkpoint_dir: Path) -> str:
    highest = 0
    if checkpoint_dir.exists():
        for path in checkpoint_dir.glob("v7_lite_checkpoint_*.yaml"):
            m = _CHECKPOINT_PATTERN.match(path.name)
            if m:
                highest = max(highest, int(m.group(1)))
    return f"V7LITE-{highest + 1:03d}"


def _yaml_scalar(value: object) -> str:
    if isinstance(value, str):
        escaped = value.replace('"', '\\"')
        return f'"{escaped}"'
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def write_readiness_checkpoint(
    readiness: ReadinessScore,
    commands_run: list[str],
    *,
    checkpoint_dir: str | Path = "reports/accp",
    scope_confirmation: str = "",
    remaining_holds: list[str] | None = None,
    safe_next_step: str = "",
) -> Path:
    """Write a deterministic ACCP-YAML checkpoint for one readiness score.

    ``v7_lite_readiness_percent`` and ``result`` are derived directly from
    ``readiness`` — never typed by the caller. ``checkpoint_id`` is
    auto-incremented from existing files in ``checkpoint_dir``.
    """
    checkpoint_path_dir = Path(checkpoint_dir)
    checkpoint_path_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_id = _next_checkpoint_id(checkpoint_path_dir)
    numeric_suffix = checkpoint_id.split("-")[-1]
    result = "PASS" if readiness.gate_completion_pct == 100.0 else "HOLD"
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    filename = f"v7_lite_checkpoint_{numeric_suffix}_{readiness.mode.lower()}_readiness_{now}.accp.yaml"
    file_path = checkpoint_path_dir / filename

    remaining_holds = remaining_holds or [
        f"gate:{gid}:{','.join(r.reasons)}"
        for gid, r in readiness.per_gate.items()
        if not r.passed
    ]

    lines: list[str] = [
        'accp_version: "2.0.0"',
        'source_format: "ACCP-YAML"',
        f"checkpoint_id: {checkpoint_id}",
        f"result: {result}",
        f"mode: {readiness.mode}",
        f"v7_lite_readiness_percent: {readiness.gate_completion_pct:.4f}",
        f"quality_subscore_percent: {readiness.quality_subscore_pct:.4f}",
        f"formula_version: {_yaml_scalar(readiness.formula_version)}",
        f"scope_confirmation: {_yaml_scalar(scope_confirmation)}",
        "data_scope:",
        f"  symbol_count: {len(readiness.scope.symbols)}",
        f"  feature_count: {readiness.scope.feature_count}",
        f"  uses_all_feature_groups: {_yaml_scalar(readiness.scope.uses_all_feature_groups)}",
        f"  start_ts: {readiness.scope.start_ts}",
        f"  end_ts: {readiness.scope.end_ts}",
        f"  canonical: {_yaml_scalar(readiness.scope.is_canonical())}",
        "gate_results:",
    ]
    for gate_id in REQUIRED_GATES:
        gr = readiness.per_gate[gate_id]
        lines.append(f"  {gate_id}:")
        lines.append(f"    passed: {_yaml_scalar(gr.passed)}")
        if gr.reasons:
            lines.append("    reasons:")
            for reason in gr.reasons:
                lines.append(f"      - {_yaml_scalar(reason)}")
        else:
            lines.append("    reasons: []")
    lines.append("commands_run:")
    for cmd in commands_run:
        lines.append(f"  - {_yaml_scalar(cmd)}")
    lines.append("remaining_holds:")
    for hold in remaining_holds:
        lines.append(f"  - {_yaml_scalar(hold)}")
    lines.append(f"safe_next_step: {_yaml_scalar(safe_next_step)}")

    file_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return file_path
