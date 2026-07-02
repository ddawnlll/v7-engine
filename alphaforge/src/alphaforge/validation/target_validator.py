"""Alpha Target Validator — scores research runs against the target alpha profile.

Consumes walk-forward validation (WFV) results and a target alpha profile
(YAML) to produce proximity scores, level assessments, blockers, and
next-step recommendations.  Produces a single consolidated report dict
that merges validator scores + WFV raw data + pipeline context.

Usage:
    validator = AlphaTargetValidator()
    report = validator.score(wfv_results)
    consolidated = report.consolidated(wfv_raw=wfv_results)
    # consolidated is a single dict ready for JSON serialisation
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Scoring weights (LOCKED_INITIAL_BASELINE)
# ---------------------------------------------------------------------------

WEIGHT_ECONOMIC: float = 0.35
WEIGHT_BEHAVIOR: float = 0.25
WEIGHT_VALIDATION: float = 0.25
WEIGHT_DATA_QUALITY: float = 0.15

# Default profile path — relative to this file, up to alphaforge/config/
_DEFAULT_PROFILE_PATH: str = os.path.normpath(
    os.path.join(
        os.path.dirname(__file__),
        "..", "..", "..", "config", "target_alpha_profile.yaml",
    )
)

# Ordered level check (highest first)
_LEVEL_ORDER: list[str] = [
    "V7_PROMOTION_CANDIDATE",
    "V7_SHADOW_CANDIDATE",
    "RESEARCH_CANDIDATE",
]


# ---------------------------------------------------------------------------
# TargetValidatorReport
# ---------------------------------------------------------------------------


@dataclass
class TargetValidatorReport:
    """Scored report from the Alpha Target Validator.

    Attributes:
        target_name: Name of the target profile used.
        target_proximity_score: Overall 0-100 proximity to target.
        economic_score:    0-100  (weight 35%) — net_R metrics.
        behavior_score:    0-100  (weight 25%) — exposure, no-trade, turnover.
        validation_score:  0-100  (weight 25%) — fold stability, PBO, overfit.
        data_quality_score: 0-100 (weight 15%) — synthetic/real, symbols, bars.
        level_assessment: One of NOT_ALPHA_CANDIDATE_YET / RESEARCH_CANDIDATE /
            V7_SHADOW_CANDIDATE / V7_PROMOTION_CANDIDATE.
        must_have_results: Nested dict per level with per-metric pass/fail.
        nice_to_have_results: Nested dict per level with per-metric pass/fail.
        main_blockers: Ordered list of blocking issues (most impactful first).
        next_recommendations: Ordered list of recommended next experiments.
        metric_details: All raw extracted metrics from the WFV results.
    """

    target_name: str = ""
    target_proximity_score: float = 0.0
    economic_score: float = 0.0
    behavior_score: float = 0.0
    validation_score: float = 0.0
    data_quality_score: float = 0.0
    level_assessment: str = "NOT_ALPHA_CANDIDATE_YET"
    must_have_results: dict = field(default_factory=dict)
    nice_to_have_results: dict = field(default_factory=dict)
    main_blockers: list[str] = field(default_factory=list)
    next_recommendations: list[str] = field(default_factory=list)
    metric_details: dict = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Consolidated report
    # ------------------------------------------------------------------

    def consolidated(self, wfv_raw: dict | None = None,
                     pipeline_context: dict | None = None) -> dict:
        """Merge validator scores, WFV raw data and pipeline context into
        a single dict suitable for JSON serialisation.

        This is the **canonical output** of the validator — one file with
        everything needed for analysis instead of N separate files.

        Args:
            wfv_raw:
                The original WFV results dict that was passed to
                ``score()``.  Its ``aggregate_metrics``, ``verdict``,
                ``overfit_flags``, ``per_fold_metrics`` and
                ``data_summary`` sections are included when present.
            pipeline_context:
                Optional pipeline-level metadata (step statuses,
                config, evidence checksums).

        Returns:
            A single flat+structured dict with:
            - header: report type, target, generated_at
            - validator: scores, level, blockers, recommendations
            - wfv_summary: key WFV aggregate + verdict + folds
            - wfv_raw: full original WFV dict (when provided)
            - pipeline_context: pipeline metadata (when provided)
            - must_have_results, nice_to_have_results, metric_details
        """
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        # --- Validator scores ---
        body = {
            "report_type": "alpha_target_validator_consolidated",
            "target_name": self.target_name,
            "generated_at": now,
            "validator": {
                "target_proximity_score": self.target_proximity_score,
                "economic_score": self.economic_score,
                "behavior_score": self.behavior_score,
                "validation_score": self.validation_score,
                "data_quality_score": self.data_quality_score,
                "level_assessment": self.level_assessment,
                "main_blockers": self.main_blockers,
                "next_recommendations": self.next_recommendations,
                "anomaly_flags": self.metric_details.get("_anomaly_flags", []),
            },
            "must_have_results": self.must_have_results,
            "nice_to_have_results": self.nice_to_have_results,
            "metric_details": self.metric_details,
        }

        # --- WFV summary (key fields extracted from raw) ---
        if wfv_raw is not None:
            agg = wfv_raw.get("aggregate_metrics", {})
            data_summary = wfv_raw.get("data_summary", {})

            body["wfv_summary"] = {
                "verdict": wfv_raw.get("verdict", ""),
                "folds": agg.get("n_folds", 0) or len(wfv_raw.get("fold_metrics", [])),
                "overfit_flags": len(wfv_raw.get("overfit_risk_flags", wfv_raw.get("overfit_flags", []))),
                "avg_net_sharpe": agg.get("avg_net_sharpe", 0.0),
                "avg_net_profit_factor": agg.get("avg_net_profit_factor", 0.0),
                "avg_net_expectancy": agg.get("avg_net_expectancy", 0.0),
                "avg_sharpe": agg.get("avg_sharpe", 0.0),
                "avg_win_rate": agg.get("avg_win_rate", 0.0),
                "avg_accuracy_gap": agg.get("avg_accuracy_gap", 0.0),
                "total_oos_trades": agg.get("total_oos_trades", 0),
                "folds_passing": agg.get("folds_passing", 0),
                "pass_ratio": agg.get("pass_ratio", 0.0),
                "data_source": data_summary.get("data_source", ""),
                "num_symbols": data_summary.get("n_symbols", 0),
                "n_bars": data_summary.get("n_bars", 0),
            }

            # Include full raw WFV dict for drill-down
            body["wfv_raw"] = wfv_raw

        # --- Pipeline context ---
        if pipeline_context is not None:
            body["pipeline_context"] = pipeline_context

        return body


# ---------------------------------------------------------------------------
# AlphaTargetValidator
# ---------------------------------------------------------------------------


class AlphaTargetValidator:
    """Scores research runs against the target alpha profile.

    Loads a YAML profile describing must-have / nice-to-have thresholds per
    candidate level, then scores a WFV results dict against those thresholds.
    """

    def __init__(self, profile_path: str | None = None):
        """Load target profile from YAML.

        Args:
            profile_path: Path to the target alpha profile YAML.
                Defaults to ``alphaforge/config/target_alpha_profile.yaml``.

        Raises:
            FileNotFoundError: Profile file not found.
            ValueError: PyYAML is not installed or profile is malformed.
        """
        if yaml is None:
            raise ValueError(
                "PyYAML is required but not installed. "
                "Install with: pip install pyyaml"
            )

        path = profile_path or _DEFAULT_PROFILE_PATH
        if not os.path.isfile(path):
            raise FileNotFoundError(
                f"Target alpha profile not found at: {path}"
            )

        with open(path) as f:
            self._profile: dict = yaml.safe_load(f)

        if not isinstance(self._profile, dict):
            raise ValueError(
                f"Target alpha profile must be a mapping, got "
                f"{type(self._profile).__name__}"
            )

        self._target_name: str = self._profile.get("target_name", "UNKNOWN")
        self._levels: dict = self._profile.get("levels", {})

        if not self._levels:
            raise ValueError(
                "Target alpha profile has no 'levels' section"
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def score(self, wfv_results: dict) -> TargetValidatorReport:
        """Score a WFV result set against the target profile.

        Args:
            wfv_results: The full WFV results dict from the pipeline.
                Expected to contain oos_summary, aggregate_metrics, metrics,
                cost_stress, no_trade_comparison, multiple_hypothesis_control,
                data_scope, and / or the ``walk_forward_result_to_dict``
                output structure.

        Returns:
            TargetValidatorReport with proximity scores, level assessment,
            blockers, and recommendations.
        """
        # 1. Flatten all relevant metrics
        metrics = self._extract_metrics(wfv_results)

        # 2. Score each dimension
        economic_score = self._score_economic(metrics)
        behavior_score = self._score_behavior(metrics)
        validation_score = self._score_validation(metrics)
        data_quality_score = self._score_data_quality(metrics)

        # ------------------------------------------------------------------
        # Hard guardrails — prevent inflated scores from edge cases
        # ------------------------------------------------------------------
        active_tc = metrics.get("active_trade_count", 0) or 0
        exposure = metrics.get("exposure_pct", 0.0) or 0.0
        fold_pass_ratio = metrics.get("fold_pass_ratio", 0.0) or 0.0
        pbo = str(metrics.get("pbo_risk", "NOT_RUN") or "NOT_RUN")
        is_synthetic = metrics.get("is_synthetic", True)
        cost_stress = metrics.get("cost_stress_survives", False)
        npf = metrics.get("net_profit_factor", 1.0) or 1.0
        ns = metrics.get("net_sharpe", 0.0) or 0.0

        anomaly_flags: list[str] = []

        # GR1: No active trades → no alpha evidence
        if active_tc == 0:
            economic_score = 0.0
            anomaly_flags.append("GR1: no active trades — economic score zeroed")

        # GR2: Near-zero exposure → behavior score hard cap at 15
        if exposure < 2.0:
            behavior_score = min(behavior_score, 15.0)
            anomaly_flags.append("GR2: exposure < 2% — behavior score capped at 15")

        # GR3: Synthetic random-walk → economic score hard cap at 25
        if is_synthetic:
            economic_score = min(economic_score, 25.0)
            data_quality_score = min(data_quality_score, 20.0)
            anomaly_flags.append("GR3: synthetic data — economic score capped at 25, data quality at 20")

        # GR4: PBO NOT_RUN → validation score hard cap at 35
        if pbo == "NOT_RUN":
            validation_score = min(validation_score, 35.0)
            anomaly_flags.append("GR4: PBO NOT_RUN — validation score capped at 35")

        # GR5: Unrealistic PF/Sharpe → anomaly flag
        if npf > 10.0 or ns > 5.0:
            anomaly_flags.append(
                f"GR5: unrealistic metrics — PF={npf:.1f}, Sharpe={ns:.2f} "
                f"(likely synthetic artifact)"
            )

        # Recompute target proximity with guard-railed scores
        target_proximity = round(
            economic_score * WEIGHT_ECONOMIC
            + behavior_score * WEIGHT_BEHAVIOR
            + validation_score * WEIGHT_VALIDATION
            + data_quality_score * WEIGHT_DATA_QUALITY,
            1,
        )

        # GR6: fold_pass_ratio == 0 → hard cap proximity (no fold evidence = no alpha)
        if fold_pass_ratio <= 0.0:
            target_proximity = min(target_proximity, 35.0)
            anomaly_flags.append("GR6: fold_pass_ratio == 0 — target proximity capped at 35")

        # 3. Check all levels (must_have + nice_to_have)
        must_have_results: dict = {}
        nice_to_have_results: dict = {}
        level_assessment = self._assess_level(
            metrics, must_have_results, nice_to_have_results,
        )

        # GR7: cost_stress_survives false → override level to NOT_ALPHA_CANDIDATE_YET
        #      (V7 readiness cannot exist without cost stress survival)
        if not cost_stress:
            if level_assessment in ("V7_SHADOW_CANDIDATE", "V7_PROMOTION_CANDIDATE"):
                level_assessment = "NOT_ALPHA_CANDIDATE_YET"
                anomaly_flags.append("GR7: cost stress not survived — V7 readiness zeroed")

        # Store anomaly flags in metric_details for the consolidated report
        if anomaly_flags:
            if "_anomaly_flags" not in metrics:
                metrics["_anomaly_flags"] = []
            metrics["_anomaly_flags"].extend(anomaly_flags)

        # 5. Detect blockers
        main_blockers = self._detect_blockers(metrics)

        # 6. Generate recommendations
        next_recommendations = self._generate_recommendations(metrics)

        return TargetValidatorReport(
            target_name=self._target_name,
            target_proximity_score=target_proximity,
            economic_score=economic_score,
            behavior_score=behavior_score,
            validation_score=validation_score,
            data_quality_score=data_quality_score,
            level_assessment=level_assessment,
            must_have_results=must_have_results,
            nice_to_have_results=nice_to_have_results,
            main_blockers=main_blockers,
            next_recommendations=next_recommendations,
            metric_details=metrics,
        )

    # ------------------------------------------------------------------
    # Metric extraction
    # ------------------------------------------------------------------

    def _extract_metrics(self, wfv_results: dict) -> dict:
        """Flatten all relevant metrics from ``wfv_results`` into a single dict.

        Reads from both the pipeline-style dict (``oos_summary``, ``metrics``,
        ``cost_stress`` etc.) and the ``walk_forward_result_to_dict`` output
        (``aggregate_metrics``, ``data_summary`` etc.).
        """
        oos = wfv_results.get("oos_summary", {}) or {}
        agg = wfv_results.get("aggregate_metrics", {}) or {}
        met = wfv_results.get("metrics", {}) or {}
        cost = wfv_results.get("cost_stress", {}) or {}
        regime = wfv_results.get("regime_breakdown", {}) or {}
        no_trade = wfv_results.get("no_trade_comparison", {}) or {}
        mht = wfv_results.get("multiple_hypothesis_control", {}) or {}
        data_scope = wfv_results.get("data_scope", {}) or {}
        data_summary = wfv_results.get("data_summary", {}) or {}

        # -- Net R economic (PRIMARY) --
        # Prefer aggregate_metrics (from WF runner dict output), then
        # oos_summary (pipeline dict output), then fallback.
        net_sharpe = (
            agg.get("avg_net_sharpe")
            or oos.get("net_sharpe")
            or 0.0
        )
        net_profit_factor = (
            agg.get("avg_net_profit_factor")
            or oos.get("net_profit_factor")
            or 1.0
        )
        net_expectancy = (
            agg.get("avg_net_expectancy")
            or oos.get("net_expectancy")
            or 0.0
        )

        # -- Classic economic (fallback) --
        oos_sharpe = oos.get("oos_sharpe", 0.0) or 0.0
        oos_profit_factor = oos.get("oos_profit_factor", 1.0) or 1.0
        oos_expectancy_r = oos.get("oos_expectancy_r", 0.0) or 0.0
        oos_max_drawdown = oos.get("oos_max_drawdown_r", 0.0) or 0.0
        oos_trade_count = oos.get("oos_trade_count", 0) or 0

        # -- Active trade / behavior --
        # NOTE: Supports both pipeline-style (metrics/oos_summary) and
        # walk_forward_runner.py dict shape (aggregate_metrics.total_oos_trades).
        total_bars = data_summary.get("total_bars", 0) or 0
        active_trade_count = (
            met.get("active_trade_count")
            or oos.get("active_trade_count")
            or oos_trade_count
            or agg.get("total_oos_trades", 0)
        )
        exposure_pct = (
            met.get("exposure_pct", 0.0)
            or oos.get("exposure_pct", 0.0)
            or ((active_trade_count / total_bars * 100) if total_bars > 0 else 0.0)
        )
        turnover = met.get("turnover", 0.0) or 0.0
        avg_hold_bars = met.get("avg_hold_bars", 0.0) or 0.0

        # -- Validation --
        fold_pass_ratio = agg.get("pass_ratio", 0.0) or oos.get("fold_pass_ratio", 0.0) or 0.0
        fold_count = wfv_results.get("fold_count", 0) or agg.get("n_folds", 0) or 0
        avg_accuracy_gap = agg.get("avg_accuracy_gap", 0.0) or oos.get("overfit_gap", 0.0) or 0.0

        # PBO / overfit risk
        pbo_risk = mht.get("pbo_or_backtest_overfit_risk", "NOT_RUN") or "NOT_RUN"

        # -- No-trade comparison --
        active_beats_no_trade = no_trade.get("active_beats_no_trade", False) or False

        # -- Cost stress --
        cost_stress_survives = cost.get("combined_stress_edge_survives", False) or False

        # -- Data scope --
        symbols = data_scope.get("symbols", []) or []
        n_symbols = len(symbols)
        if not n_symbols:
            n_symbols = agg.get("n_symbols", 0) or agg.get("num_symbols", 0) or 0
        if not n_symbols:
            n_symbols = data_summary.get("n_symbols", 0) or 0

        total_bars = data_summary.get("total_bars", 0) or 0

        data_quality_summary = str(data_scope.get("data_quality_summary", "") or "")
        data_source_raw = str(data_summary.get("data_source", "") or "")
        # Default to synthetic unless explicitly marked as real/binance
        if data_source_raw and "synthetic" not in data_source_raw.lower():
            is_synthetic = False
        elif "real" in data_quality_summary.lower() or "binance" in data_quality_summary.lower():
            is_synthetic = False
        elif "synthetic" in data_quality_summary.lower() or "synthetic" in data_source_raw.lower():
            is_synthetic = True
        else:
            is_synthetic = True  # safe default for unmarked data

        # -- Feature set refs (for ablation detection) --
        feature_set_refs = wfv_results.get("feature_set_refs", []) or []

        # -- Regime stability --
        edge_only_in_rare_regime = regime.get("edge_only_in_rare_regime", True)

        # -- Symbol stability --
        symbol_stability_section = wfv_results.get("symbol_stability", {}) or {}
        symbol_stability_pass = symbol_stability_section.get("verdict") == "PASS"

        # -- MHT correction --
        mht_status = str(mht.get("mht_status", "NONE_APPLIED") or "NONE_APPLIED")
        has_mht = mht_status == "APPLIED"
        deflated_sharpe = mht.get("deflated_sharpe_or_equivalent")
        dsr_positive = deflated_sharpe is not None and deflated_sharpe > 0

        # -- Composite metrics --
        regime_stable = not edge_only_in_rare_regime
        real_data_multi_symbol_pass = n_symbols > 1 and not is_synthetic

        return {
            # Net R economic (PRIMARY)
            "net_sharpe": net_sharpe,
            "net_profit_factor": net_profit_factor,
            "net_expectancy": net_expectancy,
            # Classic economic (fallback)
            "oos_sharpe": oos_sharpe,
            "oos_profit_factor": oos_profit_factor,
            "oos_expectancy_r": oos_expectancy_r,
            "oos_max_drawdown": oos_max_drawdown,
            "oos_trade_count": oos_trade_count,
            # Active trade / behavior
            "active_trade_count": active_trade_count,
            "exposure_pct": exposure_pct,
            "turnover": turnover,
            "avg_hold_bars": avg_hold_bars,
            # Validation
            "fold_pass_ratio": fold_pass_ratio,
            "fold_count": fold_count,
            "pbo_risk": pbo_risk,
            "overfit_gap": avg_accuracy_gap,
            # No-trade
            "active_beats_no_trade": active_beats_no_trade,
            # Cost
            "cost_stress_survives": cost_stress_survives,
            # Data
            "n_symbols": n_symbols,
            "total_bars": total_bars,
            "is_synthetic": is_synthetic,
            "data_quality_summary": data_quality_summary,
            "feature_set_refs": feature_set_refs,
            # Stability
            "edge_only_in_rare_regime": edge_only_in_rare_regime,
            "regime_stable": regime_stable,
            "symbol_stability_pass": symbol_stability_pass,
            # MHT
            "mht_status": mht_status,
            "has_mht": has_mht,
            "deflated_sharpe": deflated_sharpe,
            "dsr_positive": dsr_positive,
            # Composite
            "real_data_multi_symbol_pass": real_data_multi_symbol_pass,
        }

    # ------------------------------------------------------------------
    # Dimension scoring
    # ------------------------------------------------------------------

    @staticmethod
    def _score_economic(m: dict) -> float:
        """Economic score (0-100) based on net_R metrics.

        Components:
            - Net Sharpe (40% of economic)
            - Net Profit Factor (35% of economic)
            - Net Expectancy (25% of economic)
        """
        ns = m.get("net_sharpe", 0.0)
        npf = m.get("net_profit_factor", 1.0)
        nexp = m.get("net_expectancy", 0.0)

        # -- Detect not-plumbed: all three are zero --
        all_zero = abs(ns) < 1e-9 and abs(npf - 1.0) < 1e-9 and abs(nexp) < 1e-9
        # Also detect not-plumbed when everything is exactly zero
        if all_zero:
            sharpe_score = 0.0
            pf_score = 0.0
            exp_score = 0.0
        else:
            # Net Sharpe
            if ns <= 0.0:
                sharpe_score = 20.0
            elif ns < 0.5:
                sharpe_score = 40.0
            elif ns < 1.0:
                sharpe_score = 70.0
            else:
                sharpe_score = 100.0

            # Net Profit Factor
            if npf <= 1.0:
                pf_score = 0.0
            elif npf < 1.05:
                pf_score = 25.0
            elif npf < 1.10:
                pf_score = 50.0
            elif npf < 1.20:
                pf_score = 75.0
            else:
                pf_score = 100.0

            # Net Expectancy
            if nexp <= 0.0:
                exp_score = 0.0
            elif nexp < 0.05:
                exp_score = 25.0
            elif nexp < 0.10:
                exp_score = 50.0
            elif nexp < 0.15:
                exp_score = 75.0
            else:
                exp_score = 100.0

        return round(
            0.40 * sharpe_score + 0.35 * pf_score + 0.25 * exp_score,
            1,
        )

    @staticmethod
    def _score_behavior(m: dict) -> float:
        """Behavior score (0-100) based on exposure, no-trade quality, turnover.

        Components:
            - Exposure % (40% of behavior)
            - No-trade quality / active beats no-trade (35% of behavior)
            - Turnover reasonableness (25% of behavior)
        """
        exposure = m.get("exposure_pct", 0.0)

        # Exposure score: 10-40% ideal, 5-60% acceptable, edges penalised
        if 10.0 <= exposure <= 40.0:
            exp_score = 100.0
        elif 5.0 <= exposure <= 60.0:
            exp_score = 70.0
        elif (3.0 <= exposure < 5.0) or (60.0 < exposure <= 70.0):
            exp_score = 40.0
        else:
            exp_score = 10.0

        # No-trade quality
        ntq_score = 100.0 if m.get("active_beats_no_trade", False) else 30.0

        # Turnover: 0.1-0.9 ideal, wider still acceptable
        turnover = m.get("turnover", 0.0)
        if 0.10 <= turnover <= 0.90:
            to_score = 100.0
        elif 0.05 <= turnover < 0.10 or 0.90 < turnover <= 1.50:
            to_score = 60.0
        else:
            to_score = 20.0

        return round(
            0.40 * exp_score + 0.35 * ntq_score + 0.25 * to_score,
            1,
        )

    @staticmethod
    def _score_validation(m: dict) -> float:
        """Validation score (0-100) based on fold stability, PBO, overfit gap.

        Components:
            - Fold pass ratio (35% of validation)
            - PBO / backtest overfit risk (35% of validation)
            - Overfit gap (30% of validation)
        """
        pass_ratio = m.get("fold_pass_ratio", 0.0)

        # Fold pass ratio
        if pass_ratio >= 0.80:
            fold_score = 100.0
        elif pass_ratio >= 0.60:
            fold_score = 70.0
        elif pass_ratio >= 0.40:
            fold_score = 40.0
        else:
            fold_score = 10.0

        # PBO risk
        pbo = str(m.get("pbo_risk", "NOT_RUN") or "NOT_RUN")
        if pbo == "LOW":
            pbo_score = 100.0
        elif pbo == "MEDIUM":
            pbo_score = 60.0
        elif pbo == "HIGH":
            pbo_score = 20.0
        elif pbo == "CRITICAL":
            pbo_score = 0.0
        else:  # NOT_RUN, UNKNOWN
            pbo_score = 30.0

        # Overfit gap (absolute accuracy gap across folds)
        gap = abs(m.get("overfit_gap", 0.0) or 0.0)
        if gap < 0.05:
            gap_score = 100.0
        elif gap < 0.10:
            gap_score = 70.0
        elif gap < 0.20:
            gap_score = 40.0
        else:
            gap_score = 10.0

        return round(
            0.35 * fold_score + 0.35 * pbo_score + 0.30 * gap_score,
            1,
        )

    @staticmethod
    def _score_data_quality(m: dict) -> float:
        """Data quality score (0-100) based on source, symbol count, bar count.

        Components:
            - Data source — synthetic vs real (40% of data quality)
            - Symbol count (30% of data quality)
            - Bar count (30% of data quality)
        """
        is_synthetic = m.get("is_synthetic", True)

        # Source score: synthetic data penalised heavily (real baseline later)
        source_score = 10.0 if is_synthetic else 80.0

        # Symbol count
        n_sym = m.get("n_symbols", 0) or 0
        if n_sym >= 5:
            sym_score = 100.0
        elif n_sym >= 3:
            sym_score = 80.0
        elif n_sym >= 2:
            sym_score = 60.0
        elif n_sym >= 1:
            sym_score = 40.0
        else:
            sym_score = 0.0

        # Bar count (total across all symbols)
        n_bars = m.get("total_bars", 0) or 0
        if n_bars >= 10000:
            bars_score = 100.0
        elif n_bars >= 5000:
            bars_score = 80.0
        elif n_bars >= 2000:
            bars_score = 60.0
        elif n_bars >= 500:
            bars_score = 40.0
        else:
            bars_score = 20.0

        return round(
            0.40 * source_score + 0.30 * sym_score + 0.30 * bars_score,
            1,
        )

    # ------------------------------------------------------------------
    # Level assessment
    # ------------------------------------------------------------------

    def _check_level(
        self,
        level_name: str,
        level_config: dict,
        metrics: dict,
    ) -> tuple[dict, dict, list[str]]:
        """Check all must_have and nice_to_have for a single level.

        Returns:
            (must_have_results, nice_to_have_results, failures)
            where ``failures`` is a list of must-have failures (empty if
            the level's must_have criteria are all met).
        """
        must_have_results: dict = {}
        nice_to_have_results: dict = {}
        failures: list[str] = []

        for metric_key, rule in level_config.get("must_have", {}).items():
            actual_value = self._resolve_metric(metric_key, metrics)
            passed, reason = self._check_rule(
                metric_key, rule, actual_value, metrics,
            )
            must_have_results[metric_key] = {
                "passed": passed,
                "actual": actual_value,
                "required": rule,
                "reason": reason,
            }
            if not passed:
                failures.append(f"{metric_key}: {reason}")

        for metric_key, rule in level_config.get("nice_to_have", {}).items():
            actual_value = self._resolve_metric(metric_key, metrics)
            passed, reason = self._check_rule(
                metric_key, rule, actual_value, metrics,
            )
            nice_to_have_results[metric_key] = {
                "passed": passed,
                "actual": actual_value,
                "required": rule,
                "reason": reason,
            }

        return must_have_results, nice_to_have_results, failures

    @staticmethod
    def _resolve_metric(metric_key: str, metrics: dict) -> Any:
        """Resolve a profile metric key to its actual value in the metrics dict.

        Maps human-readable keys from the YAML profile to the flattened
        metric names produced by ``_extract_metrics``.
        """
        mapping: dict[str, str] = {
            "net_profit_factor": "net_profit_factor",
            "net_sharpe": "net_sharpe",
            "max_drawdown": "oos_max_drawdown",
            "fold_pass_ratio": "fold_pass_ratio",
            "pbo_risk": "pbo_risk",
            "active_trade_count": "active_trade_count",
            "exposure_pct": "exposure_pct",
            "active_beats_no_trade": "active_beats_no_trade",
            "cost_stress_survives": "cost_stress_survives",
            "symbol_stability": "symbol_stability_pass",
            "regime_stability": "regime_stable",
            "dsr_positive": "dsr_positive",
            "mht_pass": "has_mht",
            "real_data_multi_symbol_pass": "real_data_multi_symbol_pass",
        }
        key = mapping.get(metric_key, metric_key)
        return metrics.get(key)

    @staticmethod
    def _check_rule(
        metric_key: str,
        rule: dict,
        actual_value: Any,
        metrics: dict,
    ) -> tuple[bool, str | None]:
        """Check a single rule from the YAML profile against an actual value.

        Supports constraint types:
            - ``min``: actual >= threshold
            - ``max``: actual <= threshold
            - ``value``: exact match (or truthy check for bool thresholds
              and special symbolic metrics)
            - ``not``: actual != threshold

        Returns:
            (passed, fail_reason) tuple.
        """
        for constraint, threshold in rule.items():
            if constraint == "min":
                if not isinstance(actual_value, (int, float)):
                    return False, (
                        f"Value '{actual_value}' is not numeric for min check"
                    )
                if actual_value < threshold:
                    return False, (
                        f"Value {actual_value:.4f} < min {threshold}"
                    )

            elif constraint == "max":
                if not isinstance(actual_value, (int, float)):
                    return False, (
                        f"Value '{actual_value}' is not numeric for max check"
                    )
                # For negative-threshold metrics (e.g. max_drawdown), more
                # negative = worse, so we check actual < threshold (deeper
                # drawdown than the limit) rather than actual > threshold.
                if threshold < 0 and actual_value < 0:
                    if actual_value < threshold:
                        return False, (
                            f"Value {actual_value:.4f} exceeds max {threshold} "
                            f"(more negative than limit)"
                        )
                elif actual_value > threshold:
                    return False, (
                        f"Value {actual_value:.4f} > max {threshold}"
                    )

            elif constraint == "value":
                # Boolean threshold: true / false
                if isinstance(threshold, bool):
                    if bool(actual_value) != threshold:
                        return False, (
                            f"Expected {threshold}, got {bool(actual_value)} "
                            f"(raw: {actual_value})"
                        )
                # String threshold like ``pass`` or ``fail``
                elif threshold == "pass" or threshold == "true":
                    passed_check = (
                        (isinstance(actual_value, str) and actual_value.upper() == "PASS")
                        or (isinstance(actual_value, bool) and actual_value)
                    )
                    if not passed_check:
                        return False, (
                            f"Expected '{threshold}', got '{actual_value}'"
                        )
                elif threshold == "fail" or threshold == "false":
                    failed_check = (
                        (isinstance(actual_value, str) and actual_value.upper() == "FAIL")
                        or (isinstance(actual_value, bool) and not actual_value)
                    )
                    if not failed_check:
                        return False, (
                            f"Expected '{threshold}', got '{actual_value}'"
                        )
                else:
                    if actual_value != threshold:
                        return False, (
                            f"Value '{actual_value}' != expected '{threshold}'"
                        )

            elif constraint == "not":
                if actual_value == threshold:
                    return False, (
                        f"Value '{actual_value}' is forbidden "
                        f"(constraint: not {threshold})"
                    )

        return True, None

    def _assess_level(
        self,
        metrics: dict,
        must_have_results: dict,
        nice_to_have_results: dict,
    ) -> str:
        """Assess the highest achievable candidate level.

        Checks from most stringent (V7_PROMOTION_CANDIDATE) down to
        RESEARCH_CANDIDATE. Returns the first level whose must_have
        criteria are all met, or ``NOT_ALPHA_CANDIDATE_YET``.

        Populates ``must_have_results`` and ``nice_to_have_results``
        for all levels (not just the highest passing), keyed by level name.
        """
        highest_passing: str = "NOT_ALPHA_CANDIDATE_YET"

        for level_name in _LEVEL_ORDER:
            level_config = self._levels.get(level_name)
            if level_config is None:
                continue

            mh, nh, failures = self._check_level(
                level_name, level_config, metrics,
            )
            must_have_results[level_name] = mh
            nice_to_have_results[level_name] = nh

            if not failures and highest_passing == "NOT_ALPHA_CANDIDATE_YET":
                highest_passing = level_name

        return highest_passing

    # ------------------------------------------------------------------
    # Blocker detection
    # ------------------------------------------------------------------

    def _detect_blockers(self, metrics: dict) -> list[str]:
        """Detect ordered blockers from metric values.

        Returns blockers sorted by estimated impact (most critical first).
        """
        blockers: list[str] = []

        # 1. net_R metrics not plumbed
        ns = metrics.get("net_sharpe", 0.0) or 0.0
        npf = metrics.get("net_profit_factor", 1.0) or 1.0
        if abs(ns) < 1e-9 and abs(npf - 1.0) < 1e-9:
            blockers.append("net_R metrics not fully plumbed")

        # 2. synthetic data only
        if metrics.get("is_synthetic", True):
            blockers.append("synthetic data only")

        # 3. PBO HIGH / CRITICAL
        pbo = str(metrics.get("pbo_risk", "NOT_RUN") or "NOT_RUN")
        if pbo in ("HIGH", "CRITICAL"):
            blockers.append(f"PBO {pbo}")

        # 4. No feature family ablation — detect from feature_set_refs
        feature_refs = metrics.get("feature_set_refs", []) or []
        if not feature_refs:
            blockers.append("no feature family ablation")

        # 5. Real-data net_R WFV — implicit in synthetic check (2)

        # 6. Fold count insufficient
        fold_count = metrics.get("fold_count", 0) or 0
        if 0 < fold_count < 6:
            blockers.append(
                f"fold count insufficient ({fold_count} < 6)"
            )

        # 7. Trades insufficient
        active_tc = metrics.get("active_trade_count", 0) or 0
        if 0 < active_tc < 100:
            blockers.append(
                f"trades insufficient ({active_tc} < 100)"
            )

        # 8. Exposure out of range
        exposure = metrics.get("exposure_pct", 0.0) or 0.0
        if exposure > 0 and (exposure < 5 or exposure > 60):
            blockers.append(
                f"exposure out of range ({exposure:.1f}%)"
            )

        # 9. Cost stress not survived
        if not metrics.get("cost_stress_survives", False):
            blockers.append("cost stress not survived")

        return blockers

    # ------------------------------------------------------------------
    # Recommendations
    # ------------------------------------------------------------------

    def _generate_recommendations(self, metrics: dict) -> list[str]:
        """Generate next-step recommendations based on metric gaps.

        Ordered by estimated impact (most impactful first).
        """
        recs: list[str] = []

        # 1. Run feature family ablation
        feature_refs = metrics.get("feature_set_refs", []) or []
        if not feature_refs:
            recs.append("Run feature family ablation")

        # 2. Replace synthetic data
        if metrics.get("is_synthetic", True):
            recs.append("Replace synthetic data with real Binance data")

        # 3. Increase fold count
        fold_count = metrics.get("fold_count", 0) or 0
        if 0 < fold_count < 6:
            recs.append("Increase fold count")

        # 4. Increase n_bars or symbols
        active_tc = metrics.get("active_trade_count", 0) or 0
        if 0 < active_tc < 100:
            recs.append("Increase n_bars or symbols")

        # 5. Apply MHT correction
        pbo = str(metrics.get("pbo_risk", "NOT_RUN") or "NOT_RUN")
        if pbo in ("HIGH", "CRITICAL"):
            recs.append("Apply MHT correction")

        # 6. Tune confidence threshold
        exposure = metrics.get("exposure_pct", 0.0) or 0.0
        if exposure > 0 and (exposure < 5 or exposure > 60):
            recs.append("Tune confidence threshold")

        # 7. Use net_R cost decomposition
        ns = metrics.get("net_sharpe", 0.0) or 0.0
        npf = metrics.get("net_profit_factor", 1.0) or 1.0
        if abs(ns) < 1e-9 and abs(npf - 1.0) < 1e-9:
            recs.append("Use net_R cost decomposition")

        # 8. Run regime stability analysis
        if metrics.get("is_synthetic", True):
            recs.append("Run regime stability analysis")

        return recs
