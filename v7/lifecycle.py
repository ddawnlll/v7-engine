"""
V7 DecisionEvent & TradeOutcome lifecycle management.

DecisionEvent lifecycle:  create -> persist -> update -> close
TradeOutcome lifecycle:   create -> update -> resolve

DecisionEvent sections (v7/docs/contracts/decision_event.md):
  contract, identity, lineage, scope, request_summary, decision_summary,
  runtime_interpretation, execution_linkage, outcome_linkage, observability

TradeOutcome sections (v7/docs/contracts/trade_outcome.md):
  contract, identity, lineage, execution_summary, resolution_status,
  realized_outcome, path_metrics, comparative_outcome,
  quality_and_interpretation, observability

TradeOutcome status transitions:
  PENDING -> RESOLVED | PARTIALLY_RESOLVED | INVALIDATED | UNAVAILABLE
  PARTIALLY_RESOLVED -> RESOLVED | INVALIDATED
  RESOLVED / INVALIDATED / UNAVAILABLE = terminal
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

# ---- Schema versions (single source of truth) ----
EVENT_SCHEMA_VERSION = "decision-event-1.0.0"
CONTRACT_VERSION = "v7-1.0.0"
RESPONSE_SCHEMA_VERSION = "result-1.0.0"
OUTCOME_SCHEMA_VERSION = "trade-outcome-1.0.0"

# ---- Enum sets ----
EVENT_TYPES = frozenset(
    {
        "ORDER_PLACED",
        "ORDER_FILLED",
        "ORDER_REJECTED",
        "POSITION_OPENED",
        "POSITION_CLOSED",
        "ERROR",
    }
)

EVENT_STATUSES = frozenset({"SUCCESS", "PARTIAL", "FAILED", "PENDING"})

OUTCOME_STATUSES = frozenset(
    {
        "PENDING",
        "RESOLVED",
        "PARTIALLY_RESOLVED",
        "INVALIDATED",
        "UNAVAILABLE",
    }
)

OUTCOME_SOURCES = frozenset(
    {
        "LIVE_EXECUTION",
        "PAPER_EXECUTION",
        "REPLAY_PROJECTION",
        "OFFLINE_LABELING",
        "SKIP_EVAL",
    }
)

EXECUTION_PATHS = frozenset(
    {
        "NOT_EXECUTED",
        "PAPER_EXECUTED",
        "LIVE_EXECUTED",
        "REPLAY_ONLY",
        "SKIPPED_BY_RUNTIME",
        "BLOCKED_BY_RUNTIME",
    }
)

EXECUTION_DECISIONS = frozenset(
    {
        "EXECUTED",
        "SKIPPED",
        "BLOCKED",
        "NOT_APPLICABLE",
    }
)

RESOLUTION_REASONS = frozenset(
    {
        "HORIZON_COMPLETE",
        "TRADE_CLOSED",
        "STOP_HIT",
        "TARGET_HIT",
        "TIME_EXIT",
        "SKIP_EVAL_COMPLETE",
        "DATA_INCOMPLETE",
        "EXECUTION_INCOMPLETE",
    }
)

REQUEST_KINDS = frozenset(
    {"live_scan", "paper_scan", "replay_eval", "shadow", "validation"}
)

SIGNAL_STATUSES = frozenset(
    {"SIGNAL", "NO_TRADE", "FILTERED", "DEGRADED", "ERROR"}
)

DECISION_STATUSES = frozenset(
    {"VALID", "LOW_CONFIDENCE", "BLOCKED", "DEGRADED", "FAILED"}
)

# ---- Outcome status transition rules ----
_OUTCOME_TRANSITIONS: dict[str, set[str]] = {
    "PENDING": {"RESOLVED", "PARTIALLY_RESOLVED", "INVALIDATED", "UNAVAILABLE"},
    "PARTIALLY_RESOLVED": {"RESOLVED", "INVALIDATED"},
    "RESOLVED": set(),
    "INVALIDATED": set(),
    "UNAVAILABLE": set(),
}

# Resolution reasons that indicate a terminal/final state
_TERMINAL_REASONS = frozenset(
    {
        "HORIZON_COMPLETE",
        "TRADE_CLOSED",
        "STOP_HIT",
        "TARGET_HIT",
        "TIME_EXIT",
        "SKIP_EVAL_COMPLETE",
    }
)

_NON_TERMINAL_REASONS = frozenset(
    {
        "DATA_INCOMPLETE",
        "EXECUTION_INCOMPLETE",
    }
)

# A DecisionEvent's event_type implies order for execution progression
_EVENT_TYPE_PROGRESSION = [
    "ORDER_PLACED",
    "ORDER_FILLED",
    "PARTIAL_FILL",
    "ORDER_REJECTED",
    "POSITION_OPENED",
    "POSITION_CLOSED",
    "ERROR",
]


# ---- Custom errors ----
class LifecycleError(Exception):
    """Base error for lifecycle operations."""


class InvalidTransitionError(LifecycleError):
    """Raised when an outcome status transition is not allowed."""


class ValidationError(LifecycleError):
    """Raised when input data fails validation."""


# ---- Helpers ----
def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _gen_id(prefix: str = "evt") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _clean_empty_meta(d: dict[str, Any]) -> dict[str, Any]:
    """Remove optional_extended_metadata if it is empty.

    Preserves all other fields including explicit None values, which are
    semantically meaningful in the contract (e.g. trade_outcome_id: null
    means 'not yet linked').
    """
    if (
        "optional_extended_metadata" in d
        and d["optional_extended_metadata"] == {}
    ):
        del d["optional_extended_metadata"]
    return d


def _validate_enum(value: str, valid: frozenset, label: str) -> None:
    """Validate a string value belongs to a known enum set."""
    if value not in valid:
        raise ValidationError(
            f"Invalid {label} '{value}'. Must be one of {sorted(valid)}"
        )


def _derive_analysis_mode(request_kind: str) -> str:
    """Map request_kind to analysis_mode."""
    mapping = {
        "live_scan": "live",
        "paper_scan": "paper",
        "replay_eval": "replay",
        "shadow": "shadow",
        "validation": "validation",
    }
    return mapping.get(request_kind, "unknown")


def _derive_runtime_actionability(
    result_status: dict[str, Any],
    result_fallback: dict[str, Any],
) -> str:
    """Determine runtime actionability from result status and fallback."""
    if result_fallback.get("fallback_used", False):
        return "DEGRADED"
    if result_status.get("is_actionable", False):
        return "ACTIONABLE"
    return "NOT_ACTIONABLE"


def _derive_execution_path(venue: str) -> str:
    """Map venue to execution_path."""
    if venue in ("binance_futures", "binance_spot", "bybit_futures"):
        return "LIVE_EXECUTED"
    if venue in ("paper_trading", "paper"):
        return "PAPER_EXECUTED"
    if venue in ("replay", "historical"):
        return "REPLAY_ONLY"
    return "NOT_EXECUTED"


def _derive_execution_decision(
    result_status: dict[str, Any],
    result_fallback: dict[str, Any],
) -> str:
    """Determine execution decision from result status."""
    if result_fallback.get("fallback_used", False):
        return "BLOCKED"
    if result_status.get("is_actionable", False):
        return "EXECUTED"
    return "SKIPPED"


def _derive_timing_tags(
    exec_guidance: dict[str, Any],
) -> list[str]:
    """Derive timing review tags from execution guidance."""
    tags: list[str] = []
    readiness = exec_guidance.get("entry_readiness", "")
    if readiness == "READY_NOW":
        tags.append("ready_now")
    elif readiness == "WAIT":
        tags.append("wait_preferred")
    elif readiness == "CHASING":
        tags.append("chasing_entry")
    elif readiness == "EXPIRING":
        tags.append("expiring_setup")
    elif readiness == "MISSED":
        tags.append("missed_setup")
    return tags


# =========================================================================
# DecisionEventManager
# =========================================================================


class DecisionEventManager:
    """Manages DecisionEvent lifecycle: create -> update -> close.

    Produces full nested DecisionEvent dicts matching the contract spec at
    v7/docs/contracts/decision_event.md.
    """

    def __init__(self) -> None:
        self._store: dict[str, dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # CREATE
    # ------------------------------------------------------------------

    def create(
        self,
        analysis_result: dict[str, Any],
        *,
        venue: str = "paper_trading",
        decision_event_id: str | None = None,
        event_type: str = "ORDER_PLACED",
        status: str = "SUCCESS",
        order_id: str | None = None,
        position_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a full nested DecisionEvent from an AnalysisResult.

        Args:
            analysis_result: V7 AnalysisResult dict (nested contract shape).
            venue: Execution venue identifier.
            decision_event_id: Override auto-generated event ID.
            event_type: ORDER_PLACED, ORDER_FILLED, ORDER_REJECTED,
                        POSITION_OPENED, POSITION_CLOSED, or ERROR.
            status: SUCCESS, PARTIAL, FAILED, or PENDING.
            order_id: Optional exchange/broker order ID.
            position_id: Optional exchange/broker position ID.
            metadata: Optional arbitrary metadata dict.

        Returns:
            Full nested DecisionEvent dict.

        Raises:
            ValidationError: If event_type or status is invalid.
        """
        self._validate_create_input(analysis_result, event_type, status)

        ri = analysis_result.get("identity", {})
        rc = analysis_result.get("contract", {})
        rs = analysis_result.get("status", {})
        rd = analysis_result.get("decision", {})
        rsc = analysis_result.get("scores", {})
        reg = analysis_result.get("execution_guidance", {})
        ruq = analysis_result.get("uncertainty_and_quality", {})
        rfb = analysis_result.get("fallback_and_degradation", {})
        rob = analysis_result.get("observability", {})
        rl = analysis_result.get("lineage", {})
        rrl = analysis_result.get("request_link", {})

        request_id = ri.get("request_id", "unknown")
        ts_utc = ri.get("timestamp_utc", _utc_now())
        engine_name = ri.get("engine_name", "v7")
        engine_version = ri.get("engine_version", "0.0.0")
        model_scope = ri.get("model_scope", "swing_v1")
        trade_mode = ri.get("trade_mode", "SWING")

        symbol = rrl.get("symbol", "UNKNOWN")
        primary_interval = rrl.get("primary_interval", "unknown")
        request_kind = rrl.get("request_kind_seen", "live_scan")
        request_cv = rrl.get("request_contract_version", CONTRACT_VERSION)

        event_id = decision_event_id or _gen_id("evt")

        event: dict[str, Any] = {
            "contract": {
                "event_schema_version": EVENT_SCHEMA_VERSION,
                "contract_version": CONTRACT_VERSION,
                "request_contract_version": request_cv,
                "response_schema_version": RESPONSE_SCHEMA_VERSION,
                "state_schema_version_seen": rc.get(
                    "state_schema_version"
                ),
                "snapshot_builder_version_seen": rc.get(
                    "snapshot_builder_version"
                ),
            },
            "identity": {
                "decision_event_id": event_id,
                "request_id": request_id,
                "timestamp_utc": ts_utc,
                "run_id": ri.get("run_id"),
                "trace_id": ri.get("trace_id"),
            },
            "lineage": {
                "engine_name": engine_name,
                "engine_version": engine_version,
                "request_kind": request_kind,
                "analysis_batch_id": rl.get("analysis_batch_id"),
                "decision_session_id": rl.get("decision_session_id"),
                "model_scope": model_scope,
                "trade_mode": trade_mode,
                "model_artifact_version": ri.get("model_artifact_version"),
                "artifact_id": ri.get("artifact_id"),
                "calibration_artifact_version": ri.get(
                    "calibration_artifact_version"
                ),
                "calibration_artifact_id": ri.get("calibration_artifact_id"),
                "policy_artifact_version": ri.get("policy_artifact_version"),
            },
            "scope": {
                "symbol": symbol,
                "model_scope": model_scope,
                "trade_mode": trade_mode,
                "primary_interval": primary_interval,
                "analysis_mode": _derive_analysis_mode(request_kind),
                "exchange": None,
                "market_type": None,
            },
            "request_summary": self._build_request_summary(analysis_result, rc, rrl),
            "decision_summary": self._build_decision_summary(rs, rd, rsc, reg, rob),
            "runtime_interpretation": self._build_runtime_interpretation(rs, rfb, rl),
            "execution_linkage": self._build_execution_linkage(
                venue, rs, rfb, event_type, status, order_id, position_id
            ),
            "outcome_linkage": {
                "trade_outcome_id": None,
                "outcome_status": "PENDING",
                "label_status": "NOT_LABELED",
                "outcome_horizon_family": rrl.get(
                    "label_horizon_family"
                ),
                "outcome_ready_timestamp_utc": None,
            },
            "observability": self._build_observability(rob, ruq, reg),
            "optional_extended_metadata": metadata or {},
        }

        event = _clean_empty_meta(event)
        self._store[event_id] = event
        return event

    # ------------------------------------------------------------------
    # GET
    # ------------------------------------------------------------------

    def get(self, event_id: str) -> dict[str, Any] | None:
        """Retrieve a stored DecisionEvent by event_id."""
        return self._store.get(event_id)

    def list_all(self) -> list[dict[str, Any]]:
        """Return all stored DecisionEvents (latest first)."""
        return list(self._store.values())

    # ------------------------------------------------------------------
    # UPDATE
    # ------------------------------------------------------------------

    def update(
        self,
        event_id: str,
        *,
        event_type: str | None = None,
        status: str | None = None,
        order_id: str | None = None,
        position_id: str | None = None,
        trade_outcome_id: str | None = None,
        outcome_status: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Update an existing DecisionEvent with execution progress.

        Modifies execution_linkage, outcome_linkage, and optionally
        observability fields.

        Args:
            event_id: Event to update.
            event_type: New event type (e.g. ORDER_FILLED, POSITION_CLOSED).
            status: New status (SUCCESS, PARTIAL, FAILED).
            order_id: New order identifier.
            position_id: New position identifier.
            trade_outcome_id: Link to created TradeOutcome.
            outcome_status: New outcome linkage status.
            metadata: Additional metadata to merge.

        Returns:
            Updated DecisionEvent dict.

        Raises:
            ValidationError: If event_type or status is invalid.
            KeyError: If event_id not found.
        """
        event = self._require_event(event_id)

        if event_type is not None:
            _validate_enum(event_type, EVENT_TYPES, "event_type")

        if status is not None:
            _validate_enum(status, EVENT_STATUSES, "status")

        el = event.get("execution_linkage", {})
        if event_type is not None:
            el["event_type"] = event_type
        if status is not None:
            el["event_status"] = status
        if order_id is not None:
            el["order_group_id"] = order_id
        if position_id is not None:
            el["position_id"] = position_id
        event["execution_linkage"] = el

        ol = event.get("outcome_linkage", {})
        if trade_outcome_id is not None:
            ol["trade_outcome_id"] = trade_outcome_id
        if outcome_status is not None:
            ol["outcome_status"] = outcome_status
        event["outcome_linkage"] = ol

        if metadata:
            existing_meta = event.get("optional_extended_metadata", {})
            existing_meta.update(metadata)
            event["optional_extended_metadata"] = existing_meta

        self._store[event_id] = event
        return event

    # ------------------------------------------------------------------
    # CLOSE
    # ------------------------------------------------------------------

    def close(
        self,
        event_id: str,
        *,
        final_status: str = "SUCCESS",
        event_type: str = "POSITION_CLOSED",
    ) -> dict[str, Any]:
        """Close a DecisionEvent — marks it as final.

        Sets execution_linkage event_type to POSITION_CLOSED (or user choice)
        and updates outcome_linkage label_status to LABELED_AFTER_CLOSE.

        Args:
            event_id: Event to close.
            final_status: SUCCESS, PARTIAL, or FAILED.
            event_type: Closing event type (default POSITION_CLOSED).

        Returns:
            Finalized DecisionEvent.
        """
        return self.update(
            event_id,
            event_type=event_type,
            status=final_status,
        )

    # ------------------------------------------------------------------
    # DELETE
    # ------------------------------------------------------------------

    def delete(self, event_id: str) -> None:
        """Remove a stored DecisionEvent from the in-memory store."""
        self._store.pop(event_id, None)

    # ------------------------------------------------------------------
    # INTERNALS
    # ------------------------------------------------------------------

    def _require_event(self, event_id: str) -> dict[str, Any]:
        if event_id not in self._store:
            raise KeyError(f"DecisionEvent '{event_id}' not found")
        return dict(self._store[event_id])

    def _validate_create_input(
        self,
        analysis_result: dict[str, Any],
        event_type: str,
        status: str,
    ) -> None:
        _validate_enum(event_type, EVENT_TYPES, "event_type")
        _validate_enum(status, EVENT_STATUSES, "status")

        result_identity = analysis_result.get("identity", {})
        if not result_identity.get("request_id"):
            raise ValidationError(
                "AnalysisResult missing required 'identity.request_id'"
            )

    def _build_request_summary(
        self,
        analysis_result: dict[str, Any],
        result_contract: dict[str, Any],
        result_request_link: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "request_timestamp_utc": result_request_link.get("request_timestamp_utc"),
            "state_timestamp_utc": analysis_result.get("state_timestamp_utc"),
            "state_window_length": analysis_result.get("state_window_length"),
            "state_schema_version_seen": result_contract.get(
                "state_schema_version"
            ),
            "snapshot_builder_version_seen": result_contract.get(
                "snapshot_builder_version"
            ),
            "stale_flag": False,
            "snapshot_validity": "VALID",
            "regime_label": analysis_result.get("regime_label"),
            "paper_or_live_mode": result_request_link.get("request_kind_seen"),
        }

    def _build_decision_summary(
        self,
        result_status: dict[str, Any],
        result_decision: dict[str, Any],
        result_scores: dict[str, Any],
        exec_guidance: dict[str, Any],
        result_observability: dict[str, Any],
    ) -> dict[str, Any]:
        entry_price = exec_guidance.get("entry_price")
        stop_loss = exec_guidance.get("stop_loss")
        take_profit = exec_guidance.get("take_profit")

        return {
            "signal_status": result_status.get("signal_status", "NO_TRADE"),
            "decision_status": result_status.get("decision_status", "FAILED"),
            "is_actionable": result_status.get("is_actionable", False),
            "recommended_action": result_decision.get(
                "recommended_action", "NO_TRADE"
            ),
            "direction": result_decision.get("direction", "NONE"),
            "confidence": result_scores.get("confidence"),
            "confidence_kind": result_scores.get("confidence_kind"),
            "expected_r": result_scores.get("expected_r"),
            "expected_drawdown": result_scores.get("expected_drawdown"),
            "decision_margin": result_scores.get("decision_margin"),
            "long_score": result_scores.get("long_score"),
            "short_score": result_scores.get("short_score"),
            "no_trade_score": result_scores.get("no_trade_score"),
            "reason_summary": result_decision.get("decision_summary"),
            "entry_price_seen": entry_price,
            "stop_loss_seen": stop_loss,
            "take_profit_seen": take_profit,
            "time_sensitivity_seen": exec_guidance.get("time_sensitivity"),
            "entry_readiness_seen": exec_guidance.get("entry_readiness"),
            "entry_valid_for_bars_seen": exec_guidance.get(
                "entry_valid_for_bars"
            ),
        }

    def _build_runtime_interpretation(
        self,
        result_status: dict[str, Any],
        result_fallback: dict[str, Any],
        result_lineage: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "runtime_actionability": _derive_runtime_actionability(
                result_status, result_fallback
            ),
            "deterministic_alignment": "NEUTRAL",
            "deterministic_block": False,
            "fallback_used": result_fallback.get("fallback_used", False),
            "degraded_reason": result_fallback.get("degraded_reason"),
            "runtime_safe_action": result_fallback.get("runtime_safe_action"),
            "policy_passed": True,
            "portfolio_blocked": False,
            "risk_blocked": False,
            "suppression_reason": None,
            "should_persist_as_signal": not result_fallback.get(
                "fallback_used", False
            ),
            "should_surface_to_review": result_status.get(
                "is_actionable", False
            ),
        }

    def _build_execution_linkage(
        self,
        venue: str,
        result_status: dict[str, Any],
        result_fallback: dict[str, Any],
        event_type: str,
        status: str,
        order_id: str | None,
        position_id: str | None,
    ) -> dict[str, Any]:
        return {
            "execution_path": _derive_execution_path(venue),
            "execution_decision": _derive_execution_decision(
                result_status, result_fallback
            ),
            "event_type": event_type,
            "event_status": status,
            "order_group_id": order_id,
            "paper_trade_id": None,
            "position_id": position_id,
            "execution_reference_ids": [],
        }

    def _build_observability(
        self,
        result_observability: dict[str, Any],
        result_uncertainty: dict[str, Any],
        exec_guidance: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "analysis_latency_ms": result_observability.get(
                "analysis_latency_ms"
            ),
            "warnings": result_observability.get("warnings", []),
            "quality_flags": result_uncertainty.get("quality_flags", []),
            "uncertainty_type": result_uncertainty.get("uncertainty_type"),
            "decision_quality": result_uncertainty.get("decision_quality"),
            "regime_transition_risk": 0.0,
            "review_tags": result_observability.get("review_tags", []),
            "payload_references": {},
            "timing_extension_present": bool(
                exec_guidance.get("entry_readiness")
            ),
            "timing_review_tags": _derive_timing_tags(exec_guidance),
        }


# =========================================================================
# TradeOutcomeManager
# =========================================================================


class TradeOutcomeManager:
    """Manages TradeOutcome lifecycle: create -> update -> resolve.

    Produces full nested TradeOutcome dicts matching the contract spec at
    v7/docs/contracts/trade_outcome.md.

    Status transitions:
      PENDING -> RESOLVED | PARTIALLY_RESOLVED | INVALIDATED | UNAVAILABLE
      PARTIALLY_RESOLVED -> RESOLVED | INVALIDATED
    """

    def __init__(self) -> None:
        self._store: dict[str, dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # CREATE
    # ------------------------------------------------------------------

    def create(
        self,
        decision_event: dict[str, Any],
        *,
        trade_outcome_id: str | None = None,
        outcome_source: str = "PAPER_EXECUTION",
        execution_path: str = "PAPER_EXECUTED",
        execution_decision: str = "EXECUTED",
        position_opened: bool = False,
        outcome_status: str = "PENDING",
        resolution_reason: str = "EXECUTION_INCOMPLETE",
        realized_outcome: dict[str, Any] | None = None,
        path_metrics: dict[str, Any] | None = None,
        comparative_outcome: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a TradeOutcome from a DecisionEvent.

        Creates the outcome in PENDING state by default, then allows
        resolution progression via update() / resolve().

        Args:
            decision_event: A DecisionEvent dict (full nested shape).
            trade_outcome_id: Override auto-generated ID.
            outcome_source: Source of outcome truth.
            execution_path: How decision was executed.
            execution_decision: Whether decision was executed.
            position_opened: Whether position was opened.
            outcome_status: Initial outcome status (default PENDING).
            resolution_reason: Why outcome reached its initial state.
            realized_outcome: Optional initial realized outcome data.
            path_metrics: Optional initial path metrics.
            comparative_outcome: Optional initial comparative outcome data.
            metadata: Optional arbitrary metadata.

        Returns:
            Full nested TradeOutcome dict.

        Raises:
            ValidationError: On invalid enum values or missing fields.
        """
        self._validate_create_input(
            decision_event,
            outcome_source,
            execution_path,
            execution_decision,
            outcome_status,
            resolution_reason,
        )

        de_identity = decision_event.get("identity", {})
        de_lineage = decision_event.get("lineage", {})
        de_scope = decision_event.get("scope", {})
        de_decision_summary = decision_event.get("decision_summary", {})
        de_exec_linkage = decision_event.get("execution_linkage", {})

        outcome_id = trade_outcome_id or _gen_id("to")
        ts_utc = _utc_now()

        # Determine is_final from outcome_status
        is_final = outcome_status in ("RESOLVED", "INVALIDATED", "UNAVAILABLE")

        outcome: dict[str, Any] = {
            "contract": {
                "outcome_schema_version": OUTCOME_SCHEMA_VERSION,
                "contract_version": CONTRACT_VERSION,
                "event_schema_version": EVENT_SCHEMA_VERSION,
                "simulation_family_version": None,
                "comparative_family_version": None,
            },
            "identity": {
                "trade_outcome_id": outcome_id,
                "decision_event_id": de_identity.get("decision_event_id"),
                "timestamp_utc": ts_utc,
                "trace_id": de_identity.get("trace_id"),
                "comparison_group_id": de_identity.get("comparison_group_id"),
            },
            "lineage": {
                "request_id": de_identity.get("request_id"),
                "engine_name": de_lineage.get("engine_name", "v7"),
                "engine_version": de_lineage.get("engine_version", "0.0.0"),
                "request_kind": de_lineage.get("request_kind", "live_scan"),
                "outcome_source": outcome_source,
                "analysis_batch_id": de_lineage.get("analysis_batch_id"),
                "decision_session_id": de_lineage.get("decision_session_id"),
                "model_scope": de_lineage.get("model_scope"),
                "trade_mode": de_lineage.get("trade_mode"),
                "model_artifact_version": de_lineage.get(
                    "model_artifact_version"
                ),
                "artifact_id": de_lineage.get("artifact_id"),
                "calibration_artifact_version": de_lineage.get(
                    "calibration_artifact_version"
                ),
                "calibration_artifact_id": de_lineage.get(
                    "calibration_artifact_id"
                ),
                "policy_artifact_version": de_lineage.get(
                    "policy_artifact_version"
                ),
                "cost_model_version": None,
                "fee_model_version": None,
                "slippage_model_version": None,
                "execution_assumption_family": None,
                "simulation_family_id": None,
                "comparative_family_id": None,
            },
            "execution_summary": {
                "execution_path": execution_path,
                "execution_decision": execution_decision,
                "position_opened": position_opened,
                "order_group_id": de_exec_linkage.get("order_group_id"),
                "paper_trade_id": de_exec_linkage.get("paper_trade_id"),
                "position_id": de_exec_linkage.get("position_id"),
                "entry_timestamp_utc": None,
                "exit_timestamp_utc": None,
                "execution_block_reason": None,
            },
            "resolution_status": {
                "outcome_status": outcome_status,
                "is_final": is_final,
                "resolution_reason": resolution_reason,
                "outcome_ready_timestamp_utc": ts_utc if is_final else None,
                "pending_horizon_family": de_decision_summary.get(
                    "outcome_horizon_family"
            )
                if not is_final
                else None,
                "invalidity_reason": (
                    resolution_reason
                    if outcome_status == "INVALIDATED"
                    else None
                ),
            },
            "realized_outcome": self._build_initial_realized_outcome(
                realized_outcome, de_decision_summary
            ),
            "path_metrics": self._build_initial_path_metrics(path_metrics),
            "comparative_outcome": self._build_initial_comparative_outcome(
                comparative_outcome
            ),
            "quality_and_interpretation": {
                "outcome_quality": None,
                "outcome_label": None,
                "is_good_decision": None,
                "is_good_execution": None,
                "is_good_no_trade": None,
                "is_ambiguous": None,
                "quality_flags": [],
                "interpretation_version": "interp-1.0.0",
                "label_interpretation_version": "labelinterp-1.0.0",
            },
            "observability": {
                "warnings": [],
                "data_quality_flags": [],
                "label_quality_flags": [],
                "horizon_family": de_decision_summary.get(
                    "outcome_horizon_family"
                ),
                "stop_logic_version": None,
                "target_logic_version": None,
                "cost_model_version_seen": None,
                "simulation_family_version_seen": None,
                "decision_policy_version_seen": de_lineage.get(
                    "policy_artifact_version"
                ),
                "portfolio_policy_version_seen": None,
                "risk_policy_version_seen": None,
                "payload_references": {},
                "review_tags": [],
            },
            "optional_extended_metadata": metadata or {},
        }

        outcome = _clean_empty_meta(outcome)
        self._store[outcome_id] = outcome
        return outcome

    # ------------------------------------------------------------------
    # GET
    # ------------------------------------------------------------------

    def get(self, outcome_id: str) -> dict[str, Any] | None:
        """Retrieve a stored TradeOutcome by ID."""
        return self._store.get(outcome_id)

    def get_by_event_id(self, event_id: str) -> dict[str, Any] | None:
        """Find a TradeOutcome linked to a specific DecisionEvent."""
        for outcome in self._store.values():
            if outcome.get("identity", {}).get("decision_event_id") == event_id:
                return outcome
        return None

    def list_all(self) -> list[dict[str, Any]]:
        """Return all stored TradeOutcomes (latest first)."""
        return list(self._store.values())

    # ------------------------------------------------------------------
    # UPDATE
    # ------------------------------------------------------------------

    def update(
        self,
        outcome_id: str,
        *,
        realized_outcome: dict[str, Any] | None = None,
        path_metrics: dict[str, Any] | None = None,
        comparative_outcome: dict[str, Any] | None = None,
        quality_and_interpretation: dict[str, Any] | None = None,
        execution_summary: dict[str, Any] | None = None,
        observability: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Update a TradeOutcome with outcome data.

        Merges provided fields into the existing outcome. Does NOT change
        resolution_status — use resolve() for that.

        Args:
            outcome_id: Outcome to update.
            realized_outcome: Realized outcome fields to merge.
            path_metrics: Path metric fields to merge.
            comparative_outcome: Comparative outcome fields to merge.
            quality_and_interpretation: Quality fields to merge.
            execution_summary: Execution summary fields to merge.
            observability: Observability fields to merge.
            metadata: Extended metadata to merge.

        Returns:
            Updated TradeOutcome.

        Raises:
            KeyError: If outcome_id not found.
        """
        outcome = self._require_outcome(outcome_id)

        sections_map: dict[str, dict[str, Any] | None] = {
            "realized_outcome": realized_outcome,
            "path_metrics": path_metrics,
            "comparative_outcome": comparative_outcome,
            "quality_and_interpretation": quality_and_interpretation,
            "execution_summary": execution_summary,
            "observability": observability,
        }

        for section_name, section_data in sections_map.items():
            if section_data is not None:
                existing = outcome.get(section_name, {})
                existing.update(section_data)
                outcome[section_name] = existing

        if metadata:
            existing_meta = outcome.get("optional_extended_metadata", {})
            existing_meta.update(metadata)
            outcome["optional_extended_metadata"] = existing_meta

        self._store[outcome_id] = outcome
        return outcome

    # ------------------------------------------------------------------
    # RESOLVE
    # ------------------------------------------------------------------

    def resolve(
        self,
        outcome_id: str,
        *,
        outcome_status: str,
        resolution_reason: str,
        realized_outcome: dict[str, Any] | None = None,
        path_metrics: dict[str, Any] | None = None,
        comparative_outcome: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Resolve a TradeOutcome — transition to a final or next status.

        Args:
            outcome_id: Outcome to resolve.
            outcome_status: Target status (RESOLVED, PARTIALLY_RESOLVED,
                           INVALIDATED, UNAVAILABLE).
            resolution_reason: Why the outcome reached this state.
            realized_outcome: Optional realized outcome data to merge.
            path_metrics: Optional path metrics to merge.
            comparative_outcome: Optional comparative outcome data to merge.

        Returns:
            Resolved TradeOutcome.

        Raises:
            InvalidTransitionError: If transition is not allowed.
            ValidationError: On invalid enum values.
        """
        outcome = self._require_outcome(outcome_id)
        current_status = outcome.get("resolution_status", {}).get(
            "outcome_status", "PENDING"
        )

        _validate_enum(outcome_status, OUTCOME_STATUSES, "outcome_status")
        _validate_enum(
            resolution_reason, RESOLUTION_REASONS, "resolution_reason"
        )

        allowed = _OUTCOME_TRANSITIONS.get(current_status, set())
        if outcome_status not in allowed:
            raise InvalidTransitionError(
                f"Cannot transition from '{current_status}' to "
                f"'{outcome_status}'. Allowed: {sorted(allowed)}"
            )

        # Merge outcome data if provided
        if realized_outcome:
            existing = outcome.get("realized_outcome", {})
            existing.update(realized_outcome)
            outcome["realized_outcome"] = existing

        if path_metrics:
            existing = outcome.get("path_metrics", {})
            existing.update(path_metrics)
            outcome["path_metrics"] = existing

        if comparative_outcome:
            existing = outcome.get("comparative_outcome", {})
            existing.update(comparative_outcome)
            outcome["comparative_outcome"] = existing

        is_final = outcome_status in ("RESOLVED", "INVALIDATED", "UNAVAILABLE")

        outcome["resolution_status"] = {
            "outcome_status": outcome_status,
            "is_final": is_final,
            "resolution_reason": resolution_reason,
            "outcome_ready_timestamp_utc": _utc_now() if is_final else None,
            "pending_horizon_family": None,
            "invalidity_reason": (
                resolution_reason
                if outcome_status == "INVALIDATED"
                else None
            ),
        }

        self._store[outcome_id] = outcome
        return outcome

    # ------------------------------------------------------------------
    # DELETE
    # ------------------------------------------------------------------

    def delete(self, outcome_id: str) -> None:
        """Remove a stored TradeOutcome from the in-memory store."""
        self._store.pop(outcome_id, None)

    # ------------------------------------------------------------------
    # INTERNALS
    # ------------------------------------------------------------------

    def _require_outcome(self, outcome_id: str) -> dict[str, Any]:
        if outcome_id not in self._store:
            raise KeyError(f"TradeOutcome '{outcome_id}' not found")
        return dict(self._store[outcome_id])

    def _validate_create_input(
        self,
        decision_event: dict[str, Any],
        outcome_source: str,
        execution_path: str,
        execution_decision: str,
        outcome_status: str,
        resolution_reason: str,
    ) -> None:
        _validate_enum(outcome_source, OUTCOME_SOURCES, "outcome_source")
        _validate_enum(execution_path, EXECUTION_PATHS, "execution_path")
        _validate_enum(
            execution_decision, EXECUTION_DECISIONS, "execution_decision"
        )
        _validate_enum(outcome_status, OUTCOME_STATUSES, "outcome_status")
        _validate_enum(
            resolution_reason, RESOLUTION_REASONS, "resolution_reason"
        )

        de_id = decision_event.get("identity", {}).get("decision_event_id")
        if not de_id:
            raise ValidationError(
                "DecisionEvent missing required 'identity.decision_event_id'"
            )

    def _build_initial_realized_outcome(
        self,
        user_realized: dict[str, Any] | None,
        de_decision_summary: dict[str, Any],
    ) -> dict[str, Any]:
        base = {
            "best_realized_action": None,
            "realized_return": None,
            "realized_r": None,
            "gross_pnl": None,
            "net_pnl": None,
            "fees_paid": None,
            "slippage_cost": None,
            "hold_duration_bars": None,
            "hold_duration_minutes": None,
            "exit_reason": None,
            # Audit-echo fields from the decision event
            "decision_confidence_seen": de_decision_summary.get("confidence"),
            "decision_confidence_kind_seen": de_decision_summary.get(
                "confidence_kind"
            ),
            "decision_expected_r_seen": de_decision_summary.get("expected_r"),
            "decision_margin_seen": de_decision_summary.get("decision_margin"),
            "entry_readiness_seen": de_decision_summary.get(
                "entry_readiness_seen"
            ),
            "entry_valid_for_bars_seen": de_decision_summary.get(
                "entry_valid_for_bars_seen"
            ),
            "time_sensitivity_seen": de_decision_summary.get(
                "time_sensitivity_seen"
            ),
        }
        if user_realized:
            base.update(user_realized)
        return base

    def _build_initial_path_metrics(
        self,
        user_metrics: dict[str, Any] | None,
    ) -> dict[str, Any]:
        base = {
            "mfe": None,
            "mae": None,
            "mfe_r": None,
            "mae_r": None,
            "time_to_mfe": None,
            "time_to_mae": None,
            "time_to_target": None,
            "time_to_stop": None,
            "target_hit_before_stop": None,
            "stop_hit_before_target": None,
            "path_quality_score": None,
        }
        if user_metrics:
            base.update(user_metrics)
        return base

    def _build_initial_comparative_outcome(
        self,
        user_comparative: dict[str, Any] | None,
    ) -> dict[str, Any]:
        base = {
            "counterfactual_best_action": None,
            "counterfactual_second_best_action": None,
            "regret_score": None,
            "regret_r": None,
            "missed_opportunity_score": None,
            "saved_loss_score": None,
            "alternative_action_gap": None,
            "skip_regret_r": None,
            "skip_saved_loss_r": None,
            "skip_was_correct": None,
            "no_trade_counterfactual_quality": None,
        }
        if user_comparative:
            base.update(user_comparative)
        return base
