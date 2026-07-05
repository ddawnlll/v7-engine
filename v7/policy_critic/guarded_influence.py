"""
Guarded influence — critic advisory modulation within hard gate limits.

The GuardedInfluenceManager translates critic verdicts into modulated
configurations that V7 policy may enact. It enforces the critical boundary:

  **Cannot override HARD_BLOCK gates** — if a hard gate has blocked the
  action, the critic's opinion is irrelevant and all modulation is skipped.

Key principles (per ai_summary §Staged Rollout and §Action Mapping):
  - DOWNWEIGHT_CONFIDENCE: critic recommends reducing confidence, V7 policy
    multiplies confidence_final_score by the adjustment factor.
  - VETO_TO_NO_TRADE: critic recommends no-trade, V7 policy sets
    recommended_action = NO_TRADE.
  - ALLOW: no modulation; execution proceeds as normal.
  - REQUIRE_REVIEW: critic flags for human attention; no automated action.
  - All modulation is logged with full audit trail.
  - Per-mode activation: SWING may be active while SCALP is HOLD.

Flow (Phase 5, per ai_summary §Staged Rollout):
  HardGateResult + CriticReview
    -> GuardedInfluenceManager.soft_modulate()
    -> ModulatedGateConfig
    -> V7 policy enacts or ignores

Domain boundaries (never violated):
  - Does NOT bypass hard gates (HARD_BLOCK -> no modulation)
  - Does NOT open or close trades
  - Does NOT create new action enums
  - Does NOT hold live veto authority — V7 policy enacts veto
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Valid verdicts
# ---------------------------------------------------------------------------

VALID_VERDICTS = {"ALLOW", "DOWNWEIGHT_CONFIDENCE", "VETO_TO_NO_TRADE", "REQUIRE_REVIEW", "NOT_EVALUATED"}
INFLUENCE_VERDICTS = {"DOWNWEIGHT_CONFIDENCE", "VETO_TO_NO_TRADE"}


# ---------------------------------------------------------------------------
# Modulation log
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ModulationEntry:
    """A single modulation event — record of critic influence on one decision.

    Attributes:
        timestamp:          ISO 8601 UTC.
        mode:               Trading mode.
        symbol:             Trading symbol.
        critic_verdict:     The verdict that triggered modulation.
        original_confidence: Confidence score before modulation.
        adjusted_confidence: Confidence score after modulation.
        modulation_factor:  The factor applied (0-1). 0.0 = veto, 1.0 = no change.
        hard_gate_blocked:  True if a HARD_BLOCK was in effect (no modulation).
        is_enacted:         True if V7 policy enacted this modulation.
        detail:             Free-text description.
    """
    timestamp: str
    mode: str
    symbol: str
    critic_verdict: str
    original_confidence: float
    adjusted_confidence: float
    modulation_factor: float
    hard_gate_blocked: bool
    is_enacted: bool
    detail: str = ""


# ---------------------------------------------------------------------------
# ModulatedGateConfig
# ---------------------------------------------------------------------------


@dataclass
class ModulatedGateConfig:
    """Result of applying critic verdict to a gate configuration.

    This is the output of soft_modulate() — the V7 policy engine reads
    this to decide whether to enact the critic's recommendation.

    Attributes:
        should_block:           True if the action should be blocked
                                (NO_TRADE) based on critic verdict.
        confidence_multiplier:  Multiplier to apply to confidence_final_score
                                (1.0 = no change, 0.0 = zero confidence).
        reason:                 Machine-readable reason code.
        detail:                 Human-readable description.
        is_advisory:            Always True — policy may disregard.
        hard_gate_blocked:      True if hard gate blocked independently.
        critic_verdict:         Original critic verdict.
    """
    should_block: bool = False
    confidence_multiplier: float = 1.0
    reason: str = ""
    detail: str = ""
    is_advisory: bool = True
    hard_gate_blocked: bool = False
    critic_verdict: str = "NOT_EVALUATED"


# ---------------------------------------------------------------------------
# GuardedInfluenceManager
# ---------------------------------------------------------------------------


class GuardedInfluenceManager:
    """Translates critic verdicts into modulated gate configurations.

    The manager enforces the critical invariant:
      **Cannot override HARD_BLOCK gates**

    If a hard gate has blocked the action, all modulation is skipped
    and the block stands.

    Per-mode activation allows SWING-only influence while SCALP/AGGRESSIVE
    operate in shadow-only mode (per ai_summary §Domain Boundaries).
    """

    def __init__(
        self,
        *,
        active_modes: set[str] | None = None,
        downweight_thresholds: dict[str, float] | None = None,
        logger_fn: Callable[[ModulationEntry], None] | None = None,
    ):
        """Initialise the guarded influence manager.

        Args:
            active_modes: Set of modes where influence is active (e.g. {"SWING"}).
                          Modes not in this set pass through unchanged. Default:
                          {"SWING"} — SCALP/AGGRESSIVE influence is HOLD.
            downweight_thresholds: Per-mode dict: minimum confidence_multiplier
                          per mode (clamped). Default: {"SWING": 0.3, "SCALP": 1.0,
                          "AGGRESSIVE_SCALP": 1.0}.
            logger_fn:    Optional function to persist modulation entries (e.g.
                          database write). If None, entries are logged but not
                          persisted beyond in-memory tracking.
        """
        self._active_modes = (
            set(active_modes) if active_modes is not None else {"SWING"}
        )
        self._dw_thresholds = dict(downweight_thresholds or {
            "SWING": 0.3,
            "SCALP": 1.0,
            "AGGRESSIVE_SCALP": 1.0,
        })
        self._logger_fn = logger_fn
        self._modulation_log: list[ModulationEntry] = []

    @property
    def modulation_log(self) -> list[ModulationEntry]:
        """Read-only view of the modulation log."""
        return list(self._modulation_log)

    @property
    def active_modes(self) -> set[str]:
        """Set of modes where influence is currently active."""
        return set(self._active_modes)

    def set_active_modes(self, modes: set[str]) -> None:
        """Update the set of active modes."""
        self._active_modes = set(modes)
        logger.info(
            "GuardedInfluenceManager: active modes set to %s",
            sorted(self._active_modes),
        )

    def soft_modulate(
        self,
        gate_config: dict[str, Any] | None = None,
        critic_verdict: str = "NOT_EVALUATED",
        *,
        mode: str = "SWING",
        symbol: str = "",
        confidence_score: float = 0.5,
        hard_gate_blocked: bool = False,
        critic_adjustment: float = 1.0,
    ) -> ModulatedGateConfig:
        """Produce a modulated gate configuration from critic verdict.

        This is the core translation function. It applies the rules:

          HARD_BLOCK gate fail:
            -> NO modulation. should_block=True, multiplier=1.0.
            -> Rule 1: "Hard gate fail -> NO_TRADE. Critic NOT consulted."

          Mode not active (e.g. SCALP when only SWING is active):
            -> No modulation. should_block=False, multiplier=1.0.

          Critic ALLOW:
            -> No modulation. should_block=False, multiplier=1.0.

          Critic DOWNWEIGHT_CONFIDENCE:
            -> Set confidence_multiplier to critic_adjustment (clamped per-mode).
            -> should_block=False (confidence reduction is not a block).

          Critic VETO_TO_NO_TRADE:
            -> Set should_block=True (policy may enact as NO_TRADE).
            -> multiplier=0.0.

          Critic REQUIRE_REVIEW:
            -> No modulation, but reason is set for human attention.

        Args:
            gate_config:       Original gate config dict (unused, reserved for
                               future extension). If None, a default is assumed.
            critic_verdict:    Critic verdict string.
            mode:              Trading mode for per-mode checks.
            symbol:            Trading symbol (for logging).
            confidence_score:  Original confidence score before modulation.
            hard_gate_blocked: Whether a HARD_BLOCK is in effect.
            critic_adjustment: Confidence adjustment factor from critic (0-1).

        Returns:
            ModulatedGateConfig with should_block, confidence_multiplier,
            reason, and detail fields.

        Raises:
            ValueError: If critic_verdict is not a known verdict.
        """
        if critic_verdict not in VALID_VERDICTS:
            raise ValueError(
                f"Unknown critic_verdict '{critic_verdict}'. "
                f"Valid: {sorted(VALID_VERDICTS)}"
            )

        # Rule 1: HARD_BLOCK wins regardless of critic
        if hard_gate_blocked:
            entry = ModulationEntry(
                timestamp=_now_iso(),
                mode=mode,
                symbol=symbol,
                critic_verdict=critic_verdict,
                original_confidence=confidence_score,
                adjusted_confidence=confidence_score,
                modulation_factor=1.0,
                hard_gate_blocked=True,
                is_enacted=True,
                detail="HARD_BLOCK in effect — critic not consulted.",
            )
            self._log(entry)
            return ModulatedGateConfig(
                should_block=True,
                confidence_multiplier=1.0,
                reason="hard_block_active",
                detail="Hard gate block active; critic not consulted.",
                is_advisory=True,
                hard_gate_blocked=True,
                critic_verdict=critic_verdict,
            )

        # Per-mode activation check
        if mode not in self._active_modes:
            entry = ModulationEntry(
                timestamp=_now_iso(),
                mode=mode,
                symbol=symbol,
                critic_verdict=critic_verdict,
                original_confidence=confidence_score,
                adjusted_confidence=confidence_score,
                modulation_factor=1.0,
                hard_gate_blocked=False,
                is_enacted=False,
                detail=f"Mode {mode} not active for critic influence.",
            )
            self._log(entry)
            return ModulatedGateConfig(
                should_block=False,
                confidence_multiplier=1.0,
                reason=f"mode_not_active: {mode}",
                detail=f"Mode {mode} not in active set {sorted(self._active_modes)}.",
                is_advisory=True,
                hard_gate_blocked=False,
                critic_verdict=critic_verdict,
            )

        # Translate verdict
        if critic_verdict == "ALLOW":
            return self._modulate_allow(mode, symbol, confidence_score)
        elif critic_verdict == "DOWNWEIGHT_CONFIDENCE":
            return self._modulate_downweight(
                mode, symbol, confidence_score, critic_adjustment,
            )
        elif critic_verdict == "VETO_TO_NO_TRADE":
            return self._modulate_veto(mode, symbol, confidence_score)
        elif critic_verdict == "REQUIRE_REVIEW":
            return self._modulate_review(mode, symbol, confidence_score)
        else:  # NOT_EVALUATED
            return self._modulate_not_evaluated(mode, symbol, confidence_score)

    def get_modulation_summary(self) -> dict[str, Any]:
        """Return a summary of all modulation events."""
        if not self._modulation_log:
            return {
                "total_modulations": 0,
                "by_verdict": {},
                "by_mode": {},
                "veto_count": 0,
                "downweight_count": 0,
                "hard_block_skipped": 0,
            }

        by_verdict: dict[str, int] = {}
        by_mode: dict[str, int] = {}
        veto_count = 0
        dw_count = 0
        hb_count = 0

        for entry in self._modulation_log:
            by_verdict[entry.critic_verdict] = by_verdict.get(entry.critic_verdict, 0) + 1
            by_mode[entry.mode] = by_mode.get(entry.mode, 0) + 1
            if entry.critic_verdict == "VETO_TO_NO_TRADE":
                veto_count += 1
            if entry.critic_verdict == "DOWNWEIGHT_CONFIDENCE":
                dw_count += 1
            if entry.hard_gate_blocked:
                hb_count += 1

        return {
            "total_modulations": len(self._modulation_log),
            "by_verdict": by_verdict,
            "by_mode": by_mode,
            "veto_count": veto_count,
            "downweight_count": dw_count,
            "hard_block_skipped": hb_count,
        }

    # ------------------------------------------------------------------
    # Verdict-specific modulation rules
    # ------------------------------------------------------------------

    def _modulate_allow(
        self,
        mode: str,
        symbol: str,
        confidence_score: float,
    ) -> ModulatedGateConfig:
        entry = ModulationEntry(
            timestamp=_now_iso(),
            mode=mode,
            symbol=symbol,
            critic_verdict="ALLOW",
            original_confidence=confidence_score,
            adjusted_confidence=confidence_score,
            modulation_factor=1.0,
            hard_gate_blocked=False,
            is_enacted=False,
            detail="Critic ALLOW — no modulation applied.",
        )
        self._log(entry)
        return ModulatedGateConfig(
            should_block=False,
            confidence_multiplier=1.0,
            reason="critic_allow",
            detail="Critic ALLOW — execution proceeds unchanged.",
            is_advisory=True,
            critic_verdict="ALLOW",
        )

    def _modulate_downweight(
        self,
        mode: str,
        symbol: str,
        confidence_score: float,
        critic_adjustment: float,
    ) -> ModulatedGateConfig:
        # Clamp adjustment per-mode threshold
        min_mult = self._dw_thresholds.get(mode, 0.0)
        multiplier = max(min_mult, min(1.0, critic_adjustment))
        adjusted = confidence_score * multiplier

        entry = ModulationEntry(
            timestamp=_now_iso(),
            mode=mode,
            symbol=symbol,
            critic_verdict="DOWNWEIGHT_CONFIDENCE",
            original_confidence=confidence_score,
            adjusted_confidence=round(adjusted, 6),
            modulation_factor=multiplier,
            hard_gate_blocked=False,
            is_enacted=False,
            detail=f"Confidence adjusted: {confidence_score} -> {adjusted:.4f} "
                   f"(x{multiplier}).",
        )
        self._log(entry)
        return ModulatedGateConfig(
            should_block=False,
            confidence_multiplier=multiplier,
            reason="critic_downweight_confidence",
            detail=f"Critic DOWNWEIGHT_CONFIDENCE: multiplier={multiplier}.",
            is_advisory=True,
            critic_verdict="DOWNWEIGHT_CONFIDENCE",
        )

    def _modulate_veto(
        self,
        mode: str,
        symbol: str,
        confidence_score: float,
    ) -> ModulatedGateConfig:
        entry = ModulationEntry(
            timestamp=_now_iso(),
            mode=mode,
            symbol=symbol,
            critic_verdict="VETO_TO_NO_TRADE",
            original_confidence=confidence_score,
            adjusted_confidence=0.0,
            modulation_factor=0.0,
            hard_gate_blocked=False,
            is_enacted=False,
            detail=f"VETO_TO_NO_TRADE — policy may set action to NO_TRADE.",
        )
        self._log(entry)
        return ModulatedGateConfig(
            should_block=True,
            confidence_multiplier=0.0,
            reason="critic_veto_to_no_trade",
            detail="Critic VETO_TO_NO_TRADE — policy should block this action.",
            is_advisory=True,
            critic_verdict="VETO_TO_NO_TRADE",
        )

    def _modulate_review(
        self,
        mode: str,
        symbol: str,
        confidence_score: float,
    ) -> ModulatedGateConfig:
        entry = ModulationEntry(
            timestamp=_now_iso(),
            mode=mode,
            symbol=symbol,
            critic_verdict="REQUIRE_REVIEW",
            original_confidence=confidence_score,
            adjusted_confidence=confidence_score,
            modulation_factor=1.0,
            hard_gate_blocked=False,
            is_enacted=False,
            detail="REQUIRE_REVIEW — human attention flagged, no automated action.",
        )
        self._log(entry)
        return ModulatedGateConfig(
            should_block=False,
            confidence_multiplier=1.0,
            reason="critic_require_review",
            detail="Critic REQUIRES_REVIEW — human flagged.",
            is_advisory=True,
            critic_verdict="REQUIRE_REVIEW",
        )

    def _modulate_not_evaluated(
        self,
        mode: str,
        symbol: str,
        confidence_score: float,
    ) -> ModulatedGateConfig:
        entry = ModulationEntry(
            timestamp=_now_iso(),
            mode=mode,
            symbol=symbol,
            critic_verdict="NOT_EVALUATED",
            original_confidence=confidence_score,
            adjusted_confidence=confidence_score,
            modulation_factor=1.0,
            hard_gate_blocked=False,
            is_enacted=False,
            detail="NOT_EVALUATED — critic did not evaluate this decision.",
        )
        self._log(entry)
        return ModulatedGateConfig(
            should_block=False,
            confidence_multiplier=1.0,
            reason="critic_not_evaluated",
            detail="Critic NOT_EVALUATED — no modulation.",
            is_advisory=True,
            critic_verdict="NOT_EVALUATED",
        )

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    def _log(self, entry: ModulationEntry) -> None:
        """Record a modulation entry (in-memory + external if configured)."""
        self._modulation_log.append(entry)
        if self._logger_fn is not None:
            try:
                self._logger_fn(entry)
            except Exception as exc:
                logger.warning(
                    "GuardedInfluenceManager: logger_fn raised %s: %s",
                    type(exc).__name__, exc,
                )

    def __repr__(self) -> str:
        return (
            f"GuardedInfluenceManager(active_modes={sorted(self._active_modes)}, "
            f"modulations={len(self._modulation_log)})"
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
