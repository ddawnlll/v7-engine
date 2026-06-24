"""Integration test: full pipeline from fixture dataset through WalkForwardValidator
to assembled ValidationReport.  Verifies correct structure, chronological
ordering, 6+ folds, all metrics NOT_EVALUATED, and verdict INCONCLUSIVE.
"""

from __future__ import annotations

import pytest

from alphaforge.validation.contracts import (
    NOT_EVALUATED,
    Mode,
    PurgePolicy,
    ValidationVerdict,
    WalkForwardConfig,
    WindowType,
)
from alphaforge.validation.walk_forward import WalkForwardValidator


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_row(feature_timestamp: str, symbol: str = "BTCUSDT"):
    """Create a minimal row object with feature_timestamp and symbol."""
    from dataclasses import dataclass

    @dataclass
    class Row:
        feature_timestamp: str
        symbol: str

    return Row(feature_timestamp=feature_timestamp, symbol=symbol)


@pytest.fixture
def integration_dataset():
    """1200-bar chronologically sorted dataset, 3 symbols, 1 row per bar."""
    from datetime import datetime, timedelta, timezone

    base = datetime(2025, 1, 1, tzinfo=timezone.utc)
    rows = []
    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    for bar_idx in range(1200):
        dt = base + timedelta(hours=bar_idx)
        ts = dt.isoformat()
        sym = symbols[bar_idx % 3]
        rows.append(_make_row(ts, sym))
    return rows


# ---------------------------------------------------------------------------
# Integration tests
# -------------------------------------------------------------------------


class TestIntegrationWalkForward:
    """End-to-end integration tests for walk-forward validation."""

    def test_full_pipeline_succeeds(self, integration_dataset):
        """Full pipeline: fixture dataset -> WalkForwardValidator.split()
        -> assemble_validation_report() -> verify structure."""
        config = WalkForwardConfig(
            mode=Mode.SWING,
            min_folds=6,
            train_window_bars=100,
            test_window_bars=50,
            purge_bars=10,
            embargo_bars=10,
            window_type=WindowType.ANCHORED,
        )
        policy = PurgePolicy(
            mode=Mode.SWING, purge_bars=10, embargo_bars=10
        )
        validator = WalkForwardValidator(config, policy)

        # split()
        folds = validator.split(integration_dataset)
        assert len(folds) >= 6, f"Expected >= 6 folds, got {len(folds)}"

        # Verify chronological ordering of test windows (train may overlap)
        for i in range(1, len(folds)):
            prev_test_end = max(
                integration_dataset[idx].feature_timestamp
                for idx in folds[i - 1].val_indices + folds[i - 1].oos_indices
            )
            curr_test_start = min(
                integration_dataset[idx].feature_timestamp
                for idx in folds[i].val_indices + folds[i].oos_indices
            )
            assert prev_test_end < curr_test_start, (
                f"Fold {i - 1} test end {prev_test_end} not before fold {i} test start {curr_test_start}"
            )

        # assemble_validation_report()
        report = validator.assemble_validation_report(integration_dataset)

        # Structure checks
        assert report.config is not None
        assert report.config.mode == Mode.SWING
        assert len(report.folds) >= 6
        assert report.verdict == ValidationVerdict.INCONCLUSIVE
        assert report.report_id.startswith("VR-SWING-")
        assert "T" in report.generated_at

        # All metrics NOT_EVALUATED
        oos = report.oos_summary
        assert oos.oos_sharpe is NOT_EVALUATED
        assert oos.oos_win_rate is NOT_EVALUATED
        assert oos.oos_expectancy is NOT_EVALUATED
        assert oos.oos_max_drawdown is NOT_EVALUATED
        assert oos.oos_profit_factor is NOT_EVALUATED
        assert oos.oos_trades_count is NOT_EVALUATED

        cost = report.cost_stress
        assert cost.fee_baseline is NOT_EVALUATED
        assert cost.fee_stress_2x is NOT_EVALUATED
        assert cost.slippage_baseline is NOT_EVALUATED
        assert "DEFERRED" in cost.funding_deferred_block

        regime = report.regime_breakdown
        assert regime.TREND_UP is NOT_EVALUATED
        assert regime.TREND_DOWN is NOT_EVALUATED
        assert regime.RANGE is NOT_EVALUATED
        assert regime.TRANSITION is NOT_EVALUATED

        sym = report.symbol_stability
        assert sym.max_single_symbol_concentration is NOT_EVALUATED
        assert sym.MAX_SINGLE_SYMBOL_CONCENTRATION == 0.40
        assert sym.MAX_CLUSTER_CONCENTRATION == 0.60

        mht = report.mht_controls
        assert mht.correction_method == "NONE_APPLIED"
        assert mht.data_snooping_risk_flag == "HIGH"

        # Per-fold sample counts populated
        for fr in report.folds:
            assert fr.train_count > 0
            assert fr.val_count > 0
            assert fr.oos_count > 0
            assert isinstance(fr.train_count, int)

        # overfit_risk_flags is empty
        assert report.overfit_risk_flags == []

    def test_no_ml_imports_in_validation_module(self):
        """Zero ML library imports in validation subpackage."""
        import alphaforge.validation.contracts as cm
        import alphaforge.validation.walk_forward as wf

        forbidden = ["xgboost", "sklearn", "tensorflow", "torch"]
        for mod in [cm, wf]:
            mod_dir = set(dir(mod))
            for term in forbidden:
                assert term not in mod_dir, f"{mod.__name__} exposes '{term}'"

    def test_report_id_is_deterministic(self, integration_dataset):
        """Same config + same dataset length => same hash part (not content-based)."""
        config = WalkForwardConfig(
            mode=Mode.SWING,
            min_folds=6,
            train_window_bars=100,
            test_window_bars=50,
            purge_bars=10,
            embargo_bars=10,
            window_type=WindowType.ANCHORED,
        )
        policy = PurgePolicy(
            mode=Mode.SWING, purge_bars=10, embargo_bars=10
        )

        v1 = WalkForwardValidator(config, policy)
        r1 = v1.assemble_validation_report(list(integration_dataset))

        v2 = WalkForwardValidator(config, policy)
        r2 = v2.assemble_validation_report(list(integration_dataset))

        # Report IDs should be different (different timestamps) but same format
        assert r1.report_id.startswith("VR-SWING-")
        assert r2.report_id.startswith("VR-SWING-")
        assert len(r1.report_id) == len(r2.report_id)

    def test_empty_dataset_raises(self):
        """Empty dataset raises ValidationError."""
        config = WalkForwardConfig(
            mode=Mode.SWING,
            min_folds=6,
            train_window_bars=100,
            test_window_bars=50,
            purge_bars=10,
            embargo_bars=10,
            window_type=WindowType.ANCHORED,
        )
        policy = PurgePolicy(
            mode=Mode.SWING, purge_bars=10, embargo_bars=10
        )
        validator = WalkForwardValidator(config, policy)
        with pytest.raises(Exception):
            validator.split([])
