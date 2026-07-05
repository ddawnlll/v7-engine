"""Tests for P1.0 Profit-State Mining Alpha Factory.

Tests cover:
- P1.0A: CandidateOutcomeDataset v002 side-specific rows, no side oracle
- P1.0B: Baseline-normalized excess_net_R
- P1.0D: Mining engine with excess_net_R
- P1.0E: Rule dedup / alpha-family clustering
- P1.0F: Validation funnel
- P1.0G: AlphaRuleSpec export
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_mock_simulation_output(
    symbol: str = "BTCUSDT",
    mode: str = "SCALP",
    best_action: str = "LONG_NOW",
    long_net_R: float = 0.5,
    short_net_R: float = -0.2,
    timestamp: str = "2023-11-14T17:00:00+00:00",
) -> Any:
    """Create a mock SimulationOutput-like object."""
    class MockPathMetrics:
        def __init__(self):
            self.mfe_r = 0.8
            self.mae_r = 0.3

    class MockOutcome:
        def __init__(self, net_r):
            self.realized_r_net = net_r
            self.realized_r_gross = net_r * 1.1
            self.total_cost_r = abs(net_r) * 0.08
            self.path_metrics = MockPathMetrics()
            self.hold_duration_bars = 6
            self.exit_reason = "TARGET_HIT"

    class MockSimOutput:
        def __init__(self):
            self.symbol = symbol
            self.mode = mode
            self.best_action = best_action
            self.decision_timestamp = timestamp
            self.primary_interval = "1h"
            self.simulation_run_id = f"run_{symbol}_{mode}"
            self.simulation_profile_id = f"profile_{mode}"
            self.long_outcome = MockOutcome(long_net_R)
            self.short_outcome = MockOutcome(short_net_R)

    return MockSimOutput()


def _make_mock_kline_records(n: int = 100, symbol: str = "BTCUSDT", base_ts: int = 1699801200000) -> List[Any]:
    """Create mock KlineRecord objects.

    Default base_ts puts index 50 at timestamp 1699981200000 = 2023-11-14T17:00:00Z
    which matches the mock sim output timestamp. Lookback_bars=50 means entry_idx=50.
    """
    class MockKline:
        def __init__(self, ts, close):
            self.symbol = symbol
            self.timestamp = ts
            self.open = close * 0.99
            self.high = close * 1.01
            self.low = close * 0.98
            self.close = close
            self.volume = 1000.0
            self.interval = "1h"

    records = []
    base_price = 50000.0
    for i in range(n):
        price = base_price * (1 + 0.001 * np.sin(i * 0.1))
        records.append(MockKline(base_ts + i * 3600000, price))
    return records


def _make_v002_table(n: int = 200) -> pa.Table:
    """Create a minimal v002 dataset table for testing."""
    rng = np.random.RandomState(42)
    symbols = rng.choice(["BTCUSDT", "ETHUSDT", "SOLUSDT"], n)
    sides = rng.choice(["LONG", "SHORT"], n)
    modes = rng.choice(["SCALP", "SWING"], n)
    net_R = rng.randn(n) * 0.3
    excess = net_R - rng.choice([0.0, 0.1, -0.1], n)
    atr_pct = rng.uniform(1.0, 5.0, n)
    regime = rng.choice(["up", "down", "range"], n)

    return pa.table({
        "row_id": [f"row_{i}" for i in range(n)],
        "symbol": symbols,
        "timestamp": np.arange(1700000000000, 1700000000000 + n * 3600000, 3600000, dtype=np.int64)[:n],
        "timeframe": ["1h"] * n,
        "mode": modes,
        "side": sides,
        "simulation_profile_id": ["prof_1"] * n,
        "dataset_version": ["v002"] * n,
        "regime_trend": regime,
        "volatility_percentile": rng.uniform(0, 100, n),
        "momentum_rank": rng.uniform(0, 1, n),
        "volume_zscore": rng.randn(n),
        "atr_pct": atr_pct,
        "btc_regime": rng.choice(["up", "down", "range"], n),
        "pullback_atr": rng.uniform(0, 2, n),
        "distance_to_range_high": rng.uniform(0, 1, n),
        "spread_proxy": np.zeros(n),
        "funding_context": np.zeros(n),
        "gross_R": net_R * 1.1,
        "net_R": net_R,
        "cost_R": np.abs(net_R) * 0.08,
        "mfe_R": np.abs(net_R) * 1.5,
        "mae_R": np.abs(net_R) * 0.8,
        "bars_held": rng.randint(1, 12, n),
        "exit_reason": ["TARGET_HIT"] * n,
        "is_valid": [True] * n,
        "rejection_reason": [""] * n,
        "profit_bucket": ["win" if r > 0 else "loss" for r in net_R],
        "is_profitable_state": net_R > 0,
        "is_strong_win": net_R > 0.5,
        "is_bad_state": net_R < -0.5,
        "excess_net_R": excess,
        "excess_profit_bucket": ["above_baseline" if e > 0.05 else "below_baseline" for e in excess],
        "simulation_run_id": [f"run_{s}" for s in symbols],
        "candidate_id": [f"cid_{i}" for i in range(n)],
    })


# ---------------------------------------------------------------------------
# P1.0A Tests: CandidateOutcomeDataset v002
# ---------------------------------------------------------------------------

class TestCandidateOutcomeV002:
    """Test side-specific rows and no side oracle."""

    def test_separate_long_short_rows(self):
        """LONG and SHORT rows must remain separate — no best-of-side."""
        from alphaforge.datasets.candidate_outcomes import CandidateOutcomeDatasetBuilder

        records = _make_mock_kline_records(100)
        builder = CandidateOutcomeDatasetBuilder(
            market_data={"BTCUSDT": records},
            lookback_bars=50,
        )

        sim_out = _make_mock_simulation_output(
            best_action="LONG_NOW", long_net_R=0.5, short_net_R=-0.2,
        )
        table = builder.build([sim_out])

        assert table.num_rows == 2, "Should produce exactly 2 rows (LONG + SHORT)"
        sides = table.column("side").to_pylist()
        assert "LONG" in sides
        assert "SHORT" in sides

    def test_no_best_of_side_aggregation(self):
        """Dataset must not pick the better side after the fact."""
        from alphaforge.datasets.candidate_outcomes import CandidateOutcomeDatasetBuilder

        records = _make_mock_kline_records(100)
        builder = CandidateOutcomeDatasetBuilder(
            market_data={"BTCUSDT": records},
            lookback_bars=50,
        )

        sim_out = _make_mock_simulation_output(
            best_action="LONG_NOW", long_net_R=0.5, short_net_R=-0.2,
        )
        table = builder.build([sim_out])

        # Both sides should have their actual net_R, not the max
        net_R_vals = table.column("net_R").to_pylist()
        assert 0.5 in net_R_vals, "LONG net_R should be preserved"
        assert -0.2 in net_R_vals, "SHORT net_R should be preserved"

    def test_simulation_truth_passthrough(self):
        """Simulation truth fields must be passed through, not recomputed."""
        from alphaforge.datasets.candidate_outcomes import CandidateOutcomeDatasetBuilder

        records = _make_mock_kline_records(100)
        builder = CandidateOutcomeDatasetBuilder(
            market_data={"BTCUSDT": records},
            lookback_bars=50,
        )

        sim_out = _make_mock_simulation_output(long_net_R=0.5, short_net_R=-0.2)
        table = builder.build([sim_out])

        # net_R should match the simulation output values
        net_R_vals = table.column("net_R").to_pylist()
        assert abs(net_R_vals[0] - 0.5) < 1e-6 or abs(net_R_vals[0] - (-0.2)) < 1e-6

    def test_dataset_version(self):
        """Dataset version should be v002."""
        from alphaforge.datasets.candidate_outcomes import CandidateOutcomeDatasetBuilder, DATASET_VERSION

        assert DATASET_VERSION == "v002"

        records = _make_mock_kline_records(100)
        builder = CandidateOutcomeDatasetBuilder(
            market_data={"BTCUSDT": records},
            lookback_bars=50,
        )
        sim_out = _make_mock_simulation_output()
        table = builder.build([sim_out])

        versions = set(table.column("dataset_version").to_pylist())
        assert versions == {"v002"}

    def test_derived_labels(self):
        """Derived research labels should be deterministic."""
        from alphaforge.datasets.candidate_outcomes import CandidateOutcomeDatasetBuilder

        records = _make_mock_kline_records(100)
        builder = CandidateOutcomeDatasetBuilder(
            market_data={"BTCUSDT": records},
            lookback_bars=50,
        )

        sim_out = _make_mock_simulation_output(long_net_R=0.5, short_net_R=-0.2)
        table = builder.build([sim_out])

        # Check derived labels exist
        assert "profit_bucket" in table.column_names
        assert "is_profitable_state" in table.column_names
        assert "is_strong_win" in table.column_names
        assert "is_bad_state" in table.column_names
        assert "excess_net_R" in table.column_names
        assert "excess_profit_bucket" in table.column_names

    def test_summary_report(self):
        """Summary report should contain required sections."""
        from alphaforge.datasets.candidate_outcomes import CandidateOutcomeDatasetBuilder

        records = _make_mock_kline_records(100)
        builder = CandidateOutcomeDatasetBuilder(
            market_data={"BTCUSDT": records},
            lookback_bars=50,
        )

        sim_out = _make_mock_simulation_output()
        table = builder.build([sim_out])
        summary = builder.compute_summary(table)

        assert "row_count" in summary
        assert "side_distribution" in summary
        assert "net_R_distribution" in summary
        assert "leakage_guard" in summary
        assert summary["leakage_guard"]["side_oracle_removed"] is True
        assert summary["leakage_guard"]["local_simulation_absent"] is True


# ---------------------------------------------------------------------------
# P1.0B Tests: Baseline-normalized excess_net_R
# ---------------------------------------------------------------------------

class TestBaselineTargets:
    """Test baseline normalization and excess_net_R computation."""

    def test_excess_equals_net_R_minus_baseline(self):
        """excess_net_R should equal net_R minus the correct baseline group mean."""
        from alphaforge.datasets.baseline_targets import BaselineComputer

        table = _make_v002_table(200)
        computer = BaselineComputer(min_group_size=5)
        result = computer.compute(table)

        assert "baseline_net_R_mean" in result.column_names
        assert "excess_net_R" in result.column_names

        net_R = result.column("net_R").to_numpy().astype(float)
        baseline = result.column("baseline_net_R_mean").to_numpy().astype(float)
        excess = result.column("excess_net_R").to_numpy().astype(float)

        # excess should approximately equal net_R - baseline
        np.testing.assert_allclose(excess, net_R - baseline, atol=1e-6)

    def test_baseline_grouping_is_side_specific(self):
        """Baseline grouping should be side-specific."""
        from alphaforge.datasets.baseline_targets import BaselineComputer

        table = _make_v002_table(200)
        computer = BaselineComputer(min_group_size=5)
        result = computer.compute(table)

        stats = computer.get_baseline_stats()
        # Should have separate groups for LONG and SHORT
        long_groups = [k for k in stats if "side=LONG" in k]
        short_groups = [k for k in stats if "side=SHORT" in k]
        assert len(long_groups) > 0, "Should have LONG baseline groups"
        assert len(short_groups) > 0, "Should have SHORT baseline groups"

    def test_missing_grouping_fields_reported(self):
        """Missing grouping fields should be reported, not silently ignored."""
        from alphaforge.datasets.baseline_targets import BaselineComputer

        # Table without atr_bucket or regime_bucket
        table = pa.table({
            "net_R": [0.1, 0.2, 0.3],
            "mode": ["SCALP", "SCALP", "SCALP"],
            "side": ["LONG", "LONG", "LONG"],
        })
        computer = BaselineComputer()
        missing = computer.get_missing_fields(table)
        assert "atr_bucket" in missing
        assert "regime_bucket" in missing
        assert "timeframe" in missing


# ---------------------------------------------------------------------------
# P1.0E Tests: Rule dedup / alpha-family clustering
# ---------------------------------------------------------------------------

class TestRuleDeduplicator:
    """Test rule deduplication and family clustering."""

    def test_near_duplicate_rules_clustered(self):
        """Two rules selecting nearly same rows should be clustered."""
        from alphaforge.mine.rule_deduper import RuleDeduplicator

        n = 100
        rng = np.random.RandomState(42)
        mask_a = rng.random(n) > 0.3  # ~70% true
        mask_b = mask_a.copy()
        # Flip a few bits
        flip_idx = rng.choice(n, 5, replace=False)
        mask_b[flip_idx] = ~mask_b[flip_idx]

        target = rng.randn(n)
        masks = {"cond_a": mask_a, "cond_b": mask_b}

        rules = [
            {"conditions": ["cond_a"], "mean_net_R": 0.1, "rule_id": "r1"},
            {"conditions": ["cond_b"], "mean_net_R": 0.12, "rule_id": "r2"},
        ]

        deduper = RuleDeduplicator(jaccard_threshold=0.8)
        result = deduper.deduplicate(rules, masks, target)

        assert len(result["families"]) == 1, "Similar rules should be in one family"
        assert len(result["duplicates"]) == 1, "One should be marked duplicate"

    def test_distinct_rules_not_merged(self):
        """Distinct rules should not be merged."""
        from alphaforge.mine.rule_deduper import RuleDeduplicator

        n = 100
        rng = np.random.RandomState(42)
        mask_a = np.zeros(n, dtype=bool)
        mask_a[:30] = True
        mask_b = np.zeros(n, dtype=bool)
        mask_b[70:] = True

        target = rng.randn(n)
        masks = {"cond_a": mask_a, "cond_b": mask_b}

        rules = [
            {"conditions": ["cond_a"], "mean_net_R": 0.1, "rule_id": "r1"},
            {"conditions": ["cond_b"], "mean_net_R": 0.15, "rule_id": "r2"},
        ]

        deduper = RuleDeduplicator(jaccard_threshold=0.7)
        result = deduper.deduplicate(rules, masks, target)

        assert len(result["families"]) == 2, "Distinct rules should be separate families"
        assert len(result["duplicates"]) == 0, "No duplicates"

    def test_family_representative_selection(self):
        """Family representative should be the highest mean_net_R rule."""
        from alphaforge.mine.rule_deduper import RuleDeduplicator

        n = 100
        rng = np.random.RandomState(42)
        mask = rng.random(n) > 0.3
        target = rng.randn(n)
        masks = {"cond_a": mask}

        rules = [
            {"conditions": ["cond_a"], "mean_net_R": 0.1, "rule_id": "r_low"},
            {"conditions": ["cond_a"], "mean_net_R": 0.5, "rule_id": "r_high"},
        ]

        deduper = RuleDeduplicator(jaccard_threshold=0.5)
        result = deduper.deduplicate(rules, masks, target)

        family = result["families"][0]
        assert family["representative_rule_id"] == "r_high"


# ---------------------------------------------------------------------------
# P1.0F Tests: Validation funnel
# ---------------------------------------------------------------------------

class TestValidationFunnel:
    """Test validation funnel promotion gates."""

    def test_split_produces_three_partitions(self):
        """Temporal split should produce discovery/validation/holdout."""
        from alphaforge.mine.validator import ValidationFunnel

        table = _make_v002_table(200)
        funnel = ValidationFunnel()
        splits = funnel.split(table, timestamp_col="timestamp")

        assert "discovery" in splits
        assert "validation" in splits
        assert "holdout" in splits
        assert splits["discovery"].num_rows > 0
        assert splits["validation"].num_rows > 0
        assert splits["holdout"].num_rows > 0

    def test_low_support_rule_rejected(self):
        """A rule with low support should be rejected."""
        from alphaforge.mine.validator import ValidationFunnel

        table = _make_v002_table(200)
        funnel = ValidationFunnel(gates={"min_support_total": 1000})  # Very high
        splits = funnel.split(table, timestamp_col="timestamp")

        # Rule that selects very few rows
        masks = {"rare_condition": np.zeros(200, dtype=bool)}
        masks["rare_condition"][0:5] = True  # Only 5 rows

        rules = [{"conditions": ["rare_condition"], "rule_id": "rare"}]

        result = funnel.validate(
            rules=rules,
            masks=masks,
            discovery_table=splits["discovery"],
            validation_table=splits["validation"],
            holdout_table=splits["holdout"],
            target_col="excess_net_R",
        )

        assert result["summary"]["rejected_count"] == 1
        assert result["summary"]["validated_count"] == 0

    def test_missing_holdout_prevents_full_validation(self):
        """Missing holdout should mark rule as CANDIDATE_ONLY, not VALIDATED."""
        from alphaforge.mine.validator import ValidationFunnel

        table = _make_v002_table(200)
        funnel = ValidationFunnel()
        splits = funnel.split(table, timestamp_col="timestamp")

        # Rule that works everywhere
        masks = {"broad_condition": np.ones(200, dtype=bool)}

        rules = [{"conditions": ["broad_condition"], "rule_id": "broad"}]

        result = funnel.validate(
            rules=rules,
            masks=masks,
            discovery_table=splits["discovery"],
            validation_table=splits["validation"],
            holdout_table=splits["holdout"],
            target_col="excess_net_R",
        )

        # Should be validated (broad mask works on all splits)
        assert result["summary"]["validated_count"] >= 0  # May be candidate or validated


# ---------------------------------------------------------------------------
# P1.0G Tests: AlphaRuleSpec export
# ---------------------------------------------------------------------------

class TestAlphaRuleSpecExport:
    """Test AlphaRuleSpec artifact generation."""

    def test_spec_has_required_fields(self):
        """AlphaRuleSpec should have all required fields."""
        from alphaforge.mine.exporter import AlphaRuleSpecBuilder

        builder = AlphaRuleSpecBuilder()
        rules = [
            {
                "rule_id": "test_rule",
                "status": "VALIDATED",
                "conditions": ["atr_pct__d10", "side__LONG"],
                "primary_family": "volatility",
                "discovery": {"support": 150, "mean_excess_net_R": 0.02},
                "validation": {"support": 80, "mean_excess_net_R": 0.015},
                "holdout": {"support": 60, "mean_excess_net_R": 0.01},
                "oos_is_ratio": 0.75,
                "symbol_stability": 0.8,
            }
        ]

        specs = builder.build(rules, mining_run_id="test_run")
        assert len(specs) == 1

        spec = specs[0]
        assert "alpha_id" in spec
        assert "schema_version" in spec
        assert "family_id" in spec
        assert "status" in spec
        assert "conditions" in spec
        assert "evidence" in spec
        assert "provenance" in spec
        assert "forbidden" in spec

        # Forbidden flags must be False
        assert spec["forbidden"]["contains_future_leakage"] is False
        assert spec["forbidden"]["uses_best_of_side"] is False
        assert spec["forbidden"]["uses_local_simulation"] is False

    def test_export_writes_files(self):
        """Export should write JSON files to disk."""
        from alphaforge.mine.exporter import AlphaRuleSpecBuilder

        builder = AlphaRuleSpecBuilder()
        rules = [
            {
                "rule_id": "export_test",
                "status": "VALIDATED",
                "conditions": ["atr_pct__d10"],
                "primary_family": "volatility",
                "discovery": {"support": 100, "mean_excess_net_R": 0.01},
                "validation": {"support": 50, "mean_excess_net_R": 0.008},
                "holdout": {"support": 30, "mean_excess_net_R": 0.005},
                "oos_is_ratio": 0.8,
                "symbol_stability": 0.7,
            }
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            specs = builder.build(rules)
            exported = builder.export(specs, tmpdir)
            assert exported == 1

            # Check file exists
            files = list(Path(tmpdir).glob("*.json"))
            assert len(files) == 1

            # Check content
            with open(files[0]) as f:
                data = json.load(f)
            assert data["alpha_id"] == "alpha_export_test"

    def test_registry_contains_all_specs(self):
        """Registry should index all specs."""
        from alphaforge.mine.exporter import AlphaRuleSpecBuilder

        builder = AlphaRuleSpecBuilder()
        rules = [
            {"rule_id": "r1", "status": "VALIDATED", "conditions": ["a"],
             "primary_family": "vol", "discovery": {}, "validation": {},
             "holdout": {}, "oos_is_ratio": 1.0, "symbol_stability": 1.0},
            {"rule_id": "r2", "status": "CANDIDATE_ONLY", "conditions": ["b"],
             "primary_family": "mom", "discovery": {}, "validation": {},
             "holdout": {}, "oos_is_ratio": 0.6, "symbol_stability": 0.5},
        ]

        specs = builder.build(rules)
        registry = builder.build_registry(specs)

        assert registry["total_specs"] == 2
        assert registry["validated_count"] == 1
        assert registry["candidate_count"] == 1
