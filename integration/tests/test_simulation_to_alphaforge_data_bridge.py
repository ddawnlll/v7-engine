"""
Integration test: full bridge from KlineRecords through to AlphaForgeLabel.

Tests the chain:
  fixture klines
  -> MarketDataAdapter.adapt_klines()
  -> BatchSimulator.run()
  -> LabelAdapter.adapt_simulation_output()
  -> valid AlphaForgeLabel

Verifies the data pipeline end-to-end without network or exchange access.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Dict, List, Any

import pytest

from alphaforge.labels.adapter import LabelAdapter
from lib.market_data.contracts import KlineRecord
from simulation.adapters.market_data_adapter import MarketDataAdapter
from simulation.contracts.models import (
    SimulationInput,
    SimulationOutput,
    SimulationProfile,
    TradingMode,
)
from simulation.engine.batch import BatchSimulator


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

REQUIRED_LABEL_FIELDS = {
    "symbol",
    "timestamp",
    "mode",
    "best_action_label",
    "label_validity",
    "long_R_gross",
    "short_R_gross",
    "long_R_net",
    "short_R_net",
    "action_gap_R",
    "regret_R",
    "is_ambiguous",
    "no_trade_quality",
    "resolution_status",
    "saved_loss_r",
    "missed_opportunity_r",
}


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
def fixture_profile() -> SimulationProfile:
    """Standard SWING profile for data bridge testing."""
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


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSimulationToAlphaForgeDataBridge:
    """End-to-end data bridge integration test."""

    def test_adapter_produces_inputs(
        self,
        fixture_klines_100: List[KlineRecord],
        fixture_profile: SimulationProfile,
    ):
        """Step 1: MarketDataAdapter should produce valid SimulationInputs."""
        adapter = MarketDataAdapter()
        inputs = adapter.adapt_klines(fixture_klines_100, fixture_profile)
        assert len(inputs) > 0, "Adapter produced zero inputs from 100 klines"
        for sim_input in inputs:
            assert isinstance(sim_input, SimulationInput)
            assert sim_input.atr > 0

    def test_batch_produces_outputs(
        self,
        fixture_klines_100: List[KlineRecord],
        fixture_profile: SimulationProfile,
    ):
        """Step 2: BatchSimulator should produce valid SimulationOutputs."""
        adapter = MarketDataAdapter()
        inputs = adapter.adapt_klines(fixture_klines_100, fixture_profile)

        simulator = BatchSimulator()
        outputs = simulator.run(inputs)
        assert len(outputs) > 0, "Batch produced zero outputs"
        for output in outputs:
            assert isinstance(output, SimulationOutput)
            assert output.best_action in (
                "LONG_NOW", "SHORT_NOW", "NO_TRADE", "AMBIGUOUS_STATE"
            )

    def test_label_has_valid_best_action(
        self,
        fixture_klines_100: List[KlineRecord],
        fixture_profile: SimulationProfile,
    ):
        """Step 3: Labels should have valid best_action values."""
        adapter = MarketDataAdapter()
        inputs = adapter.adapt_klines(fixture_klines_100, fixture_profile)

        simulator = BatchSimulator()
        outputs = simulator.run(inputs)

        label_adapter = LabelAdapter()
        for output in outputs:
            label = label_adapter.adapt_simulation_output(asdict(output))
            assert label["best_action_label"] in (
                "LONG_NOW", "SHORT_NOW", "NO_TRADE", "AMBIGUOUS_STATE"
            ), f"Unexpected best_action: {label['best_action_label']}"

    def test_label_has_required_fields(
        self,
        fixture_klines_100: List[KlineRecord],
        fixture_profile: SimulationProfile,
    ):
        """Step 4: Each label should have all required AlphaForgeLabel fields."""
        adapter = MarketDataAdapter()
        inputs = adapter.adapt_klines(fixture_klines_100, fixture_profile)

        simulator = BatchSimulator()
        outputs = simulator.run(inputs)

        label_adapter = LabelAdapter()
        for output in outputs:
            label = label_adapter.adapt_simulation_output(asdict(output))
            missing = REQUIRED_LABEL_FIELDS - set(label.keys())
            assert not missing, f"Label missing required fields: {missing}"

    def test_full_pipeline_no_failures(
        self,
        fixture_klines_100: List[KlineRecord],
        fixture_profile: SimulationProfile,
    ):
        """Full pipeline should complete without exceptions."""
        adapter = MarketDataAdapter()
        inputs = adapter.adapt_klines(fixture_klines_100, fixture_profile)

        simulator = BatchSimulator()
        outputs = simulator.run(inputs)

        label_adapter = LabelAdapter()
        labels: List[Dict[str, Any]] = []
        for output in outputs:
            label = label_adapter.adapt_simulation_output(asdict(output))
            labels.append(label)

        # Verify every label is well-formed
        for label in labels:
            assert isinstance(label["long_R_net"], float)
            assert isinstance(label["short_R_net"], float)
            # label_validity should be one of the known values
            assert label["label_validity"] in (
                "valid", "invalid", "ambiguous_excluded"
            )

        # All outputs should produce labels
        assert len(labels) == len(outputs)
