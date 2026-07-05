"""Tests for v7.lifecycle — DecisionEvent & TradeOutcome lifecycle management."""

import pytest

from v7.lifecycle import (
    DecisionEventManager,
    InvalidTransitionError,
    TradeOutcomeManager,
    ValidationError,
)

# =========================================================================
# Fixtures — V7 nested AnalysisResult used as input
# =========================================================================


@pytest.fixture
def nested_analysis_result() -> dict:
    """A fully populated V7 AnalysisResult dict (nested contract shape).

    Mirrors the fixture at contracts/fixtures/analysis_result_minimal.json
    with all recommended sections.
    """
    return {
        "contract": {
            "contract_version": "v7-0.3",
            "response_schema_version": "result-0.3",
            "engine_output_version": "engine-out-0.3",
            "state_schema_version": "state-0.2",
            "snapshot_builder_version": "snapshot-0.2",
        },
        "identity": {
            "request_id": "req_001",
            "engine_name": "v7",
            "engine_version": "0.3.0",
            "timestamp_utc": "2026-07-05T12:00:01Z",
            "model_scope": "swing_v1",
            "trade_mode": "SWING",
            "run_id": "scan_001",
            "trace_id": "trace_abc",
            "model_artifact_version": "model-0.3",
            "artifact_id": "artifact_001",
            "calibration_artifact_version": "calib-0.3",
            "calibration_artifact_id": "calib_001",
            "policy_artifact_version": "policy-0.3",
        },
        "request_link": {
            "symbol": "BTCUSDT",
            "model_scope": "swing_v1",
            "trade_mode": "SWING",
            "primary_interval": "4h",
            "request_contract_version": "v7-0.2",
            "request_kind_seen": "live_scan",
            "label_horizon_family": "swing_horizon",
        },
        "status": {
            "signal_status": "SIGNAL",
            "decision_status": "VALID",
            "is_actionable": True,
        },
        "decision": {
            "recommended_action": "LONG_NOW",
            "direction": "LONG",
            "decision_summary": "Bullish breakout with volume confirmation.",
        },
        "scores": {
            "confidence": 0.78,
            "confidence_kind": "CALIBRATED",
            "expected_r": 1.35,
            "long_score": 0.81,
            "short_score": 0.10,
            "no_trade_score": 0.18,
            "decision_margin": 0.42,
            "expected_drawdown": 0.55,
        },
        "execution_guidance": {
            "entry_price": 64300.0,
            "stop_loss": 62100.0,
            "take_profit": 67800.0,
            "time_sensitivity": "STANDARD",
            "entry_readiness": "READY_NOW",
            "entry_valid_for_bars": 3,
        },
        "uncertainty_and_quality": {
            "uncertainty_score": 0.25,
            "uncertainty_type": "EPISTEMIC",
            "decision_quality": "HIGH",
            "quality_flags": [],
        },
        "fallback_and_degradation": {
            "fallback_used": False,
            "degraded_reason": None,
        },
        "observability": {
            "analysis_latency_ms": 142.0,
            "warnings": [],
            "review_tags": ["trend", "momentum_breakout"],
        },
        "lineage": {
            "analysis_batch_id": "batch_001",
            "decision_session_id": "session_001",
        },
    }


@pytest.fixture
def nested_no_trade_result() -> dict:
    """AnalysisResult with NO_TRADE recommendation."""
    return {
        "contract": {
            "contract_version": "v7-0.3",
            "response_schema_version": "result-0.3",
            "engine_output_version": "engine-out-0.3",
        },
        "identity": {
            "request_id": "req_002",
            "engine_name": "v7",
            "engine_version": "0.3.0",
            "timestamp_utc": "2026-07-05T13:00:00Z",
            "model_scope": "swing_v1",
            "trade_mode": "SWING",
        },
        "request_link": {
            "symbol": "ETHUSDT",
            "model_scope": "swing_v1",
            "trade_mode": "SWING",
            "primary_interval": "4h",
            "request_kind_seen": "live_scan",
        },
        "status": {
            "signal_status": "NO_TRADE",
            "decision_status": "VALID",
            "is_actionable": False,
        },
        "decision": {
            "recommended_action": "NO_TRADE",
            "direction": "NONE",
            "decision_summary": "Low conviction, conflicting signals.",
        },
        "scores": {
            "confidence": 0.42,
            "confidence_kind": "CALIBRATED",
            "expected_r": 0.05,
            "long_score": 0.30,
            "short_score": 0.35,
            "no_trade_score": 0.55,
        },
        "execution_guidance": {},
        "fallback_and_degradation": {
            "fallback_used": False,
            "degraded_reason": None,
        },
        "observability": {},
        "lineage": {},
    }


@pytest.fixture
def decision_event_manager() -> DecisionEventManager:
    """Empty DecisionEventManager for testing."""
    return DecisionEventManager()


@pytest.fixture
def trade_outcome_manager() -> TradeOutcomeManager:
    """Empty TradeOutcomeManager for testing."""
    return TradeOutcomeManager()


# =========================================================================
# DecisionEventManager Tests
# =========================================================================


class TestDecisionEventManagerCreate:
    """Tests for DecisionEventManager.create()."""

    def test_create_full_event(self, decision_event_manager, nested_analysis_result):
        """Create a DecisionEvent and verify all 10 sections exist."""
        event = decision_event_manager.create(
            analysis_result=nested_analysis_result,
            venue="paper_trading",
        )

        # Verify all top-level sections
        assert "contract" in event
        assert "identity" in event
        assert "lineage" in event
        assert "scope" in event
        assert "request_summary" in event
        assert "decision_summary" in event
        assert "runtime_interpretation" in event
        assert "execution_linkage" in event
        assert "outcome_linkage" in event
        assert "observability" in event

    def test_create_contract_section(self, decision_event_manager, nested_analysis_result):
        """Contract section has correct version fields."""
        event = decision_event_manager.create(analysis_result=nested_analysis_result)
        c = event["contract"]
        assert c["event_schema_version"] == "decision-event-1.0.0"
        assert c["contract_version"] == "v7-1.0.0"
        assert c["request_contract_version"] == "v7-0.2"
        assert c["response_schema_version"] == "result-1.0.0"

    def test_create_identity_section(self, decision_event_manager, nested_analysis_result):
        """Identity section has correct fields."""
        event = decision_event_manager.create(analysis_result=nested_analysis_result)
        i = event["identity"]
        assert i["decision_event_id"].startswith("evt_")
        assert i["request_id"] == "req_001"
        assert i["timestamp_utc"] == "2026-07-05T12:00:01Z"
        assert i["run_id"] == "scan_001"
        assert i["trace_id"] == "trace_abc"

    def test_create_lineage_section(self, decision_event_manager, nested_analysis_result):
        """Lineage section carries engine/artifact info."""
        event = decision_event_manager.create(analysis_result=nested_analysis_result)
        l = event["lineage"]
        assert l["engine_name"] == "v7"
        assert l["engine_version"] == "0.3.0"
        assert l["model_scope"] == "swing_v1"
        assert l["trade_mode"] == "SWING"
        assert l["analysis_batch_id"] == "batch_001"
        assert l["decision_session_id"] == "session_001"
        assert l["model_artifact_version"] == "model-0.3"

    def test_create_scope_section(self, decision_event_manager, nested_analysis_result):
        """Scope section carries symbol/mode/interval."""
        event = decision_event_manager.create(analysis_result=nested_analysis_result)
        s = event["scope"]
        assert s["symbol"] == "BTCUSDT"
        assert s["model_scope"] == "swing_v1"
        assert s["trade_mode"] == "SWING"
        assert s["primary_interval"] == "4h"
        assert s["analysis_mode"] == "live"

    def test_create_decision_summary(self, decision_event_manager, nested_analysis_result):
        """Decision summary mirrors result decision/scores."""
        event = decision_event_manager.create(analysis_result=nested_analysis_result)
        ds = event["decision_summary"]
        assert ds["signal_status"] == "SIGNAL"
        assert ds["decision_status"] == "VALID"
        assert ds["is_actionable"] is True
        assert ds["recommended_action"] == "LONG_NOW"
        assert ds["direction"] == "LONG"
        assert ds["confidence"] == 0.78
        assert ds["expected_r"] == 1.35
        assert ds["entry_readiness_seen"] == "READY_NOW"
        assert ds["entry_valid_for_bars_seen"] == 3

    def test_create_runtime_interpretation(self, decision_event_manager, nested_analysis_result):
        """Runtime interpretation reflects actionable result."""
        event = decision_event_manager.create(analysis_result=nested_analysis_result)
        ri = event["runtime_interpretation"]
        assert ri["runtime_actionability"] == "ACTIONABLE"
        assert ri["fallback_used"] is False
        assert ri["should_persist_as_signal"] is True
        assert ri["should_surface_to_review"] is True

    def test_create_execution_linkage(self, decision_event_manager, nested_analysis_result):
        """Execution linkage reflects venue and actionability."""
        event = decision_event_manager.create(
            analysis_result=nested_analysis_result,
            venue="paper_trading",
        )
        el = event["execution_linkage"]
        assert el["execution_path"] == "PAPER_EXECUTED"
        assert el["execution_decision"] == "EXECUTED"
        assert el["event_type"] == "ORDER_PLACED"
        assert el["event_status"] == "SUCCESS"

    def test_create_outcome_linkage(self, decision_event_manager, nested_analysis_result):
        """Outcome linkage starts in PENDING."""
        event = decision_event_manager.create(analysis_result=nested_analysis_result)
        ol = event["outcome_linkage"]
        assert ol["outcome_status"] == "PENDING"
        assert ol["label_status"] == "NOT_LABELED"
        assert ol["trade_outcome_id"] is None

    def test_create_with_live_venue(self, decision_event_manager, nested_analysis_result):
        """Live venue yields LIVE_EXECUTED path."""
        event = decision_event_manager.create(
            analysis_result=nested_analysis_result,
            venue="binance_futures",
            order_id="ord_123",
            event_type="ORDER_FILLED",
            status="SUCCESS",
        )
        el = event["execution_linkage"]
        assert el["execution_path"] == "LIVE_EXECUTED"
        assert el["order_group_id"] == "ord_123"

    def test_create_with_order_and_position(
        self, decision_event_manager, nested_analysis_result
    ):
        """Order and position IDs appear in execution linkage."""
        event = decision_event_manager.create(
            analysis_result=nested_analysis_result,
            order_id="ord_abc",
            position_id="pos_xyz",
        )
        el = event["execution_linkage"]
        assert el["order_group_id"] == "ord_abc"
        assert el["position_id"] == "pos_xyz"

    def test_create_with_metadata(self, decision_event_manager, nested_analysis_result):
        """Custom metadata is stored in optional_extended_metadata."""
        metadata = {"filled_qty": 0.05, "commission": 0.0032}
        event = decision_event_manager.create(
            analysis_result=nested_analysis_result,
            metadata=metadata,
        )
        assert event["optional_extended_metadata"] == metadata

    def test_create_no_trade_event(self, decision_event_manager, nested_no_trade_result):
        """NO_TRADE result yields NOT_ACTIONABLE event."""
        event = decision_event_manager.create(analysis_result=nested_no_trade_result)
        assert event["decision_summary"]["is_actionable"] is False
        assert event["decision_summary"]["recommended_action"] == "NO_TRADE"
        assert event["execution_linkage"]["execution_decision"] == "SKIPPED"

    def test_create_with_custom_id(self, decision_event_manager, nested_analysis_result):
        """Custom event_id is preserved."""
        event = decision_event_manager.create(
            analysis_result=nested_analysis_result,
            decision_event_id="evt_custom_id",
        )
        assert event["identity"]["decision_event_id"] == "evt_custom_id"

    def test_create_invalid_event_type(self, decision_event_manager, nested_analysis_result):
        """Invalid event_type raises ValidationError."""
        with pytest.raises(ValidationError):
            decision_event_manager.create(
                analysis_result=nested_analysis_result,
                event_type="INVALID_TYPE",
            )

    def test_create_invalid_status(self, decision_event_manager, nested_analysis_result):
        """Invalid status raises ValidationError."""
        with pytest.raises(ValidationError):
            decision_event_manager.create(
                analysis_result=nested_analysis_result,
                status="INVALID_STATUS",
            )

    def test_create_missing_request_id(self, decision_event_manager):
        """Missing identity.request_id raises ValidationError."""
        with pytest.raises(ValidationError, match="request_id"):
            decision_event_manager.create(
                analysis_result={"identity": {}},
            )


class TestDecisionEventManagerGet:
    """Tests for DecisionEventManager.get() and list_all()."""

    def test_get_stored_event(self, decision_event_manager, nested_analysis_result):
        """Get returns a stored event."""
        created = decision_event_manager.create(analysis_result=nested_analysis_result)
        eid = created["identity"]["decision_event_id"]
        retrieved = decision_event_manager.get(eid)
        assert retrieved is not None
        assert retrieved["identity"]["decision_event_id"] == eid

    def test_get_missing_event(self, decision_event_manager):
        """Get returns None for unknown event."""
        assert decision_event_manager.get("nonexistent") is None

    def test_list_all(self, decision_event_manager, nested_analysis_result):
        """List all returns events in insertion order."""
        assert len(decision_event_manager.list_all()) == 0
        decision_event_manager.create(analysis_result=nested_analysis_result)
        decision_event_manager.create(
            analysis_result=nested_analysis_result,
            decision_event_id="evt_second",
        )
        assert len(decision_event_manager.list_all()) == 2


class TestDecisionEventManagerUpdate:
    """Tests for DecisionEventManager.update()."""

    def test_update_execution_linkage(self, decision_event_manager, nested_analysis_result):
        """Update modifies execution linkage fields."""
        created = decision_event_manager.create(analysis_result=nested_analysis_result)
        eid = created["identity"]["decision_event_id"]

        updated = decision_event_manager.update(
            eid,
            event_type="ORDER_FILLED",
            status="SUCCESS",
            order_id="ord_filled_123",
            position_id="pos_456",
        )
        el = updated["execution_linkage"]
        assert el["event_type"] == "ORDER_FILLED"
        assert el["event_status"] == "SUCCESS"
        assert el["order_group_id"] == "ord_filled_123"
        assert el["position_id"] == "pos_456"

    def test_update_outcome_linkage(self, decision_event_manager, nested_analysis_result):
        """Update can link a TradeOutcome ID."""
        created = decision_event_manager.create(analysis_result=nested_analysis_result)
        eid = created["identity"]["decision_event_id"]

        updated = decision_event_manager.update(
            eid,
            trade_outcome_id="to_001",
            outcome_status="RESOLVED",
        )
        ol = updated["outcome_linkage"]
        assert ol["trade_outcome_id"] == "to_001"
        assert ol["outcome_status"] == "RESOLVED"

    def test_update_metadata(self, decision_event_manager, nested_analysis_result):
        """Update merges metadata."""
        created = decision_event_manager.create(analysis_result=nested_analysis_result)
        eid = created["identity"]["decision_event_id"]

        updated = decision_event_manager.update(
            eid,
            metadata={"extra_field": "value"},
        )
        assert updated["optional_extended_metadata"]["extra_field"] == "value"

    def test_update_missing_event(self, decision_event_manager):
        """Updating a nonexistent event raises KeyError."""
        with pytest.raises(KeyError):
            decision_event_manager.update("nonexistent", event_type="ERROR")


class TestDecisionEventManagerClose:
    """Tests for DecisionEventManager.close()."""

    def test_close_event(self, decision_event_manager, nested_analysis_result):
        """Close transitions to POSITION_CLOSED."""
        created = decision_event_manager.create(analysis_result=nested_analysis_result)
        eid = created["identity"]["decision_event_id"]

        closed = decision_event_manager.close(eid)
        assert closed["execution_linkage"]["event_type"] == "POSITION_CLOSED"
        assert closed["execution_linkage"]["event_status"] == "SUCCESS"

    def test_close_with_status(self, decision_event_manager, nested_analysis_result):
        """Close supports custom final status."""
        created = decision_event_manager.create(analysis_result=nested_analysis_result)
        eid = created["identity"]["decision_event_id"]

        closed = decision_event_manager.close(
            eid, final_status="PARTIAL", event_type="ERROR"
        )
        assert closed["execution_linkage"]["event_type"] == "ERROR"
        assert closed["execution_linkage"]["event_status"] == "PARTIAL"


class TestDecisionEventManagerDelete:
    """Tests for DecisionEventManager.delete()."""

    def test_delete_event(self, decision_event_manager, nested_analysis_result):
        """Delete removes from store."""
        created = decision_event_manager.create(analysis_result=nested_analysis_result)
        eid = created["identity"]["decision_event_id"]
        decision_event_manager.delete(eid)
        assert decision_event_manager.get(eid) is None

    def test_delete_nonexistent(self, decision_event_manager):
        """Delete on missing event does not raise."""
        decision_event_manager.delete("nonexistent")  # should not raise


# =========================================================================
# TradeOutcomeManager Tests
# =========================================================================


@pytest.fixture
def sample_decision_event(decision_event_manager, nested_analysis_result) -> dict:
    """Fixture providing a DecisionEvent for TradeOutcome creation."""
    return decision_event_manager.create(analysis_result=nested_analysis_result)


class TestTradeOutcomeManagerCreate:
    """Tests for TradeOutcomeManager.create()."""

    def test_create_full_outcome(self, trade_outcome_manager, sample_decision_event):
        """Create TradeOutcome and verify all sections exist."""
        outcome = trade_outcome_manager.create(decision_event=sample_decision_event)

        assert "contract" in outcome
        assert "identity" in outcome
        assert "lineage" in outcome
        assert "execution_summary" in outcome
        assert "resolution_status" in outcome
        assert "realized_outcome" in outcome
        assert "path_metrics" in outcome
        assert "comparative_outcome" in outcome
        assert "quality_and_interpretation" in outcome
        assert "observability" in outcome

    def test_create_contract_section(self, trade_outcome_manager, sample_decision_event):
        """Contract section has correct versions."""
        outcome = trade_outcome_manager.create(decision_event=sample_decision_event)
        c = outcome["contract"]
        assert c["outcome_schema_version"] == "trade-outcome-1.0.0"
        assert c["contract_version"] == "v7-1.0.0"
        assert c["event_schema_version"] == "decision-event-1.0.0"

    def test_create_identity_section(self, trade_outcome_manager, sample_decision_event):
        """Identity links to DecisionEvent."""
        de_id = sample_decision_event["identity"]["decision_event_id"]
        outcome = trade_outcome_manager.create(decision_event=sample_decision_event)
        i = outcome["identity"]
        assert i["trade_outcome_id"].startswith("to_")
        assert i["decision_event_id"] == de_id
        assert i["timestamp_utc"] is not None

    def test_create_lineage_section(self, trade_outcome_manager, sample_decision_event):
        """Lineage carries request_id, engine info, mode."""
        de_req_id = sample_decision_event["identity"]["request_id"]
        outcome = trade_outcome_manager.create(decision_event=sample_decision_event)
        l = outcome["lineage"]
        assert l["request_id"] == de_req_id
        assert l["engine_name"] == "v7"
        assert l["engine_version"] == "0.3.0"
        assert l["outcome_source"] == "PAPER_EXECUTION"
        assert l["model_scope"] == "swing_v1"
        assert l["trade_mode"] == "SWING"

    def test_create_execution_summary(self, trade_outcome_manager, sample_decision_event):
        """Execution summary reflects defaults."""
        outcome = trade_outcome_manager.create(decision_event=sample_decision_event)
        es = outcome["execution_summary"]
        assert es["execution_path"] == "PAPER_EXECUTED"
        assert es["execution_decision"] == "EXECUTED"
        assert es["position_opened"] is False

    def test_create_resolution_status_pending(
        self, trade_outcome_manager, sample_decision_event
    ):
        """Default resolution status is PENDING, not final."""
        outcome = trade_outcome_manager.create(decision_event=sample_decision_event)
        rs = outcome["resolution_status"]
        assert rs["outcome_status"] == "PENDING"
        assert rs["is_final"] is False
        assert rs["resolution_reason"] == "EXECUTION_INCOMPLETE"

    def test_create_resolution_status_resolved(
        self, trade_outcome_manager, sample_decision_event
    ):
        """Can create outcome already in RESOLVED state."""
        outcome = trade_outcome_manager.create(
            decision_event=sample_decision_event,
            outcome_status="RESOLVED",
            resolution_reason="HORIZON_COMPLETE",
        )
        rs = outcome["resolution_status"]
        assert rs["outcome_status"] == "RESOLVED"
        assert rs["is_final"] is True
        assert rs["resolution_reason"] == "HORIZON_COMPLETE"

    def test_create_outcome_source_variants(
        self, trade_outcome_manager, sample_decision_event
    ):
        """Can set different outcome_source values."""
        for source in ("LIVE_EXECUTION", "REPLAY_PROJECTION", "OFFLINE_LABELING", "SKIP_EVAL"):
            outcome = trade_outcome_manager.create(
                decision_event=sample_decision_event,
                outcome_source=source,
            )
            assert outcome["lineage"]["outcome_source"] == source

    def test_create_execution_path_variants(
        self, trade_outcome_manager, sample_decision_event
    ):
        """Can set different execution_path values."""
        outcome = trade_outcome_manager.create(
            decision_event=sample_decision_event,
            execution_path="LIVE_EXECUTED",
            execution_decision="EXECUTED",
            position_opened=True,
        )
        es = outcome["execution_summary"]
        assert es["execution_path"] == "LIVE_EXECUTED"
        assert es["execution_decision"] == "EXECUTED"
        assert es["position_opened"] is True

    def test_create_realized_outcome_echos(
        self, trade_outcome_manager, sample_decision_event
    ):
        """Realized outcome includes decision-time audit echoes."""
        outcome = trade_outcome_manager.create(decision_event=sample_decision_event)
        ro = outcome["realized_outcome"]
        assert ro["decision_confidence_seen"] == 0.78
        assert ro["decision_expected_r_seen"] == 1.35
        assert ro["entry_readiness_seen"] == "READY_NOW"

    def test_create_with_realized_outcome_data(
        self, trade_outcome_manager, sample_decision_event
    ):
        """Can pass initial realized outcome data."""
        realized = {"realized_r": 1.5, "exit_reason": "TARGET_HIT"}
        outcome = trade_outcome_manager.create(
            decision_event=sample_decision_event,
            realized_outcome=realized,
        )
        assert outcome["realized_outcome"]["realized_r"] == 1.5
        # Echo fields still present alongside user data
        assert outcome["realized_outcome"]["decision_confidence_seen"] == 0.78

    def test_create_with_path_metrics(
        self, trade_outcome_manager, sample_decision_event
    ):
        """Can pass initial path metrics."""
        metrics = {"mfe_r": 2.1, "mae_r": -0.5, "path_quality_score": 0.82}
        outcome = trade_outcome_manager.create(
            decision_event=sample_decision_event,
            path_metrics=metrics,
        )
        assert outcome["path_metrics"]["mfe_r"] == 2.1
        assert outcome["path_metrics"]["path_quality_score"] == 0.82

    def test_create_invalid_outcome_source(
        self, trade_outcome_manager, sample_decision_event
    ):
        """Invalid outcome_source raises ValidationError."""
        with pytest.raises(ValidationError):
            trade_outcome_manager.create(
                decision_event=sample_decision_event,
                outcome_source="INVALID_SOURCE",
            )

    def test_create_invalid_execution_path(
        self, trade_outcome_manager, sample_decision_event
    ):
        """Invalid execution_path raises ValidationError."""
        with pytest.raises(ValidationError):
            trade_outcome_manager.create(
                decision_event=sample_decision_event,
                execution_path="INVALID_PATH",
            )

    def test_create_invalid_outcome_status(
        self, trade_outcome_manager, sample_decision_event
    ):
        """Invalid outcome_status raises ValidationError."""
        with pytest.raises(ValidationError):
            trade_outcome_manager.create(
                decision_event=sample_decision_event,
                outcome_status="INVALID_STATUS",
            )

    def test_create_missing_decision_event_id(
        self, trade_outcome_manager
    ):
        """Missing decision_event_id in event raises ValidationError."""
        bad_event = {"identity": {}}
        with pytest.raises(ValidationError, match="decision_event_id"):
            trade_outcome_manager.create(decision_event=bad_event)


class TestTradeOutcomeManagerGet:
    """Tests for TradeOutcomeManager get/list methods."""

    def test_get_stored(self, trade_outcome_manager, sample_decision_event):
        """Get returns stored outcome by ID."""
        created = trade_outcome_manager.create(decision_event=sample_decision_event)
        to_id = created["identity"]["trade_outcome_id"]
        retrieved = trade_outcome_manager.get(to_id)
        assert retrieved is not None
        assert retrieved["identity"]["trade_outcome_id"] == to_id

    def test_get_missing(self, trade_outcome_manager):
        """Get returns None for unknown outcome."""
        assert trade_outcome_manager.get("nonexistent") is None

    def test_get_by_event_id(self, trade_outcome_manager, sample_decision_event):
        """Get by event ID finds linked outcome."""
        de_id = sample_decision_event["identity"]["decision_event_id"]
        created = trade_outcome_manager.create(decision_event=sample_decision_event)
        found = trade_outcome_manager.get_by_event_id(de_id)
        assert found is not None
        assert found["identity"]["trade_outcome_id"] == created["identity"]["trade_outcome_id"]

    def test_get_by_event_id_missing(self, trade_outcome_manager):
        """Get by event ID returns None when no match."""
        assert trade_outcome_manager.get_by_event_id("nonexistent") is None

    def test_list_all(self, trade_outcome_manager, sample_decision_event):
        """List all returns outcomes in insertion order."""
        assert len(trade_outcome_manager.list_all()) == 0
        trade_outcome_manager.create(decision_event=sample_decision_event)
        trade_outcome_manager.create(
            decision_event=sample_decision_event,
            trade_outcome_id="to_second",
        )
        assert len(trade_outcome_manager.list_all()) == 2


class TestTradeOutcomeManagerUpdate:
    """Tests for TradeOutcomeManager.update()."""

    def test_update_realized_outcome(
        self, trade_outcome_manager, sample_decision_event
    ):
        """Update can fill in realized outcome data."""
        created = trade_outcome_manager.create(decision_event=sample_decision_event)
        to_id = created["identity"]["trade_outcome_id"]

        updated = trade_outcome_manager.update(
            to_id,
            realized_outcome={
                "realized_r": 1.82,
                "best_realized_action": "LONG_NOW",
                "exit_reason": "TARGET_HIT",
                "hold_duration_bars": 10,
            },
        )
        ro = updated["realized_outcome"]
        assert ro["realized_r"] == 1.82
        assert ro["best_realized_action"] == "LONG_NOW"
        assert ro["exit_reason"] == "TARGET_HIT"

    def test_update_path_metrics(self, trade_outcome_manager, sample_decision_event):
        """Update fills in path metrics."""
        created = trade_outcome_manager.create(decision_event=sample_decision_event)
        to_id = created["identity"]["trade_outcome_id"]

        updated = trade_outcome_manager.update(
            to_id,
            path_metrics={
                "mfe_r": 2.5,
                "mae_r": -0.35,
                "path_quality_score": 0.85,
            },
        )
        pm = updated["path_metrics"]
        assert pm["mfe_r"] == 2.5
        assert pm["mae_r"] == -0.35
        assert pm["path_quality_score"] == 0.85

    def test_update_comparative_outcome(
        self, trade_outcome_manager, sample_decision_event
    ):
        """Update fills in comparative outcome."""
        created = trade_outcome_manager.create(decision_event=sample_decision_event)
        to_id = created["identity"]["trade_outcome_id"]

        updated = trade_outcome_manager.update(
            to_id,
            comparative_outcome={
                "counterfactual_best_action": "LONG_NOW",
                "regret_r": 0.0,
                "saved_loss_score": 0.62,
                "missed_opportunity_score": 0.73,
            },
        )
        co = updated["comparative_outcome"]
        assert co["counterfactual_best_action"] == "LONG_NOW"
        assert co["regret_r"] == 0.0

    def test_update_quality_and_interpretation(
        self, trade_outcome_manager, sample_decision_event
    ):
        """Update fills in quality interpretation."""
        created = trade_outcome_manager.create(decision_event=sample_decision_event)
        to_id = created["identity"]["trade_outcome_id"]

        updated = trade_outcome_manager.update(
            to_id,
            quality_and_interpretation={
                "outcome_label": "CLEAN_LONG_OPPORTUNITY",
                "is_good_decision": True,
                "outcome_quality": "HIGH",
            },
        )
        qi = updated["quality_and_interpretation"]
        assert qi["outcome_label"] == "CLEAN_LONG_OPPORTUNITY"
        assert qi["is_good_decision"] is True

    def test_update_metadata(self, trade_outcome_manager, sample_decision_event):
        """Update merges extended metadata."""
        created = trade_outcome_manager.create(decision_event=sample_decision_event)
        to_id = created["identity"]["trade_outcome_id"]

        updated = trade_outcome_manager.update(
            to_id,
            metadata={"review_note": "Clean trade"},
        )
        assert updated["optional_extended_metadata"]["review_note"] == "Clean trade"

    def test_update_missing_outcome(self, trade_outcome_manager):
        """Updating nonexistent outcome raises KeyError."""
        with pytest.raises(KeyError):
            trade_outcome_manager.update("nonexistent", realized_outcome={})


class TestTradeOutcomeManagerResolve:
    """Tests for TradeOutcomeManager.resolve()."""

    def test_resolve_pending_to_resolved(
        self, trade_outcome_manager, sample_decision_event
    ):
        """PENDING -> RESOLVED transition works."""
        outcome = trade_outcome_manager.create(decision_event=sample_decision_event)
        to_id = outcome["identity"]["trade_outcome_id"]

        resolved = trade_outcome_manager.resolve(
            to_id,
            outcome_status="RESOLVED",
            resolution_reason="TARGET_HIT",
            realized_outcome={"realized_r": 1.8, "exit_reason": "TARGET_HIT"},
        )
        rs = resolved["resolution_status"]
        assert rs["outcome_status"] == "RESOLVED"
        assert rs["is_final"] is True
        assert rs["resolution_reason"] == "TARGET_HIT"

    def test_resolve_pending_to_invalidated(
        self, trade_outcome_manager, sample_decision_event
    ):
        """PENDING -> INVALIDATED transition works."""
        outcome = trade_outcome_manager.create(decision_event=sample_decision_event)
        to_id = outcome["identity"]["trade_outcome_id"]

        invalidated = trade_outcome_manager.resolve(
            to_id,
            outcome_status="INVALIDATED",
            resolution_reason="DATA_INCOMPLETE",
        )
        rs = invalidated["resolution_status"]
        assert rs["outcome_status"] == "INVALIDATED"
        assert rs["is_final"] is True
        assert rs["invalidity_reason"] == "DATA_INCOMPLETE"

    def test_resolve_pending_to_partially_resolved(
        self, trade_outcome_manager, sample_decision_event
    ):
        """PENDING -> PARTIALLY_RESOLVED transition works."""
        outcome = trade_outcome_manager.create(decision_event=sample_decision_event)
        to_id = outcome["identity"]["trade_outcome_id"]

        pr = trade_outcome_manager.resolve(
            to_id,
            outcome_status="PARTIALLY_RESOLVED",
            resolution_reason="EXECUTION_INCOMPLETE",
        )
        rs = pr["resolution_status"]
        assert rs["outcome_status"] == "PARTIALLY_RESOLVED"
        assert rs["is_final"] is False

    def test_resolve_partial_to_resolved(
        self, trade_outcome_manager, sample_decision_event
    ):
        """PARTIALLY_RESOLVED -> RESOLVED transition works."""
        outcome = trade_outcome_manager.create(decision_event=sample_decision_event)
        to_id = outcome["identity"]["trade_outcome_id"]

        trade_outcome_manager.resolve(
            to_id,
            outcome_status="PARTIALLY_RESOLVED",
            resolution_reason="EXECUTION_INCOMPLETE",
        )
        resolved = trade_outcome_manager.resolve(
            to_id,
            outcome_status="RESOLVED",
            resolution_reason="HORIZON_COMPLETE",
        )
        assert resolved["resolution_status"]["outcome_status"] == "RESOLVED"
        assert resolved["resolution_status"]["is_final"] is True

    def test_resolve_pending_to_unavailable(
        self, trade_outcome_manager, sample_decision_event
    ):
        """PENDING -> UNAVAILABLE transition works."""
        outcome = trade_outcome_manager.create(decision_event=sample_decision_event)
        to_id = outcome["identity"]["trade_outcome_id"]

        ua = trade_outcome_manager.resolve(
            to_id,
            outcome_status="UNAVAILABLE",
            resolution_reason="DATA_INCOMPLETE",
        )
        assert ua["resolution_status"]["outcome_status"] == "UNAVAILABLE"
        assert ua["resolution_status"]["is_final"] is True

    def test_invalid_transition_resolved_to_pending(
        self, trade_outcome_manager, sample_decision_event
    ):
        """RESOLVED -> PENDING is not allowed."""
        outcome = trade_outcome_manager.create(
            decision_event=sample_decision_event,
            outcome_status="RESOLVED",
            resolution_reason="TARGET_HIT",
        )
        to_id = outcome["identity"]["trade_outcome_id"]

        with pytest.raises(InvalidTransitionError, match="transition"):
            trade_outcome_manager.resolve(
                to_id,
                outcome_status="PENDING",
                resolution_reason="EXECUTION_INCOMPLETE",
            )

    def test_invalid_transition_resolved_to_invalidated(
        self, trade_outcome_manager, sample_decision_event
    ):
        """RESOLVED -> INVALIDATED is not allowed."""
        outcome = trade_outcome_manager.create(
            decision_event=sample_decision_event,
            outcome_status="RESOLVED",
            resolution_reason="TARGET_HIT",
        )
        to_id = outcome["identity"]["trade_outcome_id"]

        with pytest.raises(InvalidTransitionError):
            trade_outcome_manager.resolve(
                to_id,
                outcome_status="INVALIDATED",
                resolution_reason="DATA_INCOMPLETE",
            )

    def test_invalid_transition_unavailable_to_resolved(
        self, trade_outcome_manager, sample_decision_event
    ):
        """UNAVAILABLE -> RESOLVED is not allowed."""
        outcome = trade_outcome_manager.create(
            decision_event=sample_decision_event,
            outcome_status="UNAVAILABLE",
            resolution_reason="DATA_INCOMPLETE",
        )
        to_id = outcome["identity"]["trade_outcome_id"]

        with pytest.raises(InvalidTransitionError):
            trade_outcome_manager.resolve(
                to_id,
                outcome_status="RESOLVED",
                resolution_reason="HORIZON_COMPLETE",
            )

    def test_resolve_with_data_merge(
        self, trade_outcome_manager, sample_decision_event
    ):
        """Resolve merges outcome data alongside resolution."""
        outcome = trade_outcome_manager.create(decision_event=sample_decision_event)
        to_id = outcome["identity"]["trade_outcome_id"]

        resolved = trade_outcome_manager.resolve(
            to_id,
            outcome_status="RESOLVED",
            resolution_reason="TARGET_HIT",
            realized_outcome={"realized_r": 2.1, "exit_reason": "TARGET_HIT"},
            path_metrics={"mfe_r": 3.0, "path_quality_score": 0.9},
            comparative_outcome={"counterfactual_best_action": "LONG_NOW"},
        )
        assert resolved["realized_outcome"]["realized_r"] == 2.1
        assert resolved["path_metrics"]["mfe_r"] == 3.0
        assert resolved["comparative_outcome"]["counterfactual_best_action"] == "LONG_NOW"


class TestTradeOutcomeManagerDelete:
    """Tests for TradeOutcomeManager.delete()."""

    def test_delete_outcome(self, trade_outcome_manager, sample_decision_event):
        """Delete removes from store."""
        outcome = trade_outcome_manager.create(decision_event=sample_decision_event)
        to_id = outcome["identity"]["trade_outcome_id"]
        trade_outcome_manager.delete(to_id)
        assert trade_outcome_manager.get(to_id) is None

    def test_delete_nonexistent(self, trade_outcome_manager):
        """Delete on missing outcome does not raise."""
        trade_outcome_manager.delete("nonexistent")


# =========================================================================
# Integration Tests
# =========================================================================


class TestLifecycleIntegration:
    """End-to-end lifecycle: AnalysisResult -> DecisionEvent -> TradeOutcome."""

    def test_full_swing_lifecycle(self, nested_analysis_result):
        """Complete SWING trade lifecycle: create DE -> create TO -> resolve."""
        dem = DecisionEventManager()
        tom = TradeOutcomeManager()

        # Step 1: Create DecisionEvent from AnalysisResult
        event = dem.create(
            analysis_result=nested_analysis_result,
            venue="binance_futures",
            event_type="ORDER_PLACED",
            status="PENDING",
        )
        eid = event["identity"]["decision_event_id"]
        assert event["scope"]["symbol"] == "BTCUSDT"
        assert event["scope"]["trade_mode"] == "SWING"
        assert event["decision_summary"]["recommended_action"] == "LONG_NOW"

        # Step 2: Update event with execution progress
        event = dem.update(
            eid,
            event_type="ORDER_FILLED",
            status="SUCCESS",
            order_id="ord_binance_123",
            position_id="pos_binance_456",
        )
        assert event["execution_linkage"]["order_group_id"] == "ord_binance_123"
        assert event["execution_linkage"]["position_id"] == "pos_binance_456"

        # Step 3: Create TradeOutcome from DecisionEvent
        outcome = tom.create(
            decision_event=event,
            outcome_source="LIVE_EXECUTION",
            execution_path="LIVE_EXECUTED",
            execution_decision="EXECUTED",
            position_opened=True,
        )
        to_id = outcome["identity"]["trade_outcome_id"]
        assert outcome["identity"]["decision_event_id"] == eid
        assert outcome["lineage"]["request_id"] == "req_001"

        # Link outcome back to event
        dem.update(eid, trade_outcome_id=to_id, outcome_status="PENDING")

        # Step 4: Close the event (position closed)
        dem.close(eid)
        assert dem.get(eid)["execution_linkage"]["event_type"] == "POSITION_CLOSED"

        # Step 5: Update outcome with realized data
        tom.update(
            to_id,
            realized_outcome={
                "best_realized_action": "LONG_NOW",
                "realized_r": 1.82,
                "exit_reason": "TARGET_HIT",
            },
            path_metrics={
                "mfe_r": 2.5,
                "mae_r": -0.35,
                "path_quality_score": 0.82,
            },
        )

        # Step 6: Resolve outcome
        resolved = tom.resolve(
            to_id,
            outcome_status="RESOLVED",
            resolution_reason="TARGET_HIT",
        )
        assert resolved["resolution_status"]["outcome_status"] == "RESOLVED"
        assert resolved["resolution_status"]["is_final"] is True
        assert resolved["realized_outcome"]["realized_r"] == 1.82
        assert resolved["path_metrics"]["path_quality_score"] == 0.82

    def test_no_trade_skip_lifecycle(self, nested_no_trade_result):
        """NO_TRADE lifecycle: event created, skipped, outcome resolved."""
        dem = DecisionEventManager()
        tom = TradeOutcomeManager()

        event = dem.create(
            analysis_result=nested_no_trade_result,
            event_type="ORDER_PLACED",
            status="PENDING",
        )
        eid = event["identity"]["decision_event_id"]
        assert event["decision_summary"]["recommended_action"] == "NO_TRADE"
        assert event["execution_linkage"]["execution_decision"] == "SKIPPED"

        outcome = tom.create(
            decision_event=event,
            outcome_source="SKIP_EVAL",
            execution_path="SKIPPED_BY_RUNTIME",
            execution_decision="SKIPPED",
            position_opened=False,
            outcome_status="RESOLVED",
            resolution_reason="SKIP_EVAL_COMPLETE",
        )
        assert outcome["resolution_status"]["outcome_status"] == "RESOLVED"
        assert outcome["resolution_status"]["is_final"] is True

    def test_traceability(self, nested_analysis_result):
        """Full traceability from outcome back to original AnalysisResult."""
        dem = DecisionEventManager()
        tom = TradeOutcomeManager()

        event = dem.create(analysis_result=nested_analysis_result)
        eid = event["identity"]["decision_event_id"]
        req_id_original = nested_analysis_result["identity"]["request_id"]

        outcome = tom.create(decision_event=event)
        to_id = outcome["identity"]["trade_outcome_id"]

        # Trace forward: result -> event -> outcome
        assert event["identity"]["request_id"] == req_id_original
        assert outcome["identity"]["decision_event_id"] == eid
        assert outcome["lineage"]["request_id"] == req_id_original

        # Trace backward: outcome -> event -> result
        retrieved_event = dem.get(eid)
        assert retrieved_event is not None
        assert retrieved_event["identity"]["request_id"] == req_id_original

        retrieved_outcome = tom.get_by_event_id(eid)
        assert retrieved_outcome is not None
        assert retrieved_outcome["identity"]["trade_outcome_id"] == to_id

        # Verify consistency rules from contract docs
        assert (
            outcome["identity"]["decision_event_id"]
            == event["identity"]["decision_event_id"]
        )
        assert outcome["lineage"]["request_id"] == event["identity"]["request_id"]
        assert (
            outcome["lineage"]["engine_name"]
            == event["lineage"]["engine_name"]
        )
        assert (
            outcome["lineage"]["engine_version"]
            == event["lineage"]["engine_version"]
        )

    def test_fixture_compatible_shape(self, nested_analysis_result):
        """Output is compatible with contract fixture shapes."""
        dem = DecisionEventManager()
        tom = TradeOutcomeManager()

        event = dem.create(analysis_result=nested_analysis_result)

        # DecisionEvent flat-schema required fields exist in nested shape
        assert event["identity"]["decision_event_id"]  # event_id
        assert event["identity"]["request_id"]  # maps to analysis_result_id
        assert event["decision_summary"]["recommended_action"]  # decision
        assert event["identity"]["timestamp_utc"]  # executed_at
        assert event["execution_linkage"]["event_type"]  # event_type
        assert event["execution_linkage"]["event_status"]  # status

        outcome = tom.create(decision_event=event)

        # TradeOutcome flat-schema required fields exist
        assert outcome["identity"]["trade_outcome_id"]
        assert outcome["identity"]["decision_event_id"]
        assert outcome["identity"]["timestamp_utc"]
        assert outcome["contract"]["outcome_schema_version"]
        assert outcome["contract"]["contract_version"]
        assert outcome["contract"]["event_schema_version"]
        assert outcome["lineage"]["request_id"]
        assert outcome["lineage"]["outcome_source"]
        assert outcome["execution_summary"]["execution_path"]
        assert outcome["execution_summary"]["execution_decision"]
        assert outcome["resolution_status"]["outcome_status"]
        assert outcome["resolution_status"]["is_final"] is not None
        assert outcome["resolution_status"]["resolution_reason"]
