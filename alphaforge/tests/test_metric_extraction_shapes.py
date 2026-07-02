"""
Tests for _extract_metrics — metric extraction from different WFV dict shapes.

Verifies that target_validator._extract_metrics handles both pipeline-shaped
dicts (metrics/oos_summary keys) and walk_forward_runner-shaped dicts
(aggregate_metrics.total_oos_trades key).

Uses the default target_alpha_profile.yaml for validator construction.
"""

import os

from alphaforge.validation.target_validator import (
    AlphaTargetValidator,
    _DEFAULT_PROFILE_PATH,
)


def _make_validator():
    """Create a validator using the default profile."""
    assert os.path.isfile(_DEFAULT_PROFILE_PATH), (
        f"Profile not found: {_DEFAULT_PROFILE_PATH}"
    )
    return AlphaTargetValidator()


def test_runner_shaped_dict():
    """Runner dict → active_trade_count from aggregate_metrics.total_oos_trades."""
    validator = _make_validator()
    wfv = {
        "aggregate_metrics": {"total_oos_trades": 100},
        "data_summary": {"total_bars": 1000},
    }
    metrics = validator._extract_metrics(wfv)
    assert metrics["active_trade_count"] == 100
    assert metrics["exposure_pct"] == 10.0


def test_pipeline_shaped_dict():
    """Pipeline dict → active_trade_count from metrics key."""
    validator = _make_validator()
    wfv = {
        "metrics": {"active_trade_count": 50, "exposure_pct": 5.0},
    }
    metrics = validator._extract_metrics(wfv)
    assert metrics["active_trade_count"] == 50
    assert metrics["exposure_pct"] == 5.0


def test_pipeline_with_oos_summary():
    """Pipeline dict → oos_summary.active_trade_count fallback."""
    validator = _make_validator()
    wfv = {
        "oos_summary": {"active_trade_count": 75, "exposure_pct": 7.5},
        "data_summary": {"total_bars": 1000},
    }
    metrics = validator._extract_metrics(wfv)
    assert metrics["active_trade_count"] == 75
    assert metrics["exposure_pct"] == 7.5


def test_empty_dict():
    """Empty dict → zeros."""
    validator = _make_validator()
    metrics = validator._extract_metrics({})
    assert metrics["active_trade_count"] == 0
    assert metrics["exposure_pct"] == 0.0


def test_runner_with_oos_trade_count_fallback():
    """agg has no total_oos_trades → falls through to oos_trade_count."""
    validator = _make_validator()
    wfv = {
        "aggregate_metrics": {"avg_net_sharpe": 0.5},
        "oos_summary": {"oos_trade_count": 30},
        "data_summary": {"total_bars": 600},
    }
    metrics = validator._extract_metrics(wfv)
    assert metrics["active_trade_count"] == 30
    assert metrics["exposure_pct"] == 5.0


def test_score_gr1_not_triggered_by_runner_shape():
    """Score with runner-shaped dict does not trigger GR1.

    The runner-shaped dict has aggregate_metrics.total_oos_trades=200
    but no metrics.active_trade_count key. With the fix, _extract_metrics
    reads total_oos_trades as the fourth fallback, so GR1 doesn't fire.
    """
    validator = _make_validator()
    wfv = {
        "aggregate_metrics": {
            "total_oos_trades": 200,
            "avg_net_sharpe": 0.5,
            "avg_net_profit_factor": 1.2,
            "avg_net_expectancy": 0.15,
            "pass_ratio": 0.8,
            "n_folds": 6,
        },
        "data_summary": {"total_bars": 2000, "n_symbols": 5},
    }
    result = validator.score(wfv)
    # GR1 triggers when active_trade_count=0 → economic_score=0
    # With runner shape fixed, economic_score should NOT be 0
    assert result.economic_score > 0, (
        f"GR1 incorrectly triggered (economic=0): {result}"
    )
    assert "GR1: no active trades" not in str(result), (
        "GR1 anomaly flag should not appear"
    )
