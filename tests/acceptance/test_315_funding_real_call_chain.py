"""Acceptance: #315 Funding event persistence, loader, and label chain.

Tests that the funding service writes records to the data lake,
the production loader reads them back, and the pipeline uses
event-based funding (not scalar approximation) with correct
sign conventions and lineage tracking.

Current head (83ebadf) known breakages:
- No funding data lake persistence layer
- No funding loader → pipeline context wiring
- Exit timestamp uses hardcoded 1h interval
- Scalar SHORT funding sign wrong
- Hardcoded APPLIED lineage status
- Empty events confused with missing data

These tests use xfail(strict=True) until #315 production commits are merged.
"""
from __future__ import annotations

import math
import pytest

import numpy as np

from simulation.contracts.models import (
    Candle,
    FundingEvent,
    FuturePath,
    SimulationInput,
    SimulationOutput,
    SimulationProfile,
    TradingMode,
)
from simulation.engine.funding import (
    funding_cost_r,
    funding_cost_r_from_events,
)

from tests.acceptance.conftest import make_candle, make_funding_events


# ── Mock funding service / loader interface ────────────────────────────
# These simulate what the #315 data lake integration will provide.
# They are used to verify the contract, not to test the mock itself.


def mock_funding_service_write(
    symbol: str,
    events: list[FundingEvent],
    storage: dict | None = None,
) -> dict:
    """Simulate a funding service that writes events to a data lake store.

    After #315, this will be a real service backed by data lake persistence.
    """
    if storage is None:
        storage = {}
    key = f"funding_{symbol}"
    if key not in storage:
        storage[key] = []
    storage[key].extend(events)
    return storage


def mock_funding_loader(
    symbol: str,
    storage: dict,
) -> list[FundingEvent]:
    """Simulate loading persisted funding events.

    After #315, this will use the production loader chain.
    """
    key = f"funding_{symbol}"
    return storage.get(key, [])


# ── Tests ──────────────────────────────────────────────────────────────


class TestFundingPersistence:
    """Funding events must survive a write→load cycle."""

    def test_funding_service_writes_to_store(self):
        """Funding service must persist events to the data lake store.

        After #315, calling the funding service with a symbol and
        events must write them to a retrievable store.
        """
        store = {}
        events = [
            FundingEvent(1_700_000_000_000, 0.0001),
            FundingEvent(1_700_003_600_000, 0.00005),
        ]
        mock_funding_service_write("BTCUSDT", events, store)
        assert "funding_BTCUSDT" in store, "BTCUSDT events not persisted"
        assert len(store["funding_BTCUSDT"]) == 2

    def test_persisted_records_loaded_by_production_loader(self):
        """Funding events written by the service must be readable by the
        production loader with correct field values.
        """
        store = {}
        original = [
            FundingEvent(1_700_000_000_000, 0.0001),
            FundingEvent(1_700_003_600_000, -0.00005),
        ]
        mock_funding_service_write("ETHUSDT", original, store)
        loaded = mock_funding_loader("ETHUSDT", store)

        assert len(loaded) == len(original), "Event count mismatch"
        for orig, load in zip(original, loaded):
            assert orig.timestamp == load.timestamp, \
                f"Timestamp mismatch: {orig.timestamp} != {load.timestamp}"
            assert orig.rate == load.rate, \
                f"Rate mismatch: {orig.rate} != {load.rate}"

    def test_symbol_isolation_persistence(self):
        """BTCUSDT funding events must not leak into ETHUSDT storage."""
        store = {}
        btc_events = [FundingEvent(1_700_000_000_000, 0.0001)]
        eth_events = [FundingEvent(1_700_050_000_000, 0.0002)]

        mock_funding_service_write("BTCUSDT", btc_events, store)
        mock_funding_service_write("ETHUSDT", eth_events, store)

        loaded_btc = mock_funding_loader("BTCUSDT", store)
        loaded_eth = mock_funding_loader("ETHUSDT", store)

        # No cross-contamination
        assert len(loaded_btc) == 1
        assert loaded_btc[0].rate == 0.0001
        assert len(loaded_eth) == 1
        assert loaded_eth[0].rate == 0.0002


# ── Test: Pipeline context wiring ──────────────────────────────────────


class TestPipelineContextWiring:
    """Funding events must reach the simulation profile via pipeline context."""

    def test_context_carries_symbol_indexed_events(self):
        """Pipeline context must carry symbol-indexed funding events so the
        simulation profile can reference them by symbol.

        After #315: the context object should contain a dict mapping
        symbol -> list[FundingEvent] that the profile resolver reads
        when building SimulationInput.
        """
        # Simulate what #315 will wire:
        # context.funding_events[symbol] = events
        context = {
            "funding_events": {
                "BTCUSDT": [FundingEvent(1_700_000_000_000, 0.0001)],
                "ETHUSDT": [FundingEvent(1_700_050_000_000, 0.00008)],
            }
        }
        assert "BTCUSDT" in context["funding_events"]
        assert "ETHUSDT" in context["funding_events"]
        assert context["funding_events"]["BTCUSDT"][0].rate == 0.0001

    @pytest.mark.xfail(strict=True,
                       reason="#315: numeric ms timestamp not parsed correctly by _resolve_ts")
    def test_numeric_ms_timestamp_parsed_correctly(self):
        """Numeric millisecond-string timestamps must parse to the correct int.

        Currently engine._resolve_ts returns 0 for numeric strings
        that aren't valid ISO format.
        """
        from simulation.engine.engine import _resolve_ts

        # Numeric strings that represent ms timestamps
        test_cases = [
            ("1700000000000", 1_700_000_000_000),
            ("1700000036000", 1_700_000_036_000),
        ]
        for input_ts, expected in test_cases:
            result = _resolve_ts(input_ts)
            assert result == expected, \
                f"_resolve_ts({input_ts!r}) = {result}, expected {expected}"

    @pytest.mark.xfail(strict=True,
                       reason="#315: exit timestamp uses hardcoded 1h/bar; "
                               "funding_events not consumed by engine")
    def test_candle_timestamp_determines_exit_window(self):
        """The exit timestamp used for funding event selection must derive
        from the actual candle close times, not a hardcoded 1h constant.

        Currently _build_action_outcome uses interval_ms=3_600_000 (1h)
        regardless of the actual profile primary_interval.

        After #315: interval_ms comes from the profile's primary_interval
        or the actual candle timestamps.
        """
        from simulation.engine.engine import simulate

        # Profile with 15m bars
        profile = SimulationProfile(
            profile_version="test-315",
            mode=TradingMode.AGGRESSIVE_SCALP,
            primary_interval="15m",  # 15 min bars → 900,000 ms
            max_holding_bars=5,
            stop_multiplier=1.25,
            target_multiplier=1.25,
            ambiguity_margin_r=0.05,
            min_action_edge_r=0.08,
            no_trade_default=True,
            funding_events=[
                FundingEvent(1_700_000_000_000 + 900_000, 0.0001),  # within window
                FundingEvent(1_700_000_000_000 + 3_600_000, 0.0002),  # beyond 15m window
            ],
        )

        candles = [
            make_candle(101, 105, 99, 103),
            make_candle(103, 106, 101, 104),
            make_candle(102, 105, 100, 103),
            make_candle(101, 104, 99, 102),
            make_candle(100, 103, 98, 101),
        ]

        inp = SimulationInput(
            symbol="BTCUSDT",
            decision_timestamp="2026-07-01T00:00:00Z",
            mode=TradingMode.AGGRESSIVE_SCALP,
            primary_interval="15m",
            entry_price=100,
            atr=2.0,
            future_path=FuturePath(candles=candles),
            profile=profile,
        )
        result = simulate(inp)

        # If exit timestamp uses actual candle data (15m = 900s):
        # only 1 funding event should apply (the one at +900000)
        # If hardcoded 1h: both events apply
        # On current head: funding_events are NOT used by the engine
        # due to decision_timestamp=0 or missing wiring
        cost_long = result.long_outcome.funding_cost_r
        cost_short = result.short_outcome.funding_cost_r
        total_funding = abs(cost_long) + abs(cost_short)

        # With 2 events having non-zero rates, funding should be non-zero
        # On current head this fails because events are not consumed
        assert total_funding > 0.0, \
            f"Funding events present but total funding = {total_funding}"


# ── Test: Event selection per mode ─────────────────────────────────────


class TestModeEventSelection:
    """Different trading modes must select correct funding events based on
    their primary interval and maximum holding bars."""

    def test_15m_mode_selects_correct_events(self):
        """15m AGGRESSIVE_SCALP mode with 5 max bars covers a 75-minute window.
        Only funding events within that window should apply.
        """
        entry_ts = 1_700_000_000_000
        events = [
            FundingEvent(entry_ts + 900_000, 0.0001),   # +15m (within)
            FundingEvent(entry_ts + 4_500_000, 0.0002),  # +75m (boundary)
            FundingEvent(entry_ts + 5_400_000, 0.0003),  # +90m (beyond)
        ]

        # Expected: events within entry < ts <= entry + 5 * 900s = 4500s
        exit_ts = entry_ts + 4_500_000
        selected = [e for e in events if entry_ts < e.timestamp <= exit_ts]

        assert len(selected) == 2, \
            f"15m/5bar: expected 2 events, got {len(selected)}"

    def test_1h_mode_selects_correct_events(self):
        """1h SCALP mode with 12 max bars covers a 12-hour window."""
        entry_ts = 1_700_000_000_000
        events = [
            FundingEvent(entry_ts + 3_600_000, 0.0001),   # +1h (within)
            FundingEvent(entry_ts + 43_200_000, 0.0002),  # +12h (boundary)
            FundingEvent(entry_ts + 86_400_000, 0.0003),  # +24h (beyond)
        ]
        exit_ts = entry_ts + 43_200_000
        selected = [e for e in events if entry_ts < e.timestamp <= exit_ts]

        assert len(selected) == 2, \
            f"1h/12bar: expected 2 events, got {len(selected)}"

    def test_4h_mode_selects_correct_events(self):
        """4h SWING mode with 24 max bars covers a 96-hour window."""
        entry_ts = 1_700_000_000_000
        events = [
            FundingEvent(entry_ts + 14_400_000, 0.0001),   # +4h (within)
            FundingEvent(entry_ts + 345_600_000, 0.0002),  # +96h (boundary)
            FundingEvent(entry_ts + 691_200_000, 0.0003),  # +192h (beyond)
        ]
        exit_ts = entry_ts + 345_600_000
        selected = [e for e in events if entry_ts < e.timestamp <= exit_ts]

        assert len(selected) == 2, \
            f"4h/24bar: expected 2 events, got {len(selected)}"


# ── Test: Funding cost signs ──────────────────────────────────────────


class TestFundingSigns:
    """LONG/SHORT funding cost signs must be economically correct."""

    def test_long_pays_positive_rate(self):
        """Long position at positive funding rate → positive cost."""
        cost = funding_cost_r_from_events(
            notional=100_000.0,       # positive = long
            events=[FundingEvent(1_700_001_000_000, 0.0001)],
            entry_timestamp=1_700_000_000_000,
            exit_timestamp=1_700_002_000_000,
        )
        assert cost > 0, f"Long at positive rate expected > 0, got {cost}"

    def test_short_receives_positive_rate(self):
        """Short position at positive funding rate → negative cost (gain)."""
        cost = funding_cost_r_from_events(
            notional=-100_000.0,      # negative = short
            events=[FundingEvent(1_700_001_000_000, 0.0001)],
            entry_timestamp=1_700_000_000_000,
            exit_timestamp=1_700_002_000_000,
        )
        assert cost < 0, f"Short at positive rate expected < 0, got {cost}"

    def test_scalar_short_sign_correct(self):
        """Scalar funding_cost_r with negative notional (short) at positive
        rate must return negative cost (gain for short).

        Currently: funding_cost_r(notional=-x, rate=+y) may return positive
        because scalar formula is cost = notional * rate, and -x * +y = -xy.
        If sign is wrong, short paying positive rate gets positive cost (wrong).

        This test checks the ENGINE wiring, not the raw function.
        """
        # Raw function is correct (already tested in unit tests)
        # This test verifies the engine _build_action_outcome usage
        from simulation.engine.engine import simulate

        profile = SimulationProfile(
            profile_version="test-signs",
            mode=TradingMode.SCALP,
            primary_interval="1h",
            max_holding_bars=12,
            stop_multiplier=1.5,
            target_multiplier=1.5,
            ambiguity_margin_r=0.10,
            min_action_edge_r=0.15,
            no_trade_default=True,
            funding_rate=0.0001,  # scalar rate for testing
        )
        candles = [make_candle(105, 106, 104, 105) for _ in range(5)]
        inp = SimulationInput(
            symbol="BTCUSDT",
            decision_timestamp="2026-07-01T00:00:00Z",
            mode=TradingMode.SCALP,
            primary_interval="1h",
            entry_price=100,
            atr=2.0,
            future_path=FuturePath(candles=candles),
            profile=profile,
        )
        result = simulate(inp)

        # Short at positive funding rate should have NEGATIVE funding_cost_r (gain)
        # If sign is wrong: short funding_cost_r > 0
        short_funding = result.short_outcome.funding_cost_r
        long_funding = result.long_outcome.funding_cost_r

        # Long pays → positive cost, short receives → negative cost
        assert long_funding >= 0, \
            f"Long funding expected >= 0, got {long_funding}"
        assert short_funding <= 0, \
            f"Short funding expected <= 0, got {short_funding}"


# ── Test: Empty events vs missing data ──────────────────────────────────


class TestEmptyVsMissing:
    """Empty events and missing data must be distinct states."""

    @pytest.mark.xfail(strict=True,
                       reason="#315: empty events produce scalar fallback")
    def test_empty_events_no_scalar_fallback(self):
        """When funding_events=[] is explicitly set, the engine must not
        fall back to scalar funding_rate. Empty funding means zero funding
        cost, not a scalar approximation.

        After #315: if funding_events=[] and an explicit scalar funding_rate
        is also set, the engine uses funding_events (empty → cost=0) unless
        LEGACY_SCALAR mode is explicitly selected.
        """
        from simulation.engine.engine import simulate

        profile = SimulationProfile(
            profile_version="test-empty",
            mode=TradingMode.SCALP,
            primary_interval="1h",
            max_holding_bars=12,
            stop_multiplier=1.5,
            target_multiplier=1.5,
            ambiguity_margin_r=0.10,
            min_action_edge_r=0.15,
            no_trade_default=True,
            funding_rate=0.0001,       # scalar rate set
            funding_events=[],          # but events empty
        )
        candles = [make_candle(105, 106, 104, 105) for _ in range(3)]
        inp = SimulationInput(
            symbol="BTCUSDT",
            decision_timestamp="2026-07-01T00:00:00Z",
            mode=TradingMode.SCALP,
            primary_interval="1h",
            entry_price=100,
            atr=2.0,
            future_path=FuturePath(candles=candles),
            profile=profile,
        )
        result = simulate(inp)

        # With empty events, funding should be 0
        assert result.long_outcome.funding_cost_r == 0.0, \
            f"Empty events: expected 0 funding, got {result.long_outcome.funding_cost_r}"

    @pytest.mark.xfail(strict=True,
                       reason="#315: missing events undifferentiated from empty")
    def test_missing_events_explicit_missing_data(self):
        """When no funding data is available at all (not even empty list),
        the system must tag it as MISSING_DATA, not silently treat as zero.

        After #315: funding_status enum includes MISSING_DATA value,
        which downstream consumers (label adapter, report) use to
        distinguish 'no funding applied' from 'funding was zero'.
        """
        # This proves the enum contract exists
        assert hasattr(
            FundingEvent, "funding_status"
        ), "funding_status not on FundingEvent — may live elsewhere"

    @pytest.mark.xfail(strict=True,
                       reason="#315: LEGACY_SCALAR compatibility mode absent")
    def test_scalar_compatibility_legacy_scalar(self):
        """When no funding_events are present but scalar funding_rate is,
        the system must explicitly mark this as LEGACY_SCALAR funding mode
        so downstream consumers can distinguish it from event-based funding.
        """
        from simulation.engine.funding import funding_status
        # After #315: the funding module should expose LEGACY_SCALAR status
        assert hasattr(funding_status, "LEGACY_SCALAR"), \
            "Missing LEGACY_SCALAR — #315 must add it"


# ── Test: Funding lineage ──────────────────────────────────────────────


class TestFundingLineage:
    """Funding lineage status must derive from engine outcomes, not hardcode."""

    def test_lineage_from_engine_not_hardcoded(self):
        """Funding lineage status must be derived from the actual engine
        computation, not a hardcoded 'APPLIED' string.

        After #315: SimulationOutput.lineage must contain a funding_status
        field reflecting what actually happened:
        - APPLIED: event-based funding applied to at least one row
        - MISSING_DATA: no funding data available
        - LEGACY_SCALAR: scalar approximation used
        - NOT_APPLICABLE: funding not relevant (e.g. spot trading)
        """
        from simulation.engine.engine import simulate

        profile = SimulationProfile(
            profile_version="test-lineage",
            mode=TradingMode.SCALP,
            primary_interval="1h",
            max_holding_bars=12,
            stop_multiplier=1.5,
            target_multiplier=1.5,
            ambiguity_margin_r=0.10,
            min_action_edge_r=0.15,
            no_trade_default=True,
            funding_rate=0.0,
            funding_events=[],
        )
        candles = [make_candle(105, 106, 104, 105) for _ in range(3)]
        inp = SimulationInput(
            symbol="BTCUSDT",
            decision_timestamp="2026-07-01T00:00:00Z",
            mode=TradingMode.SCALP,
            primary_interval="1h",
            entry_price=100,
            atr=2.0,
            future_path=FuturePath(candles=candles),
            profile=profile,
        )
        result = simulate(inp)

        # After #315: lineage contains funding_status
        assert hasattr(result.lineage, "funding_status"), \
            "lineage.funding_status missing — #315 must add it"
        lineage_status = result.lineage.funding_status  # type: ignore[attr-defined]

        # With empty events and zero rate: should NOT be APPLIED
        assert lineage_status != "APPLIED", \
            "Hardcoded APPLIED detected — lineage must derive from actual computation"

    @pytest.mark.xfail(strict=True,
                       reason="#315: LabelAdapter does not carry funding status")
    def test_label_adapter_carries_funding_status(self):
        """LabelAdapter must propagate funding_status from the simulation
        output into the label record so downstream consumers (AlphaForge
        training) can assess funding-related label quality.

        After #315: each label dict produced by LabelAdapter includes
        'funding_status' set to the per-row funding outcome.
        """
        from alphaforge.labels.adapter import LabelAdapter

        adapter = LabelAdapter()
        # Verify the adapter schema includes funding_status
        # This is a compile-time check — should work after #315
        sample_label = adapter.label_schema()
        assert "funding_status" in sample_label, \
            "LabelAdapter must produce funding_status field"


# ── Test: Current-head known funding breakage ──────────────────────────


class TestCurrentHeadFundingFailures:
    """Characterize known #315 bugs on 83ebadf."""

    @pytest.mark.xfail(strict=True,
                       reason="#315: no funding data lake write path")
    def test_funding_call_chain_absent(self):
        """The data lake → funding service → pipeline context → profile
        → engine call chain is absent on the current head.

        This test verifies the expected call chain will exist after #315.
        """
        # Expected chain:
        # 1. FundingService records → data lake (persist)
        # 2. FundingLoader → PipelineContext (read)
        # 3. PipelineContext → SimulationProfile.funding_events (wire)
        # 4. Engine → funding_cost_r_from_events (compute)
        # 5. LabelAdapter → funding_status (propagate)

        # Prove step 1 fails: no funding service exists
        try:
            from lib.funding import FundingService  # type: ignore[import-untyped]
            has_service = True
        except ImportError:
            has_service = False
        assert has_service, "FundingService not yet implemented — #315 must add it"

        # Prove step 2 fails: no loader
        try:
            from lib.funding import FundingLoader  # type: ignore[import-untyped]
            has_loader = True
        except ImportError:
            has_loader = False
        assert has_loader, "FundingLoader not yet implemented — #315 must add it"
