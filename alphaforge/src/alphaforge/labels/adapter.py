"""LabelAdapter — deterministic SimulationOutput-to-AlphaForgeLabel transformer.

Maps all 15+ fields from SimulationOutput to AlphaForgeLabel format per
contracts/mappings/simulation_to_alphaforge.json and alphaforge/docs/label_contract.md.
Exposes LabelAdapter class with adapt_simulation_output() and classify_no_trade_quality().

Deterministic: same SimulationOutput always produces bit-for-bit identical AlphaForgeLabel.
No network, no exchange API, no xgboost, no Binance. Stdlib-only + existing alphaforge modules.
"""

from __future__ import annotations

import copy
import enum
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LABEL_INTERPRETATION_VERSION: str = "1.0.0"
# FUNDING_STATUS_DEFAULT removed in #315 — truthful funding status
# is now propagated from simulation lineage.  If lineage has no funding
# status, MISSING_DATA is used (backward-compatible truthful default).

VALID_MODES: Tuple[str, ...] = ("SWING", "SCALP", "AGGRESSIVE_SCALP")
VALID_BEST_ACTIONS: Tuple[str, ...] = ("LONG_NOW", "SHORT_NOW", "NO_TRADE", "AMBIGUOUS_STATE")

# NO_TRADE quality classifier thresholds
NO_TRADE_THRESHOLD_CORRECT: float = 0.3
NO_TRADE_THRESHOLD_SIGNIFICANT: float = 0.5
NO_TRADE_AMBIGUITY_MARGIN: float = 0.2

# label_validity values
LABEL_VALIDITY_VALID: str = "valid"
LABEL_VALIDITY_INVALID: str = "invalid"
LABEL_VALIDITY_AMBIGUOUS_EXCLUDED: str = "ambiguous_excluded"

# Cost-consumed-edge tolerance (R units)
COST_NET_TOLERANCE: float = 0.0001

# Truthful default when lineage has no funding information
TRUTHFUL_FUNDING_STATUS_DEFAULT: str = "MISSING_DATA"


class NoTradeQuality(str, enum.Enum):
    """NO_TRADE quality classification categories."""
    CORRECT_NO_TRADE = "CORRECT_NO_TRADE"
    SAVED_LOSS = "SAVED_LOSS"
    MISSED_OPPORTUNITY = "MISSED_OPPORTUNITY"
    AMBIGUOUS_NO_TRADE = "AMBIGUOUS_NO_TRADE"


class LabelValidity(str, enum.Enum):
    """Label validity for training inclusion/exclusion."""
    VALID = "valid"
    INVALID = "invalid"
    AMBIGUOUS_EXCLUDED = "ambiguous_excluded"


# ---------------------------------------------------------------------------
# Required SimulationOutput top-level fields (from schema)
# ---------------------------------------------------------------------------

_REQUIRED_SIM_FIELDS: Tuple[str, ...] = (
    "simulation_run_id",
    "symbol",
    "decision_timestamp",
    "mode",
    "resolution_status",
    "long_outcome",
    "short_outcome",
    "no_trade_outcome",
    "best_action",
    "action_gap_r",
    "regret_r",
    "is_ambiguous",
    "lineage",
)


# ---------------------------------------------------------------------------
# LabelAdapter
# ---------------------------------------------------------------------------

class LabelAdapter:
    """Deterministic adapter from SimulationOutput to AlphaForgeLabel.

    Public methods:
        adapt_simulation_output(sim_output: dict) -> dict
        classify_no_trade_quality(no_trade_outcome: dict) -> str
    """

    def __init__(self, label_interpretation_version: str = LABEL_INTERPRETATION_VERSION):
        self._label_interpretation_version = label_interpretation_version
        self._warnings: List[str] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def adapt_simulation_output(self, sim_output: dict) -> dict:
        """Transform a SimulationOutput dict into an AlphaForgeLabel dict.

        Args:
            sim_output: SimulationOutput record as a dict (per simulation_output.schema.json).

        Returns:
            AlphaForgeLabel-compatible dict with all required fields populated.

        Raises:
            ValueError: If sim_output is missing required top-level fields or has invalid field values.
        """
        # Reset warnings accumulator
        self._warnings = []

        # Validate required fields
        self._validate_sim_output(sim_output)

        # Deep-copy input to avoid mutation
        sim = copy.deepcopy(sim_output)

        # Extract sub-structs
        long_out = sim["long_outcome"]
        short_out = sim["short_outcome"]
        no_trade_out = sim["no_trade_outcome"]
        lineage = sim.get("lineage", {})

        # --- Basic identifiers ---
        symbol: str = sim["symbol"]
        timestamp: str = sim["decision_timestamp"]
        mode: str = sim["mode"]
        simulation_run_id: str = sim["simulation_run_id"]

        # --- Resolve best action ---
        best_action: str = sim["best_action"]

        # --- Compute no_trade_quality ---
        no_trade_quality: str = self.classify_no_trade_quality(no_trade_out)

        # --- label_validity derivation ---
        resolution_status: str = sim["resolution_status"]
        is_ambiguous: bool = bool(sim.get("is_ambiguous", False))
        label_validity: str = self._derive_label_validity(resolution_status, is_ambiguous)

        # --- Cost-aware fields ---
        long_R_gross: float = self._get_number(long_out, "realized_r_gross")
        long_R_net: float = self._get_number(long_out, "realized_r_net")
        short_R_gross: float = self._get_number(short_out, "realized_r_gross")
        short_R_net: float = self._get_number(short_out, "realized_r_net")

        fee_cost_r_long: float = self._get_number(long_out, "fee_cost_r")
        slippage_cost_r_long: float = self._get_number(long_out, "slippage_cost_r")
        total_cost_r_long: float = self._get_number(long_out, "total_cost_r")

        fee_cost_r_short: float = self._get_number(short_out, "fee_cost_r")
        slippage_cost_r_short: float = self._get_number(short_out, "slippage_cost_r")
        total_cost_r_short: float = self._get_number(short_out, "total_cost_r")

        # --- Path metrics ---
        long_mfe_R: float = self._get_nested_number(long_out, "path_metrics", "mfe_r")
        short_mfe_R: float = self._get_nested_number(short_out, "path_metrics", "mfe_r")
        long_mae_R: float = self._get_nested_number(long_out, "path_metrics", "mae_r")
        short_mae_R: float = self._get_nested_number(short_out, "path_metrics", "mae_r")
        path_quality_score: float = self._get_nested_number(long_out, "path_metrics", "path_quality_score")

        # --- NO_TRADE scores ---
        saved_loss_score: float = self._get_number(no_trade_out, "saved_loss_score", 0.0)
        missed_opportunity_score: float = self._get_number(no_trade_out, "missed_opportunity_score", 0.0)
        saved_loss_r: float = self._get_number(no_trade_out, "saved_loss_r", 0.0)
        missed_opportunity_r: float = self._get_number(no_trade_out, "missed_opportunity_r", 0.0)
        was_correct_skip: bool = bool(no_trade_out.get("was_correct_skip", False))

        # --- Action gap / regret ---
        action_gap_R: float = self._get_number(sim, "action_gap_r", 0.0)
        regret_R: float = self._get_number(sim, "regret_r", 0.0)

        # --- Lineage propagation ---
        simulation_family_version: str = lineage.get("simulation_family_version", "unknown")
        simulation_profile_id: str = lineage.get("simulation_profile_version", "unknown")
        simulation_engine_version: str = lineage.get("simulation_engine_version", "unknown")
        cost_model_version: str = lineage.get("cost_model_version", "unknown")

        # --- Cost-consumed-edge detection ---
        cost_edge_warning: bool = self._detect_cost_consumed_edge(
            long_R_gross, long_R_net, short_R_gross, short_R_net
        )

        # --- Best action after cost ---
        best_action_after_cost: str = self._compute_best_action_after_cost(
            best_action, long_R_gross, long_R_net, short_R_gross, short_R_net
        )

        # --- Exit reason ---
        exit_reason: Optional[str] = long_out.get("exit_reason")

        # --- Cost impact aliases for downstream compatibility ---
        cost_impact_long: float = total_cost_r_long
        cost_impact_short: float = total_cost_r_short

        # ── Truthful funding status from lineage ──────────────────────
        # Priority: long_outcome.funding_status → lineage.funding_status → MISSING_DATA
        funding_status: str = self._resolve_funding_status(long_out, lineage)

        # Additional funding lineage fields
        funding_event_count: int = self._get_int(long_out, "funding_event_count", 0)
        funding_source: str = str(long_out.get("funding_source", lineage.get("funding_source", "")))
        funding_model_version: str = lineage.get("funding_model_version", "unknown")
        funding_window_start_ms: int = self._get_int(lineage, "funding_window_start_ms", 0)
        funding_window_end_ms: int = self._get_int(lineage, "funding_window_end_ms", 0)

        # Assemble label dict
        label: Dict[str, Any] = {
            "symbol": symbol,
            "timestamp": timestamp,
            "mode": mode,
            "simulation_family_version": simulation_family_version,
            "label_interpretation_version": self._label_interpretation_version,
            "simulation_profile_id": simulation_profile_id,
            "simulation_engine_version": simulation_engine_version,
            "cost_model_version": cost_model_version,
            "long_R_gross": long_R_gross,
            "long_R_net": long_R_net,
            "short_R_gross": short_R_gross,
            "short_R_net": short_R_net,
            "fee_cost_r_long": fee_cost_r_long,
            "slippage_cost_r_long": slippage_cost_r_long,
            "total_cost_r_long": total_cost_r_long,
            "fee_cost_r_short": fee_cost_r_short,
            "slippage_cost_r_short": slippage_cost_r_short,
            "total_cost_r_short": total_cost_r_short,
            "best_action_label": best_action,
            "label_validity": label_validity,
            "resolution_status": resolution_status,
            "exit_reason": exit_reason,
            "no_trade_quality": no_trade_quality,
            "saved_loss_r": saved_loss_r,
            "saved_loss_score": saved_loss_score,
            "missed_opportunity_r": missed_opportunity_r,
            "missed_opportunity_score": missed_opportunity_score,
            "was_correct_skip": was_correct_skip,
            "best_action_after_cost": best_action_after_cost,
            "action_gap_R": action_gap_R,
            "regret_R": regret_R,
            "is_ambiguous": is_ambiguous,
            "long_mae_R": long_mae_R,
            "short_mae_R": short_mae_R,
            "long_mfe_R": long_mfe_R,
            "short_mfe_R": short_mfe_R,
            "path_quality_score": path_quality_score,
            "funding_status": funding_status,
            "funding_event_count": funding_event_count,
            "funding_source": funding_source,
            "funding_model_version": funding_model_version,
            "funding_window_start_ms": funding_window_start_ms,
            "funding_window_end_ms": funding_window_end_ms,
            "cost_edge_warning": cost_edge_warning,
            "cost_impact_long": cost_impact_long,
            "cost_impact_short": cost_impact_short,
        }

        return label

    def classify_no_trade_quality(self, no_trade_outcome: dict) -> str:
        """Classify NO_TRADE outcome quality from NoTradeOutcome fields.

        Decision rules (deterministic, no randomness, no external state):
          1. CORRECT_NO_TRADE: was_correct_skip is True AND both
             saved_loss_score < 0.3 AND missed_opportunity_score < 0.3.
          2. SAVED_LOSS: saved_loss_score >= 0.5 AND
             saved_loss_score > missed_opportunity_score.
          3. MISSED_OPPORTUNITY: missed_opportunity_score >= 0.5 AND
             missed_opportunity_score > saved_loss_score.
          4. AMBIGUOUS_NO_TRADE: catch-all for all remaining cases, including
             scores within ambiguity margin (|diff| < 0.2 and both < 0.5).

        Args:
            no_trade_outcome: NoTradeOutcome dict from SimulationOutput.

        Returns:
            One of: CORRECT_NO_TRADE, SAVED_LOSS, MISSED_OPPORTUNITY, AMBIGUOUS_NO_TRADE.
        """
        was_correct_skip: bool = bool(no_trade_outcome.get("was_correct_skip", False))
        saved_loss_score: float = float(no_trade_outcome.get("saved_loss_score", 0.0))
        missed_opportunity_score: float = float(no_trade_outcome.get("missed_opportunity_score", 0.0))

        # Rule 1: CORRECT_NO_TRADE
        if (
            was_correct_skip
            and saved_loss_score < NO_TRADE_THRESHOLD_CORRECT
            and missed_opportunity_score < NO_TRADE_THRESHOLD_CORRECT
        ):
            return NoTradeQuality.CORRECT_NO_TRADE.value

        # Rule 2: SAVED_LOSS
        if (
            saved_loss_score >= NO_TRADE_THRESHOLD_SIGNIFICANT
            and saved_loss_score > missed_opportunity_score
        ):
            return NoTradeQuality.SAVED_LOSS.value

        # Rule 3: MISSED_OPPORTUNITY
        if (
            missed_opportunity_score >= NO_TRADE_THRESHOLD_SIGNIFICANT
            and missed_opportunity_score > saved_loss_score
        ):
            return NoTradeQuality.MISSED_OPPORTUNITY.value

        # Rule 4: AMBIGUOUS_NO_TRADE (catch-all)
        return NoTradeQuality.AMBIGUOUS_NO_TRADE.value

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _validate_sim_output(self, sim_output: dict) -> None:
        """Validate that sim_output has all required top-level fields and valid values.

        Raises:
            ValueError: If a required field is missing or has an invalid value.
        """
        if not isinstance(sim_output, dict):
            raise ValueError(
                f"sim_output must be a dict, got {type(sim_output).__name__}"
            )

        # Check required fields
        missing: List[str] = []
        for field in _REQUIRED_SIM_FIELDS:
            if field not in sim_output:
                missing.append(field)

        if missing:
            raise ValueError(
                f"SimulationOutput missing required fields: {missing}"
            )

        # Validate mode
        mode = sim_output.get("mode")
        if mode not in VALID_MODES:
            raise ValueError(
                f"Invalid mode '{mode}'. Must be one of {VALID_MODES}"
            )

        # Validate best_action
        best_action = sim_output.get("best_action")
        if best_action not in VALID_BEST_ACTIONS:
            raise ValueError(
                f"Invalid best_action '{best_action}'. Must be one of {VALID_BEST_ACTIONS}"
            )

        # Validate resolution_status
        resolution_status = sim_output.get("resolution_status")
        if resolution_status not in ("COMPLETE", "UNRESOLVED", "INVALIDATED"):
            raise ValueError(
                f"Invalid resolution_status '{resolution_status}'. "
                f"Must be COMPLETE, UNRESOLVED, or INVALIDATED"
            )

        # Validate sub-structs are dicts
        for sub in ("long_outcome", "short_outcome", "no_trade_outcome", "lineage"):
            val = sim_output.get(sub)
            if val is not None and not isinstance(val, dict):
                raise ValueError(f"'{sub}' must be a dict, got {type(val).__name__}")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_funding_status(long_out: dict, lineage: dict) -> str:
        """Resolve truthful funding status from available sources.

        Priority:
          1. ``long_outcome.funding_status`` (engine-level, most truthful)
          2. ``lineage.funding_status`` (propagated lineage)
          3. ``TRUTHFUL_FUNDING_STATUS_DEFAULT`` (MISSING_DATA) as fallback
        """
        # Check action outcome first (engine source of truth)
        outcome_status = long_out.get("funding_status")
        if outcome_status and isinstance(outcome_status, str) and outcome_status.strip():
            return outcome_status.strip()

        # Check lineage next
        lineage_status = lineage.get("funding_status")
        if lineage_status and isinstance(lineage_status, str) and lineage_status.strip():
            return lineage_status.strip()

        return TRUTHFUL_FUNDING_STATUS_DEFAULT

    @staticmethod
    def _get_number(obj: dict, key: str, default: float = 0.0) -> float:
        """Safely extract a numeric field from a dict with a default."""
        val = obj.get(key, default)
        if val is None:
            return default
        return float(val)

    @staticmethod
    def _get_int(obj: dict, key: str, default: int = 0) -> int:
        """Safely extract an integer field from a dict with a default."""
        val = obj.get(key, default)
        if val is None:
            return default
        return int(val)

    @staticmethod
    def _get_nested_number(obj: dict, sub_key: str, field: str, default: float = 0.0) -> float:
        """Safely extract a nested numeric field (obj.sub.field) with a default."""
        sub = obj.get(sub_key)
        if not isinstance(sub, dict):
            return default
        val = sub.get(field, default)
        if val is None:
            return default
        return float(val)

    @staticmethod
    def _derive_label_validity(resolution_status: str, is_ambiguous: bool) -> str:
        """Derive label_validity from resolution_status and is_ambiguous.

        Rules:
            COMPLETE + not ambiguous  → "valid"
            COMPLETE + ambiguous      → "ambiguous_excluded"
            UNRESOLVED                → "invalid"
            INVALIDATED               → "invalid"

        Args:
            resolution_status: One of COMPLETE, UNRESOLVED, INVALIDATED.
            is_ambiguous: Whether the best action is ambiguous.

        Returns:
            One of: valid, invalid, ambiguous_excluded.
        """
        if resolution_status in ("UNRESOLVED", "INVALIDATED"):
            return LABEL_VALIDITY_INVALID
        if is_ambiguous:
            return LABEL_VALIDITY_AMBIGUOUS_EXCLUDED
        return LABEL_VALIDITY_VALID

    @staticmethod
    def _detect_cost_consumed_edge(
        long_R_gross: float,
        long_R_net: float,
        short_R_gross: float,
        short_R_net: float,
    ) -> bool:
        """Return True if gross edge exists but net is consumed by costs.

        Cost-consumed-edge: gross > 0 but net < 0 (for either side).

        Args:
            long_R_gross, long_R_net, short_R_gross, short_R_net: R values.

        Returns:
            True if cost-consumed-edge detected on either side.
        """
        if long_R_gross > 0 and long_R_net < 0:
            return True
        if short_R_gross > 0 and short_R_net < 0:
            return True
        return False

    @staticmethod
    def _compute_best_action_after_cost(
        best_action: str,
        long_R_gross: float,
        long_R_net: float,
        short_R_gross: float,
        short_R_net: float,
    ) -> str:
        """Compute best action after applying full cost model.

        If costs consume the edge (gross > 0 but net <= 0 for both sides),
        the best action becomes NO_TRADE.

        Args:
            best_action: Original best_action from simulation.
            long_R_gross, long_R_net, short_R_gross, short_R_net: R values.

        Returns:
            Best action after cost (LONG_NOW, SHORT_NOW, NO_TRADE, AMBIGUOUS_STATE).
        """
        # If best action is LONG_NOW but net is consumed, fallback to NO_TRADE
        if best_action == "LONG_NOW" and long_R_gross > 0 and long_R_net <= 0:
            return "NO_TRADE"
        # If best action is SHORT_NOW but net is consumed, fallback to NO_TRADE
        if best_action == "SHORT_NOW" and short_R_gross > 0 and short_R_net <= 0:
            return "NO_TRADE"
        return best_action

    @property
    def warnings(self) -> List[str]:
        """Return accumulated warnings from the last adapt_simulation_output call."""
        return list(self._warnings)


# ---------------------------------------------------------------------------
# Top-level convenience functions
# ---------------------------------------------------------------------------

_DEFAULT_ADAPTER: Optional[LabelAdapter] = None


def _get_adapter() -> LabelAdapter:
    """Return or create the module-level LabelAdapter singleton."""
    global _DEFAULT_ADAPTER
    if _DEFAULT_ADAPTER is None:
        _DEFAULT_ADAPTER = LabelAdapter()
    return _DEFAULT_ADAPTER


def adapt_simulation_output(sim_output: dict) -> dict:
    """Transform a SimulationOutput dict into an AlphaForgeLabel dict.

    Convenience wrapper around LabelAdapter.adapt_simulation_output.

    Args:
        sim_output: SimulationOutput record as a dict.

    Returns:
        AlphaForgeLabel-compatible dict.
    """
    return _get_adapter().adapt_simulation_output(sim_output)


def classify_no_trade_quality(no_trade_outcome: dict) -> str:
    """Classify NO_TRADE outcome quality.

    Convenience wrapper around LabelAdapter.classify_no_trade_quality.

    Args:
        no_trade_outcome: NoTradeOutcome dict from SimulationOutput.

    Returns:
        One of: CORRECT_NO_TRADE, SAVED_LOSS, MISSED_OPPORTUNITY, AMBIGUOUS_NO_TRADE.
    """
    return _get_adapter().classify_no_trade_quality(no_trade_outcome)
