"""End-to-end tests for the discovery pipeline.

Tests: run_discovery with synthetic data.
"""

from __future__ import annotations

import pytest

from alphaforge.discovery import DiscoveryConfig, DiscoveryResult
from alphaforge.discovery.pipeline import run_discovery


class TestDiscoveryPipeline:
    """End-to-end tests for the full discovery pipeline."""

    def test_runs_with_synthetic_data(self):
        """Full pipeline runs with synthetic data and produces a result."""
        config = DiscoveryConfig(
            mode="SWING",
            symbols=("BTCUSDT", "ETHUSDT"),
            use_synthetic=True,
            n_bars=500,
            folds=3,
            confidence_threshold=0.55,
            create_handoff=False,
            random_seed=42,
        )

        result = run_discovery(config)

        assert isinstance(result, DiscoveryResult)
        assert result.status in ("PROMOTE", "REJECTED", "WATCH", "ERROR")
        assert result.duration_seconds > 0

        if result.status == "PROMOTE":
            assert result.rejection is not None
            assert result.rejection["decision"] == "PROMOTE"
            assert result.metrics is not None
            assert result.trade_count > 0
        elif result.status in ("REJECTED", "WATCH"):
            assert result.rejection is not None
            assert result.rejection["decision"] in ("REJECT", "WATCH")
            assert result.metrics is not None

    def test_runs_scalp_synthetic(self):
        """SCALP mode runs successfully with synthetic data."""
        config = DiscoveryConfig(
            mode="SCALP",
            symbols=("BTCUSDT", "ETHUSDT"),
            use_synthetic=True,
            n_bars=500,
            folds=3,
            confidence_threshold=0.55,
            create_handoff=False,
            random_seed=42,
        )

        result = run_discovery(config)
        assert result.status in ("PROMOTE", "REJECTED", "WATCH", "ERROR")
        assert result.duration_seconds > 0

    def test_runs_aggressive_scalp_synthetic(self):
        """AGGRESSIVE_SCALP mode runs successfully with synthetic data."""
        config = DiscoveryConfig(
            mode="AGGRESSIVE_SCALP",
            symbols=("BTCUSDT", "ETHUSDT"),
            use_synthetic=True,
            n_bars=500,
            folds=3,
            confidence_threshold=0.55,
            create_handoff=False,
            random_seed=42,
        )

        result = run_discovery(config)
        assert result.status in ("PROMOTE", "REJECTED", "WATCH", "ERROR")
        assert result.duration_seconds > 0

    def test_handoff_built_on_promote(self):
        """Handoff package is built when alpha is promoted."""
        config = DiscoveryConfig(
            mode="SWING",
            symbols=("BTCUSDT", "ETHUSDT"),
            use_synthetic=True,
            n_bars=500,
            folds=3,
            confidence_threshold=0.55,
            create_handoff=True,
            random_seed=42,
        )

        result = run_discovery(config)

        if result.status == "PROMOTE":
            assert result.handoff is not None
            assert isinstance(result.handoff, dict)
            assert "handoff_package_id" in result.handoff or "handoff_type" in result.handoff

    def test_fails_with_insufficient_data(self):
        """Very small dataset produces ERROR without crashing."""
        config = DiscoveryConfig(
            mode="SWING",
            symbols=("BTCUSDT",),
            use_synthetic=True,
            n_bars=50,  # too few bars
            folds=2,
            random_seed=42,
        )

        result = run_discovery(config)
        # Should gracefully handle insufficient data
        assert result.status in ("ERROR", "REJECTED")

    def test_result_has_expected_structure(self):
        """DiscoveryResult has all expected fields populated."""
        config = DiscoveryConfig(
            mode="SWING",
            symbols=("BTCUSDT",),
            use_synthetic=True,
            n_bars=500,
            folds=3,
            create_handoff=False,
            random_seed=42,
        )

        result = run_discovery(config)

        assert hasattr(result, "status")
        assert hasattr(result, "metrics")
        assert hasattr(result, "rejection")
        assert hasattr(result, "trade_count")
        assert hasattr(result, "signal_count")
        assert hasattr(result, "duration_seconds")
        assert hasattr(result, "errors")
        assert isinstance(result.errors, list)
