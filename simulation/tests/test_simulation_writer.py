"""Tests for SimulationWriter — Parquet persistence with checksum."""

from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path
from typing import Generator, List

import pandas as pd
import pytest

from simulation.contracts.models import (
    ActionOutcome,
    Candle,
    FuturePath,
    NoTradeOutcome,
    PathMetrics,
    SimulationInput,
    SimulationLineage,
    SimulationOutput,
    SimulationProfile,
    TradingMode,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fixture_outputs_3() -> List[SimulationOutput]:
    """Three diverse SimulationOutputs for writer testing."""
    profile = SimulationProfile(
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

    outputs: List[SimulationOutput] = []
    for idx, (symbol, price, atr) in enumerate([
        ("BTCUSDT", 50000.0, 500.0),
        ("ETHUSDT", 3000.0, 30.0),
        ("SOLUSDT", 150.0, 5.0),
    ]):
        candles = [
            Candle(open=price + i * 10, high=price + i * 10 + 100,
                   low=price + i * 10 - 100, close=price + i * 10 + 50)
            for i in range(48)
        ]
        future_path = FuturePath(candles=candles, expected_bars=48)
        sim_input = SimulationInput(
            symbol=symbol,
            decision_timestamp=f"2024-01-01T00:00:{idx:02d}",
            mode=profile.mode,
            primary_interval=profile.primary_interval,
            entry_price=price,
            atr=atr,
            future_path=future_path,
            profile=profile,
        )

        # Build a minimal SimulationOutput directly to control fields
        output = SimulationOutput(
            simulation_run_id=f"test-run-{idx}",
            symbol=symbol,
            decision_timestamp=f"2024-01-01T00:00:{idx:02d}",
            mode="SWING",
            primary_interval="4h",
            resolution_status="COMPLETE",
            long_outcome=ActionOutcome(
                action="LONG_NOW",
                realized_r_gross=1.5,
                realized_r_net=1.3,
                fee_cost_r=0.1,
                slippage_cost_r=0.1,
                total_cost_r=0.2,
                exit_reason="TARGET_HIT",
                exit_price=price + 1500,
                exit_bar_index=10,
                hold_duration_bars=10,
                action_utility=1.2,
                path_metrics=PathMetrics(
                    mfe=2000.0,
                    mae=500.0,
                    mfe_r=4.0,
                    mae_r=1.0,
                    time_to_mfe=5,
                    time_to_mae=2,
                    path_quality_score=0.80,
                    path_quality_bucket="HIGH",
                ),
            ),
            short_outcome=ActionOutcome(
                action="SHORT_NOW",
                realized_r_gross=-2.0,
                realized_r_net=-2.2,
                fee_cost_r=0.1,
                slippage_cost_r=0.1,
                total_cost_r=0.2,
                exit_reason="STOP_HIT",
                exit_price=price + 1000,
                exit_bar_index=5,
                hold_duration_bars=5,
                action_utility=-2.5,
            ),
            no_trade_outcome=NoTradeOutcome(
                saved_loss_r=0.0,
                saved_loss_score=0.0,
                missed_opportunity_r=1.3,
                missed_opportunity_score=0.43,
                no_trade_quality="MISSED_OPPORTUNITY",
                was_correct_skip=False,
            ),
            best_action="LONG_NOW",
            action_gap_r=0.5,
            regret_r=0.0,
            is_ambiguous=False,
            lineage=SimulationLineage(
                simulation_family_version="simfam-1.0.0",
                simulation_profile_version="1.0.0",
                cost_model_version="cost-1.0.0",
                adapter_kind="TRAINING",
            ),
        )
        outputs.append(output)

    return outputs


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Temporary directory for parquet output."""
    with tempfile.TemporaryDirectory() as tmp:
        yield Path(tmp)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSimulationWriter:
    """SimulationWriter unit tests."""

    def test_write_parquet_readable(
        self,
        fixture_outputs_3: List[SimulationOutput],
        temp_dir: Path,
    ):
        """Written Parquet should be readable with expected row count."""
        from simulation.engine.writer import SimulationWriter

        path = str(temp_dir / "sim_output.parquet")
        writer = SimulationWriter()
        writer.write(fixture_outputs_3, path)

        assert os.path.exists(path), "Parquet file was not created"

        # Read back and verify
        df = pd.read_parquet(path)
        assert len(df) == 3, f"Expected 3 rows, got {len(df)}"

    def test_flat_contains_top_level_fields(
        self,
        fixture_outputs_3: List[SimulationOutput],
        temp_dir: Path,
    ):
        """Flattened output should include top-level simulation fields."""
        from simulation.engine.writer import SimulationWriter

        path = str(temp_dir / "sim_output.parquet")
        writer = SimulationWriter()
        writer.write(fixture_outputs_3, path)

        df = pd.read_parquet(path)
        assert "symbol" in df.columns
        assert "best_action" in df.columns
        assert "decision_timestamp" in df.columns
        assert df["symbol"].tolist() == ["BTCUSDT", "ETHUSDT", "SOLUSDT"]

    def test_flat_contains_nested_fields(
        self,
        fixture_outputs_3: List[SimulationOutput],
        temp_dir: Path,
    ):
        """Flattened output should include long/short outcome fields."""
        from simulation.engine.writer import SimulationWriter

        path = str(temp_dir / "sim_output.parquet")
        writer = SimulationWriter()
        writer.write(fixture_outputs_3, path)

        df = pd.read_parquet(path)
        # Long outcome fields
        assert "long_outcome_realized_r_net" in df.columns
        assert "long_outcome_exit_reason" in df.columns
        assert "long_outcome_path_mfe_r" in df.columns
        # Short outcome fields
        assert "short_outcome_realized_r_net" in df.columns
        assert "short_outcome_exit_reason" in df.columns

        # Verify values
        assert df["long_outcome_realized_r_net"].tolist() == [1.3, 1.3, 1.3]

    def test_flat_contains_no_trade_fields(
        self,
        fixture_outputs_3: List[SimulationOutput],
        temp_dir: Path,
    ):
        """Flattened output should include no_trade fields."""
        from simulation.engine.writer import SimulationWriter

        path = str(temp_dir / "sim_output.parquet")
        writer = SimulationWriter()
        writer.write(fixture_outputs_3, path)

        df = pd.read_parquet(path)
        assert "no_trade_saved_loss_r" in df.columns
        assert "no_trade_missed_opportunity_r" in df.columns
        assert "no_trade_no_trade_quality" in df.columns

    def test_flat_contains_lineage_fields(
        self,
        fixture_outputs_3: List[SimulationOutput],
        temp_dir: Path,
    ):
        """Flattened output should include lineage fields."""
        from simulation.engine.writer import SimulationWriter

        path = str(temp_dir / "sim_output.parquet")
        writer = SimulationWriter()
        writer.write(fixture_outputs_3, path)

        df = pd.read_parquet(path)
        assert "lineage_simulation_family_version" in df.columns
        assert "lineage_adapter_kind" in df.columns

    def test_checksum_sidecar(
        self,
        fixture_outputs_3: List[SimulationOutput],
        temp_dir: Path,
    ):
        """write_checksum should produce a valid SHA-256 sidecar file."""
        from simulation.engine.writer import SimulationWriter

        path = str(temp_dir / "sim_output.parquet")
        writer = SimulationWriter()
        writer.write(fixture_outputs_3, path)

        digest = writer.write_checksum(path)

        # Verify sidecar file exists and matches
        sidecar_path = path + ".sha256"
        assert os.path.exists(sidecar_path)

        with open(sidecar_path) as f:
            stored_digest = f.read().strip()

        assert stored_digest == digest

        # Verify digest matches actual file
        computed = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                computed.update(chunk)
        assert digest == computed.hexdigest()

    def test_write_empty_list(
        self,
        temp_dir: Path,
    ):
        """Empty output list should produce a zero-row parquet file."""
        from simulation.engine.writer import SimulationWriter

        path = str(temp_dir / "empty.parquet")
        writer = SimulationWriter()
        writer.write([], path)

        assert os.path.exists(path)
        df = pd.read_parquet(path)
        assert len(df) == 0
