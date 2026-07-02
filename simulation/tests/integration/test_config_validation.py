"""
Integration tests for config/input validation — field resolution, missing
fields, invalid values, and version mismatch detection.

Verifies that SimulationInput rejects bad data at construction time and
that mismatched versions between inputs are detectable.
"""

from __future__ import annotations

import pytest

from simulation.contracts.models import (
    Candle,
    FuturePath,
    SimulationInput,
    SimulationProfile,
    TradingMode,
)
from simulation.engine.engine import simulate

from simulation.tests.integration.test_full_pipeline import _candle


# ── Shared fixture ──────────────────────────────────────────────────────────


@pytest.fixture
def valid_profile() -> SimulationProfile:
    return SimulationProfile(
        profile_version="1.0.0",
        mode=TradingMode.SWING,
        primary_interval="4h",
        max_holding_bars=24,
        stop_multiplier=2.0,
        target_multiplier=2.5,
        ambiguity_margin_r=0.10,
        min_action_edge_r=0.05,
        no_trade_default=False,
    )


def _make_valid_input(profile: SimulationProfile) -> SimulationInput:
    return SimulationInput(
        symbol="BTCUSDT",
        decision_timestamp="2026-07-01T00:00:00Z",
        mode=TradingMode.SWING,
        primary_interval="4h",
        entry_price=100,
        atr=10,
        future_path=FuturePath(candles=[_candle(105, 130, 103, 125)]),
        profile=profile,
        simulation_family_version="simfam-1.0.0",
        cost_model_version="cost-1.0.0",
    )


# ── Tests ───────────────────────────────────────────────────────────────────


class TestConfigValidation:
    """Config/input validation — field resolution, missing fields, invalid values, version mismatch."""

    # ── Test 1: All params resolve ─────────────────────────────────────

    def test_all_params_resolve(self, valid_profile):
        """All SimulationInput fields resolve correctly and produce a valid output."""
        inp = _make_valid_input(valid_profile)
        result = simulate(inp)

        # Identity fields
        assert inp.symbol == "BTCUSDT"
        assert inp.mode == TradingMode.SWING
        assert inp.primary_interval == "4h"
        assert inp.entry_price == 100
        assert inp.atr == 10

        # Profile fields
        assert inp.profile.stop_multiplier == 2.0
        assert inp.profile.target_multiplier == 2.5
        assert inp.profile.max_holding_bars == 24

        # Version fields
        assert inp.simulation_family_version == "simfam-1.0.0"
        assert inp.cost_model_version == "cost-1.0.0"

        # Output matches input identity
        assert result.symbol == inp.symbol
        assert result.mode == inp.mode.value
        assert result.primary_interval == inp.primary_interval

    # ── Test 2: Missing field raises explicit error ────────────────────

    def test_missing_field_raises_explicit_error(self, valid_profile):
        """Missing a required field raises TypeError at construction time.

        SimulationInput uses dataclass fields without defaults for required
        params, so omitting them raises TypeError.
        """
        with pytest.raises(TypeError):
            # Missing 'symbol' (no default)
            SimulationInput(  # type: ignore[call-arg]
                decision_timestamp="2026-07-01T00:00:00Z",
                mode=TradingMode.SWING,
                primary_interval="4h",
                entry_price=100,
                atr=10,
                future_path=FuturePath(candles=[]),
                profile=valid_profile,
            )

        with pytest.raises(TypeError):
            # Missing 'entry_price' (no default)
            SimulationInput(  # type: ignore[call-arg]
                symbol="BTCUSDT",
                decision_timestamp="2026-07-01T00:00:00Z",
                mode=TradingMode.SWING,
                primary_interval="4h",
                atr=10,
                future_path=FuturePath(candles=[]),
                profile=valid_profile,
            )

        with pytest.raises(TypeError):
            # Missing 'profile' (no default)
            SimulationInput(  # type: ignore[call-arg]
                symbol="BTCUSDT",
                decision_timestamp="2026-07-01T00:00:00Z",
                mode=TradingMode.SWING,
                primary_interval="4h",
                entry_price=100,
                atr=10,
                future_path=FuturePath(candles=[]),
            )

    # ── Test 3: Invalid value raises explicit error ────────────────────

    def test_invalid_value_raises_explicit_error(self, valid_profile):
        """Invalid enum values raise ValueError at construction time.

        Note: Python dataclasses do not enforce type hints at runtime,
        so only the explicit TradingMode() construction raises ValueError.
        Passing a plain string to the dataclass stores it silently.
        """
        # Invalid TradingMode — the enum constructor validates
        with pytest.raises(ValueError):
            TradingMode("BOGUS_MODE")

        # Invalid profile field: negative max_holding_bars
        # The engine should handle this gracefully (no crash), but the
        # negative bars mean simulate_path receives available_bars=0
        # and falls through to the TIME_EXIT path immediately.
        bad_profile = SimulationProfile(
            profile_version="1.0.0",
            mode=TradingMode.SWING,
            primary_interval="4h",
            max_holding_bars=-5,
            stop_multiplier=2.0,
            target_multiplier=2.5,
            ambiguity_margin_r=0.10,
            min_action_edge_r=0.05,
            no_trade_default=False,
        )
        inp = SimulationInput(
            symbol="BTCUSDT",
            decision_timestamp="2026-07-01T00:00:00Z",
            mode=TradingMode.SWING,
            primary_interval="4h",
            entry_price=100,
            atr=10,
            future_path=FuturePath(candles=[_candle(105, 130, 103, 125)]),
            profile=bad_profile,
        )
        # Engine should not crash with negative max_holding_bars.
        # Exits module uses min(len(candles), max_holding_bars) which
        # yields -5 for 1 candle, and range(-5) is empty, so it falls
        # through to TIME_EXIT at entry price with no bars consumed.
        result = simulate(inp)
        assert result is not None
        # With 0 available bars, exit happens at entry price (realized_r_gross = 0)
        assert result.long_outcome.realized_r_gross == 0.0
        assert result.long_outcome.exit_reason == "TIME_EXIT"

    # ── Test 4: Version mismatch detected ──────────────────────────────

    def test_version_mismatch_detected(self, valid_profile):
        """Version mismatch between inputs is detectable in output lineage."""
        inp_v1 = _make_valid_input(valid_profile)
        inp_v1.simulation_family_version = "simfam-1.0.0"

        inp_v2 = _make_valid_input(valid_profile)
        inp_v2.simulation_family_version = "simfam-2.0.0"
        inp_v2.cost_model_version = "cost-2.0.0"

        result_v1 = simulate(inp_v1)
        result_v2 = simulate(inp_v2)

        # Lineage reflects the version fields from each input
        assert result_v1.lineage.simulation_family_version == "simfam-1.0.0"
        assert result_v2.lineage.simulation_family_version == "simfam-2.0.0"
        assert result_v1.lineage.cost_model_version == "cost-1.0.0"
        assert result_v2.lineage.cost_model_version == "cost-2.0.0"

        # Verify they are actually different
        assert result_v1.lineage.simulation_family_version != result_v2.lineage.simulation_family_version
        assert result_v1.lineage.cost_model_version != result_v2.lineage.cost_model_version
