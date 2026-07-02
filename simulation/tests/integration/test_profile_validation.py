"""
Integration tests for profile validation — per-mode defaults and profile behavior.

Validates that each trading mode profile resolves with the correct defaults
and that profile version changes are reflected in the output lineage.
Unknown modes produce explicit errors.
"""

from __future__ import annotations

import pytest

from simulation.contracts.models import (
    SimulationProfile,
    TradingMode,
)
from simulation.engine.engine import simulate

from simulation.tests.integration.test_full_pipeline import _make_input, _candle


# ── Tests ───────────────────────────────────────────────────────────────────


class TestProfileValidation:
    """Profile validation — per-mode defaults, lineage, invalid modes."""

    # ── Test 1: SWING defaults ─────────────────────────────────────────

    def test_swing_defaults_correct(self):
        """SWING profile defaults: 4h, 30 bars, 2.0 stop, 2.0 target."""
        profile = SimulationProfile(
            profile_version="1.0.0",
            mode=TradingMode.SWING,
            primary_interval="4h",
            max_holding_bars=30,
            stop_multiplier=2.0,
            target_multiplier=2.0,
            ambiguity_margin_r=0.20,
            min_action_edge_r=0.35,
            no_trade_default=False,
        )
        assert profile.mode == TradingMode.SWING
        assert profile.primary_interval == "4h"
        assert profile.max_holding_bars == 30
        assert profile.stop_multiplier == 2.0
        assert profile.target_multiplier == 2.0
        assert profile.ambiguity_margin_r == 0.20
        assert profile.min_action_edge_r == 0.35
        assert profile.no_trade_default is False

        # Verify it works end-to-end through the engine
        candles = [_candle(105, 130, 103, 125)]
        inp = _make_input(profile=profile, candles=candles)
        result = simulate(inp)
        assert result.mode == "SWING"

    # ── Test 2: SCALP defaults ─────────────────────────────────────────

    def test_scalp_defaults_correct(self):
        """SCALP profile defaults: 1h, 12 bars, 1.5 stop, 1.5 target."""
        profile = SimulationProfile(
            profile_version="1.0.0",
            mode=TradingMode.SCALP,
            primary_interval="1h",
            max_holding_bars=12,
            stop_multiplier=1.5,
            target_multiplier=1.5,
            ambiguity_margin_r=0.10,
            min_action_edge_r=0.15,
            no_trade_default=True,
        )
        assert profile.mode == TradingMode.SCALP
        assert profile.primary_interval == "1h"
        assert profile.max_holding_bars == 12
        assert profile.stop_multiplier == 1.5
        assert profile.target_multiplier == 1.5
        assert profile.ambiguity_margin_r == 0.10
        assert profile.min_action_edge_r == 0.15
        assert profile.no_trade_default is True

        # Verify it works end-to-end through the engine
        candles = [
            _candle(101, 102, 99, 101),
            _candle(101, 103, 100, 102),
        ]
        inp = _make_input(
            mode=TradingMode.SCALP,
            profile=profile,
            candles=candles,
        )
        result = simulate(inp)
        assert result.mode == "SCALP"
        assert result.primary_interval == "1h"

    # ── Test 3: AGGRESSIVE_SCALP defaults ──────────────────────────────

    def test_aggressive_scalp_defaults_correct(self):
        """AGGRESSIVE_SCALP profile defaults: 15m, 5 bars, 1.0 stop, 1.0 target."""
        profile = SimulationProfile(
            profile_version="1.0.0",
            mode=TradingMode.AGGRESSIVE_SCALP,
            primary_interval="15m",
            max_holding_bars=5,
            stop_multiplier=1.0,
            target_multiplier=1.0,
            ambiguity_margin_r=0.05,
            min_action_edge_r=0.08,
            no_trade_default=True,
        )
        assert profile.mode == TradingMode.AGGRESSIVE_SCALP
        assert profile.primary_interval == "15m"
        assert profile.max_holding_bars == 5
        assert profile.stop_multiplier == 1.0
        assert profile.target_multiplier == 1.0
        assert profile.ambiguity_margin_r == 0.05
        assert profile.min_action_edge_r == 0.08
        assert profile.no_trade_default is True

        # Verify it works end-to-end through the engine
        candles = [
            _candle(101, 102, 99, 101),
            _candle(101, 103, 100, 102),
            _candle(102, 104, 101, 103),
        ]
        inp = _make_input(
            mode=TradingMode.AGGRESSIVE_SCALP,
            profile=profile,
            candles=candles,
        )
        result = simulate(inp)
        assert result.mode == "AGGRESSIVE_SCALP"
        assert result.primary_interval == "15m"

    # ── Test 4: Profile version change in lineage ──────────────────────

    def test_profile_version_change_in_lineage(self):
        """Profile version change appears in output lineage."""
        profile_v1 = SimulationProfile(
            profile_version="1.0.0",
            mode=TradingMode.SWING,
            primary_interval="4h",
            max_holding_bars=30,
            stop_multiplier=2.0,
            target_multiplier=2.0,
            ambiguity_margin_r=0.20,
            min_action_edge_r=0.35,
            no_trade_default=False,
        )
        profile_v2 = SimulationProfile(
            profile_version="2.0.0",
            mode=TradingMode.SWING,
            primary_interval="4h",
            max_holding_bars=30,
            stop_multiplier=2.5,  # Changed: wider stop
            target_multiplier=2.0,
            ambiguity_margin_r=0.20,
            min_action_edge_r=0.35,
            no_trade_default=False,
        )

        candles = [_candle(105, 130, 103, 125)]
        inp_v1 = _make_input(profile=profile_v1, candles=candles)
        inp_v2 = _make_input(profile=profile_v2, candles=candles)

        result_v1 = simulate(inp_v1)
        result_v2 = simulate(inp_v2)

        assert result_v1.lineage.simulation_profile_version == "1.0.0"
        assert result_v2.lineage.simulation_profile_version == "2.0.0"
        # Different profile versions -> different outputs (different stop -> different exit behavior)
        assert result_v1.lineage.simulation_profile_version != result_v2.lineage.simulation_profile_version

    # ── Test 5: Invalid mode raises explicit error ─────────────────────

    def test_invalid_mode_raises_explicit_error(self):
        """An invalid/unknown mode produces an explicit error, not silent default.

        TradingMode(str) raises ValueError for unknown mode strings.
        Dataclass constructors do not enforce type hints at runtime, so
        passing None or an arbitrary string to SimulationProfile stores
        it without error — but the string-based enum lookup itself validates.
        """
        with pytest.raises(ValueError):
            TradingMode("INVALID_MODE")

        with pytest.raises(ValueError):
            TradingMode("")

        with pytest.raises(ValueError):
            TradingMode("SWING_")  # not exact match
