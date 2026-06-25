"""Tests for MarketDataAdapter — bridges KlineRecords to SimulationInput."""

from __future__ import annotations

from typing import List

import pytest

from lib.market_data.contracts import KlineRecord
from simulation.adapters.market_data_adapter import MarketDataAdapter
from simulation.contracts.models import SimulationProfile, TradingMode


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def fixture_profile() -> SimulationProfile:
    """Standard SWING profile for testing."""
    return SimulationProfile(
        profile_version="1.0.0",
        mode=TradingMode.SWING,
        primary_interval="4h",
        max_holding_bars=24,
        stop_multiplier=2.0,
        target_multiplier=3.0,
        ambiguity_margin_r=0.1,
        min_action_edge_r=0.05,
        no_trade_default=False,
    )


@pytest.fixture
def fixture_klines_100() -> List[KlineRecord]:
    """100 synthetic BTCUSDT 4h klines with consistent up-trend."""
    records: List[KlineRecord] = []
    base_price = 50000.0
    for i in range(100):
        records.append(
            KlineRecord(
                symbol="BTCUSDT",
                timestamp=1_000_000 + i * 240 * 60_000,
                open=float(base_price + i * 10),
                high=float(base_price + i * 10 + 200),
                low=float(base_price + i * 10 - 200),
                close=float(base_price + i * 10),
                volume=100.0,
                quote_volume=5_010_000.0,
                trade_count=1000,
                taker_buy_volume=55.0,
                taker_buy_quote_volume=2_755_500.0,
                interval="4h",
                source="binance",
                is_closed=True,
            )
        )
    return records


@pytest.fixture
def fixture_klines_10() -> List[KlineRecord]:
    """Only 10 klines — insufficient for lookback+forward."""
    records: List[KlineRecord] = []
    base_price = 50000.0
    for i in range(10):
        records.append(
            KlineRecord(
                symbol="ETHUSDT",
                timestamp=2_000_000 + i * 60 * 60_000,
                open=float(base_price + i * 5),
                high=float(base_price + i * 5 + 100),
                low=float(base_price + i * 5 - 100),
                close=float(base_price + i * 5),
                volume=50.0,
                quote_volume=2_500_000.0,
                trade_count=500,
                taker_buy_volume=25.0,
                taker_buy_quote_volume=1_250_000.0,
                interval="1h",
                source="binance",
                is_closed=True,
            )
        )
    return records


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestMarketDataAdapter:
    """MarketDataAdapter unit tests."""

    def test_adapt_produces_expected_count(
        self,
        fixture_klines_100: List[KlineRecord],
        fixture_profile: SimulationProfile,
    ):
        """100 records, lookback=20, forward=48 -> 100-20-48 = 32 inputs."""
        adapter = MarketDataAdapter()
        inputs = adapter.adapt_klines(fixture_klines_100, fixture_profile)
        assert len(inputs) == 32, (
            f"Expected 32 decision points, got {len(inputs)}"
        )

    def test_entry_price_is_bar_close(
        self,
        fixture_klines_100: List[KlineRecord],
        fixture_profile: SimulationProfile,
    ):
        """Entry price should equal the close of the decision bar."""
        adapter = MarketDataAdapter()
        inputs = adapter.adapt_klines(fixture_klines_100, fixture_profile)
        for idx, sim_input in enumerate(inputs):
            # Decision bar index = lookback_bars + idx
            decision_idx = 20 + idx
            expected_close = fixture_klines_100[decision_idx].close
            assert sim_input.entry_price == expected_close, (
                f"Input {idx}: entry_price {sim_input.entry_price} != "
                f"close {expected_close} at bar {decision_idx}"
            )

    def test_atr_is_positive(
        self,
        fixture_klines_100: List[KlineRecord],
        fixture_profile: SimulationProfile,
    ):
        """ATR should be a positive number for valid data."""
        adapter = MarketDataAdapter()
        inputs = adapter.adapt_klines(fixture_klines_100, fixture_profile)
        for idx, sim_input in enumerate(inputs):
            assert sim_input.atr > 0, (
                f"Input {idx}: ATR={sim_input.atr} is not positive"
            )

    def test_future_path_has_correct_length(
        self,
        fixture_klines_100: List[KlineRecord],
        fixture_profile: SimulationProfile,
    ):
        """FuturePath should contain forward_bars candles."""
        adapter = MarketDataAdapter()
        inputs = adapter.adapt_klines(fixture_klines_100, fixture_profile)
        for idx, sim_input in enumerate(inputs):
            assert len(sim_input.future_path.candles) == 48, (
                f"Input {idx}: expected 48 future candles, "
                f"got {len(sim_input.future_path.candles)}"
            )

    def test_insufficient_data_returns_empty(
        self,
        fixture_klines_10: List[KlineRecord],
        fixture_profile: SimulationProfile,
    ):
        """Insufficient klines should produce an empty result."""
        adapter = MarketDataAdapter()
        inputs = adapter.adapt_klines(fixture_klines_10, fixture_profile)
        assert inputs == []

    def test_symbol_and_interval_propagated(
        self,
        fixture_klines_100: List[KlineRecord],
        fixture_profile: SimulationProfile,
    ):
        """Symbol and primary_interval should match the source data."""
        adapter = MarketDataAdapter()
        inputs = adapter.adapt_klines(fixture_klines_100, fixture_profile)
        for sim_input in inputs:
            assert sim_input.symbol == "BTCUSDT"
            assert sim_input.primary_interval == "4h"

    def test_timestamp_is_iso_format(
        self,
        fixture_klines_100: List[KlineRecord],
        fixture_profile: SimulationProfile,
    ):
        """Decision timestamps should be valid ISO-8601 strings."""
        adapter = MarketDataAdapter()
        inputs = adapter.adapt_klines(fixture_klines_100, fixture_profile)
        for sim_input in inputs:
            ts = sim_input.decision_timestamp
            assert "T" in ts, f"Timestamp '{ts}' is not ISO format"

    def test_profile_is_carried_through(
        self,
        fixture_klines_100: List[KlineRecord],
        fixture_profile: SimulationProfile,
    ):
        """The passed profile should be attached to each SimulationInput."""
        adapter = MarketDataAdapter()
        inputs = adapter.adapt_klines(fixture_klines_100, fixture_profile)
        for sim_input in inputs:
            assert sim_input.profile is fixture_profile

    def test_custom_lookback(
        self,
        fixture_klines_100: List[KlineRecord],
        fixture_profile: SimulationProfile,
    ):
        """Custom lookback_bars should affect count and ATR."""
        adapter = MarketDataAdapter()
        inputs = adapter.adapt_klines(
            fixture_klines_100, fixture_profile, lookback_bars=30
        )
        assert len(inputs) == 100 - 30 - 48, (
            f"Expected {100 - 30 - 48} inputs, got {len(inputs)}"
        )
