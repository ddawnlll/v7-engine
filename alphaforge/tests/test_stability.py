"""Unit tests for Symbol + Regime Stability Metrics (Issue #116).

Tests:
  - compute_symbol_metrics: per-symbol OOS metrics from structured input
  - compute_symbol_concentration: HHI and top-symbol share
  - compute_regime_concentration: HHI and top-regime share from regime entries
  - build_stability_section: integrated section from WFV results dict
  - classify_symbol_regimes_from_ohlcv: regime classification from synthetic OHLCV
  - Edge cases: empty input, single symbol, single regime, zero trades

All tests are deterministic. No ML imports.
"""

import json
import math

import numpy as np
import pytest

from alphaforge.reports.stability import (
    STABILITY_REGIME_LABELS,
    build_stability_section,
    classify_symbol_regimes_from_ohlcv,
    compute_regime_concentration,
    compute_symbol_concentration,
    compute_symbol_metrics,
)


# ===========================================================================
# Fixtures
# ===========================================================================

def _make_symbol_oos(
    symbols=None,
    expectancy_r: float = 0.15,
    win_rate: float = 0.55,
    trade_count: int = 200,
) -> dict:
    """Create deterministic per-symbol OOS data."""
    if symbols is None:
        symbols = ["BTCUSDT"]
    return {
        sym: {
            "oos_expectancy_r": expectancy_r,
            "oos_win_rate": win_rate,
            "oos_trade_count": trade_count,
        }
        for sym in symbols
    }


def _make_regime_entries(
    regimes: list | None = None,
) -> list[dict]:
    """Create regime entries for concentration testing."""
    if regimes is None:
        regimes = [
            {"regime": "TREND_UP", "sample_pct": 0.40, "oos_expectancy_r": 0.20},
            {"regime": "TREND_DOWN", "sample_pct": 0.30, "oos_expectancy_r": 0.10},
            {"regime": "RANGE", "sample_pct": 0.20, "oos_expectancy_r": 0.05},
            {"regime": "TRANSITION", "sample_pct": 0.10, "oos_expectancy_r": 0.02},
        ]
    return regimes


# ===========================================================================
# Tests: compute_symbol_metrics
# ===========================================================================

class TestComputeSymbolMetrics:
    """Per-symbol metrics from structured OOS data."""

    def test_single_symbol(self):
        """Single symbol produces correct metrics."""
        data = _make_symbol_oos(["BTCUSDT"], expectancy_r=0.20, win_rate=0.60, trade_count=300)
        result = compute_symbol_metrics(data)
        assert "BTCUSDT" in result
        assert result["BTCUSDT"]["expectancy_r"] == 0.20
        assert result["BTCUSDT"]["win_rate"] == 0.60
        assert result["BTCUSDT"]["trade_count"] == 300

    def test_multi_symbol(self):
        """Multiple symbols each have correct metrics."""
        data = _make_symbol_oos(
            ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
            expectancy_r=0.15, win_rate=0.55, trade_count=200,
        )
        result = compute_symbol_metrics(data)
        assert len(result) == 3
        for sym in ("BTCUSDT", "ETHUSDT", "SOLUSDT"):
            assert sym in result
            assert result[sym]["expectancy_r"] == 0.15
            assert result[sym]["trade_count"] == 200

    def test_empty_dict(self):
        """Empty input produces empty result."""
        result = compute_symbol_metrics({})
        assert result == {}

    def test_missing_field_defaults(self):
        """Missing fields default to 0.0 / 0."""
        data = {"BTCUSDT": {}}
        result = compute_symbol_metrics(data)
        assert result["BTCUSDT"]["expectancy_r"] == 0.0
        assert result["BTCUSDT"]["win_rate"] == 0.0
        assert result["BTCUSDT"]["trade_count"] == 0

    def test_partial_fields(self):
        """Partial data is handled without error."""
        data = {
            "BTCUSDT": {"oos_expectancy_r": 0.10},
            "ETHUSDT": {"oos_win_rate": 0.50, "oos_trade_count": 100},
        }
        result = compute_symbol_metrics(data)
        assert result["BTCUSDT"]["win_rate"] == 0.0  # default
        assert result["ETHUSDT"]["expectancy_r"] == 0.0  # default
        assert result["ETHUSDT"]["trade_count"] == 100


# ===========================================================================
# Tests: compute_symbol_concentration
# ===========================================================================

class TestComputeSymbolConcentration:
    """Symbol concentration ratio computation."""

    def test_equal_distribution(self):
        """Equal trade counts across symbols produce low concentration."""
        data = {
            "BTCUSDT": {"trade_count": 100},
            "ETHUSDT": {"trade_count": 100},
            "SOLUSDT": {"trade_count": 100},
        }
        result = compute_symbol_concentration(data)
        assert result["num_symbols"] == 3
        assert result["total_trades"] == 300
        assert result["top_symbol_share"] == pytest.approx(1.0 / 3, abs=0.001)
        # HHI for equal shares: 3 * (1/3)^2 = 3 * 1/9 = 1/3 ≈ 0.333
        assert result["symbol_concentration_hhi"] == pytest.approx(0.333333, abs=0.001)

    def test_single_symbol_dominance(self):
        """One symbol with all trades => HHI = 1.0."""
        data = {
            "BTCUSDT": {"trade_count": 100},
            "ETHUSDT": {"trade_count": 0},
        }
        result = compute_symbol_concentration(data)
        assert result["top_symbol"] == "BTCUSDT"
        assert result["top_symbol_share"] == 1.0
        assert result["symbol_concentration_hhi"] == 1.0
        assert result["total_trades"] == 100

    def test_empty_input(self):
        """Empty input returns empty concentrations."""
        result = compute_symbol_concentration({})
        assert result["num_symbols"] == 0
        assert result["top_symbol"] == "NONE"
        assert result["top_symbol_share"] == 0.0
        assert result["symbol_concentration_hhi"] == 0.0

    def test_all_zero_trades(self):
        """All zero trades => all shares zero, top = NONE."""
        data = {"BTCUSDT": {"trade_count": 0}, "ETHUSDT": {"trade_count": 0}}
        result = compute_symbol_concentration(data)
        assert result["top_symbol"] == "NONE"
        assert result["top_symbol_share"] == 0.0
        assert result["total_trades"] == 0

    def test_uneven_distribution(self):
        """Uneven distribution produces correct HHI."""
        data = {
            "BTCUSDT": {"trade_count": 70},
            "ETHUSDT": {"trade_count": 20},
            "SOLUSDT": {"trade_count": 10},
        }
        result = compute_symbol_concentration(data)
        assert result["total_trades"] == 100
        assert result["top_symbol"] == "BTCUSDT"
        assert result["top_symbol_share"] == 0.70
        # HHI = 0.7^2 + 0.2^2 + 0.1^2 = 0.49 + 0.04 + 0.01 = 0.54
        assert result["symbol_concentration_hhi"] == pytest.approx(0.54, abs=0.001)

    def test_per_symbol_shares_present(self):
        """All symbols appear in per_symbol_shares."""
        data = {
            "BTCUSDT": {"trade_count": 50},
            "ETHUSDT": {"trade_count": 50},
        }
        result = compute_symbol_concentration(data)
        assert set(result["per_symbol_shares"].keys()) == {"BTCUSDT", "ETHUSDT"}
        assert result["per_symbol_shares"]["BTCUSDT"] == 0.5
        assert result["per_symbol_shares"]["ETHUSDT"] == 0.5


# ===========================================================================
# Tests: compute_regime_concentration
# ===========================================================================

class TestComputeRegimeConcentration:
    """Regime concentration ratio computation."""

    def test_equal_distribution(self):
        """Equal sample_pct across regimes produce low concentration."""
        entries = [
            {"regime": "TREND_UP", "sample_pct": 0.25},
            {"regime": "TREND_DOWN", "sample_pct": 0.25},
            {"regime": "RANGE", "sample_pct": 0.25},
            {"regime": "TRANSITION", "sample_pct": 0.25},
        ]
        result = compute_regime_concentration(entries)
        assert result["num_regimes"] == 4
        assert result["top_regime_share"] == pytest.approx(0.25, abs=0.001)
        # HHI = 4 * 0.25^2 = 4 * 0.0625 = 0.25
        assert result["regime_concentration_hhi"] == pytest.approx(0.25, abs=0.001)

    def test_dominant_regime(self):
        """One regime dominates => high concentration."""
        entries = [
            {"regime": "TREND_UP", "sample_pct": 0.85},
            {"regime": "TREND_DOWN", "sample_pct": 0.10},
            {"regime": "RANGE", "sample_pct": 0.05},
            {"regime": "TRANSITION", "sample_pct": 0.00},
        ]
        result = compute_regime_concentration(entries)
        assert result["top_regime"] == "TREND_UP"
        assert result["top_regime_share"] == pytest.approx(0.85, abs=0.001)
        # HHI = 0.85^2 + 0.1^2 + 0.05^2 + 0^2 = 0.7225 + 0.01 + 0.0025 = 0.735
        assert result["regime_concentration_hhi"] == pytest.approx(0.735, abs=0.001)

    def test_empty_input(self):
        """Empty input returns empty concentration."""
        result = compute_regime_concentration([])
        assert result["num_regimes"] == 0
        assert result["top_regime"] == "NONE"
        assert result["regime_concentration_hhi"] == 0.0

    def test_single_regime(self):
        """Single regime => HHI = 1.0."""
        entries = [{"regime": "TREND_UP", "sample_pct": 1.0}]
        result = compute_regime_concentration(entries)
        assert result["num_regimes"] == 1
        assert result["top_regime"] == "TREND_UP"
        assert result["top_regime_share"] == 1.0
        assert result["regime_concentration_hhi"] == 1.0

    def test_regime_without_sample_pct(self):
        """Entries without sample_pct get equal share."""
        entries = [
            {"regime": "TREND_UP"},
            {"regime": "TREND_DOWN"},
        ]
        result = compute_regime_concentration(entries)
        assert result["top_regime_share"] == 0.5
        assert result["num_regimes"] == 2

    def test_normalizes_non_zero(self):
        """Shares are normalised to sum to 1.0."""
        entries = [
            {"regime": "TREND_UP", "sample_pct": 10},
            {"regime": "TREND_DOWN", "sample_pct": 30},
        ]
        result = compute_regime_concentration(entries)
        # After normalisation: TREND_UP = 0.25, TREND_DOWN = 0.75
        assert result["per_regime_shares"]["TREND_UP"] == pytest.approx(0.25, abs=0.001)
        assert result["per_regime_shares"]["TREND_DOWN"] == pytest.approx(0.75, abs=0.001)


# ===========================================================================
# Tests: build_stability_section
# ===========================================================================

class TestBuildStabilitySection:
    """Integrated stability section from WFV results."""

    def test_with_per_symbol_oos(self):
        """WFV results with per_symbol_oos produce correct section."""
        wfv = {
            "per_symbol_oos": {
                "BTCUSDT": {"oos_expectancy_r": 0.20, "oos_win_rate": 0.60, "oos_trade_count": 150},
                "ETHUSDT": {"oos_expectancy_r": 0.10, "oos_win_rate": 0.52, "oos_trade_count": 100},
            },
            "data_scope": {"symbols": ["BTCUSDT", "ETHUSDT"]},
            "regime_breakdown": {
                "regimes": [
                    {"regime": "TREND_UP", "sample_pct": 0.40, "oos_expectancy_r": 0.20},
                    {"regime": "TREND_DOWN", "sample_pct": 0.30, "oos_expectancy_r": 0.10},
                    {"regime": "RANGE", "sample_pct": 0.20, "oos_expectancy_r": 0.05},
                    {"regime": "TRANSITION", "sample_pct": 0.10, "oos_expectancy_r": 0.02},
                ]
            },
        }
        result = build_stability_section(wfv)
        assert result["num_symbols"] == 2
        assert "BTCUSDT" in result["symbol_metrics"]
        assert "ETHUSDT" in result["symbol_metrics"]
        assert result["symbol_concentration"]["top_symbol"] == "BTCUSDT"
        assert result["regime_concentration"]["top_regime"] == "TREND_UP"

    def test_without_per_symbol_oos(self):
        """WFV results without per_symbol_oos use aggregate fallback."""
        wfv = {
            "oos_summary": {
                "oos_expectancy_r": 0.15,
                "oos_win_rate": 0.55,
                "oos_trade_count": 300,
            },
            "data_scope": {"symbols": ["BTCUSDT"]},
            "regime_breakdown": {
                "regimes": [
                    {"regime": "TREND_UP", "sample_pct": 0.40, "oos_expectancy_r": 0.20},
                ]
            },
        }
        result = build_stability_section(wfv)
        assert result["num_symbols"] == 1
        assert result["symbol_metrics"]["BTCUSDT"]["expectancy_r"] == 0.15
        assert result["symbol_concentration"]["num_symbols"] == 1

    def test_no_regime_data(self):
        """WFV without regime_breakdown returns safe defaults."""
        wfv = {
            "oos_summary": {"oos_expectancy_r": 0.15, "oos_win_rate": 0.55, "oos_trade_count": 300},
            "data_scope": {"symbols": ["BTCUSDT"]},
        }
        result = build_stability_section(wfv)
        assert result["num_symbols"] == 1
        # Regime concentration should have 0 regimes (no data provided)
        assert result["regime_concentration"]["num_regimes"] == 0
        assert result["regime_concentration"]["top_regime"] == "NONE"

    def test_json_serializable(self):
        """Stability section is JSON-serializable."""
        wfv = {
            "per_symbol_oos": {
                "BTCUSDT": {"oos_expectancy_r": 0.15, "oos_win_rate": 0.55, "oos_trade_count": 200},
            },
            "data_scope": {"symbols": ["BTCUSDT"]},
            "regime_breakdown": {
                "regimes": [
                    {"regime": "TREND_UP", "sample_pct": 0.40},
                ]
            },
        }
        result = build_stability_section(wfv)
        encoded = json.dumps(result)
        assert isinstance(encoded, str)


# ===========================================================================
# Tests: classify_symbol_regimes_from_ohlcv
# ===========================================================================

class TestClassifyRegimeFromOhlcv:
    """Regime classification from synthetic OHLCV price data."""

    def _uptrend_data(self, n=200, start=50000.0, step=50.0):
        """Generate monotonically rising price series."""
        closes = np.array([start + i * step for i in range(n)], dtype=np.float64)
        highs = closes + step * 0.5
        lows = closes - step * 0.5
        return closes, highs, lows

    def _downtrend_data(self, n=200, start=60000.0, step=50.0):
        """Generate monotonically falling price series."""
        closes = np.array([start - i * step for i in range(n)], dtype=np.float64)
        highs = closes + step * 0.5
        lows = closes - step * 0.5
        return closes, highs, lows

    def _flat_data(self, n=200, price=50000.0, atr_range=100.0):
        """Generate flat price series with small ATR."""
        closes = np.full(n, price, dtype=np.float64)
        highs = closes + atr_range
        lows = closes - atr_range
        return closes, highs, lows

    def test_uptrend_detected(self):
        """Rising price series detects TREND_UP regime."""
        closes, highs, lows = self._uptrend_data(200)
        result = classify_symbol_regimes_from_ohlcv(closes, highs, lows)
        assert result["last_regime"] == "TREND_UP"
        assert result["total_bars"] == 200
        assert result["regime_counts"]["TREND_UP"] > 0
        assert result["classification_rate"] > 0.0

    def test_downtrend_detected(self):
        """Falling price series detects TREND_DOWN regime."""
        closes, highs, lows = self._downtrend_data(200)
        result = classify_symbol_regimes_from_ohlcv(closes, highs, lows)
        assert result["last_regime"] == "TREND_DOWN"
        assert result["regime_counts"]["TREND_DOWN"] > 0

    def test_flat_detects_range(self):
        """Flat low-volatility series detects RANGE regime."""
        closes, highs, lows = self._flat_data(200, price=50000.0, atr_range=50.0)
        result = classify_symbol_regimes_from_ohlcv(closes, highs, lows)
        assert result["regime_counts"]["RANGE"] > 0

    def test_regime_fractions_sum_to_one(self):
        """Regime fractions sum to approximately 1.0."""
        closes, highs, lows = self._uptrend_data(200)
        result = classify_symbol_regimes_from_ohlcv(closes, highs, lows)
        total = sum(result["regime_fractions"].values())
        assert abs(total - 1.0) < 0.001

    def test_empty_series(self):
        """Empty series returns safe defaults."""
        empty = np.array([], dtype=np.float64)
        result = classify_symbol_regimes_from_ohlcv(empty, empty, empty)
        assert result["total_bars"] == 0
        assert result["last_regime"] == "NONE"

    def test_short_series(self):
        """Short series (<lookback) still returns safe result."""
        closes = np.array([100.0, 101.0], dtype=np.float64)
        highs = closes + 1.0
        lows = closes - 1.0
        result = classify_symbol_regimes_from_ohlcv(closes, highs, lows)
        assert result["total_bars"] == 2
        # All bars should be TRANSITION (insufficient lookback)
        assert result["regime_counts"]["TRANSITION"] == 2

    def test_regime_counts_have_all_keys(self):
        """Result contains all four regime labels."""
        closes, highs, lows = self._uptrend_data(200)
        result = classify_symbol_regimes_from_ohlcv(closes, highs, lows)
        for label in STABILITY_REGIME_LABELS:
            assert label in result["regime_counts"]
            assert label in result["regime_fractions"]


# ===========================================================================
# Tests: Integration with empirical report
# ===========================================================================

class TestIntegrationWithEmpiricalReport:
    """Stability section integrates correctly with empirical report."""

    def test_symbol_stability_in_report(self):
        """Empirical report builder includes symbol_stability section."""
        from alphaforge.reports.empirical import build_empirical_mode_research_report

        # Build WFV results with per_symbol_oos
        wfv = {
            "fold_count": 6,
            "per_fold_metrics": [
                {"fold": i + 1, "sharpe": 0.8, "expectancy_r": 0.15, "win_rate": 0.55, "trade_count": 50}
                for i in range(6)
            ],
            "oos_summary": {
                "oos_sharpe": 0.8,
                "oos_expectancy_r": 0.15,
                "oos_win_rate": 0.55,
                "oos_profit_factor": 1.3,
                "oos_max_drawdown_r": -2.5,
                "oos_trade_count": 300,
            },
            "data_scope": {
                "symbols": ["BTCUSDT", "ETHUSDT"],
                "date_range_start": "2025-01-01T00:00:00Z",
                "date_range_end": "2026-01-01T00:00:00Z",
            },
            "per_symbol_oos": {
                "BTCUSDT": {"oos_expectancy_r": 0.18, "oos_win_rate": 0.58, "oos_trade_count": 180},
                "ETHUSDT": {"oos_expectancy_r": 0.10, "oos_win_rate": 0.52, "oos_trade_count": 120},
            },
            "cost_stress": {
                "baseline_fee_pct": 0.04,
                "baseline_slippage_pct": 0.02,
                "fee_stress_levels": [{"multiplier": 1.0, "oos_expectancy_r": 0.12, "edge_survives": True}],
                "slippage_stress_levels": [{"multiplier": 1.0, "oos_expectancy_r": 0.12, "edge_survives": True}],
                "combined_stress_edge_survives": True,
            },
            "regime_breakdown": {
                "regimes": [
                    {"regime": "TREND_UP", "sample_pct": 0.35, "oos_expectancy_r": 0.20, "edge_present": True},
                    {"regime": "TREND_DOWN", "sample_pct": 0.25, "oos_expectancy_r": 0.12, "edge_present": True},
                    {"regime": "RANGE", "sample_pct": 0.25, "oos_expectancy_r": 0.08, "edge_present": True},
                    {"regime": "TRANSITION", "sample_pct": 0.15, "oos_expectancy_r": 0.05, "edge_present": True},
                ],
                "edge_only_in_rare_regime": False,
            },
        }

        report = build_empirical_mode_research_report("SWING", wfv)

        # Check symbol_stability section exists
        assert "symbol_stability" in report
        ss = report["symbol_stability"]
        assert ss["num_symbols"] == 2
        assert "BTCUSDT" in ss["symbol_metrics"]
        assert "ETHUSDT" in ss["symbol_metrics"]

        # Check per-symbol metrics are real values
        assert ss["symbol_metrics"]["BTCUSDT"]["expectancy_r"] == 0.18
        assert ss["symbol_metrics"]["BTCUSDT"]["trade_count"] == 180

        # Check concentration ratios
        assert ss["symbol_concentration"]["top_symbol"] == "BTCUSDT"
        assert ss["regime_concentration"]["top_regime"] == "TREND_UP"

    def test_regime_breakdown_has_win_rate(self):
        """Regime breakdown entries include oos_win_rate."""
        from alphaforge.reports.empirical import build_empirical_mode_research_report

        wfv = {
            "fold_count": 6,
            "per_fold_metrics": [
                {"fold": i + 1, "sharpe": 0.8, "expectancy_r": 0.15, "win_rate": 0.55, "trade_count": 50}
                for i in range(6)
            ],
            "oos_summary": {
                "oos_sharpe": 0.8,
                "oos_expectancy_r": 0.15,
                "oos_win_rate": 0.55,
                "oos_profit_factor": 1.3,
                "oos_max_drawdown_r": -2.5,
                "oos_trade_count": 300,
            },
            "data_scope": {
                "symbols": ["BTCUSDT"],
                "date_range_start": "2025-01-01T00:00:00Z",
                "date_range_end": "2026-01-01T00:00:00Z",
            },
            "regime_breakdown": {
                "regimes": [
                    {"regime": "TREND_UP", "sample_pct": 0.40, "oos_expectancy_r": 0.20, "oos_win_rate": 0.60, "edge_present": True},
                ],
                "edge_only_in_rare_regime": False,
            },
        }

        report = build_empirical_mode_research_report("SWING", wfv)
        rb = report["regime_breakdown"]
        # When regimes_raw has entries, they pass through (no fallback padding)
        assert len(rb["regimes"]) >= 1
        trend_up = next(r for r in rb["regimes"] if r["regime"] == "TREND_UP")
        assert "oos_win_rate" in trend_up
        assert trend_up["oos_win_rate"] == 0.60

    def test_g5_gate_mapped_for_multi_symbol(self):
        """G5_symbol_stability is in gates_mapped when symbol_count > 1."""
        from alphaforge.reports.empirical import build_empirical_mode_research_report

        wfv = {
            "fold_count": 6,
            "per_fold_metrics": [
                {"fold": i + 1, "sharpe": 0.8, "expectancy_r": 0.15, "win_rate": 0.55, "trade_count": 50}
                for i in range(6)
            ],
            "oos_summary": {
                "oos_sharpe": 0.8,
                "oos_expectancy_r": 0.15,
                "oos_win_rate": 0.55,
                "oos_profit_factor": 1.3,
                "oos_max_drawdown_r": -2.5,
                "oos_trade_count": 300,
            },
            "data_scope": {
                "symbols": ["BTCUSDT", "ETHUSDT"],
                "date_range_start": "2025-01-01T00:00:00Z",
                "date_range_end": "2026-01-01T00:00:00Z",
            },
            "regime_breakdown": {
                "regimes": [{"regime": "TREND_UP", "sample_pct": 1.0, "oos_expectancy_r": 0.20, "edge_present": True}],
                "edge_only_in_rare_regime": False,
            },
        }

        report = build_empirical_mode_research_report("SWING", wfv)
        gr = report["v7_gate_readiness"]
        assert "G5_symbol_stability" in gr["gates_mapped"]
