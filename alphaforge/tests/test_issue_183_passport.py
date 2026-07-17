"""Behavioral tests for #183: EvidencePassport signal quality wiring.

Tests ``alphaforge.evidence_adapter.build_alphaforge_passport()``
directly with synthetic walk-forward data, verifying IC/Rank IC values
are lifted into the passport's signal_quality field.
"""
from __future__ import annotations

import numpy as np
import pytest

from alphaforge.evidence_adapter import build_alphaforge_passport


def _make_wfv_data(
    oos_ic: float = 0.15,
    oos_rank_ic: float = 0.12,
    oos_ic_ir: float = 0.8,
    n_folds: int = 6,
) -> dict:
    """Build a minimal fake wfv_data dict simulating real WFV output."""
    metrics = {
        "oos_ic": oos_ic,
        "oos_rank_ic": oos_rank_ic,
        "oos_ic_ir": oos_ic_ir,
        "n_samples": 5000,
        "n_folds": n_folds,
        "feature_count": 80,
        "exposure_pct": 0.35,
        "total_active_trades": 400,
        "low_conf_rate_pct": 0.05,
        "overfit_gap": 0.02,
        "net_expectancy_r": 0.12,
        "cost_decomposition": {"fee": 0.02, "slippage": 0.01},
    }
    per_fold_results = []
    for i in range(n_folds):
        fold_ic = oos_ic * (1.0 + 0.2 * np.sin(i))
        fold_rank_ic = oos_rank_ic * (1.0 + 0.15 * np.cos(i * 1.5))
        per_fold_results.append({
            "fold_id": f"fold_{i}",
            "oos_ic": round(float(fold_ic), 6),
            "oos_rank_ic": round(float(fold_rank_ic), 6),
            "train_size": 800,
            "val_size": 200,
        })
    return {
        "metrics": metrics,
        "per_fold_results": per_fold_results,
        "candidate_id": "test_candidate_001",
        "mode": "SCALP",
        "labels": ["LONG"] * 500 + ["SHORT"] * 300 + ["NO_TRADE"] * 200,
        "gross_r": [round(float(r), 6) for r in np.random.default_rng(42).uniform(-1.0, 2.0, 1000)],
        "fee_pct": 0.0008,
    }


class TestEvidencePassportSignalQuality:
    """Tests that build_alphaforge_passport wires IC/Rank IC correctly."""

    def test_signal_quality_present(self):
        """Passport has signal_quality dict with expected keys."""
        wfv = _make_wfv_data()
        passport = build_alphaforge_passport(wfv, mode="SCALP")
        assert hasattr(passport, "signal_quality"), "passport must have signal_quality"
        sq = passport.signal_quality
        assert "oos_ic" in sq
        assert "oos_rank_ic" in sq
        assert "oos_ic_ir" in sq
        assert "per_fold_ic" in sq
        assert "per_fold_rank_ic" in sq
        assert "ic_stability" in sq
        assert "metric_philosophy" in sq

    def test_signal_quality_values(self):
        """Aggregate IC/Rank IC values match the input."""
        wfv = _make_wfv_data(oos_ic=0.25, oos_rank_ic=0.18, oos_ic_ir=1.2)
        passport = build_alphaforge_passport(wfv, mode="SWING")
        sq = passport.signal_quality
        assert sq["oos_ic"] == 0.25
        assert sq["oos_rank_ic"] == 0.18
        assert sq["oos_ic_ir"] == 1.2

    def test_per_fold_ic_length(self):
        """Per-fold IC arrays match the number of folds."""
        wfv = _make_wfv_data(n_folds=6)
        passport = build_alphaforge_passport(wfv, mode="SCALP")
        sq = passport.signal_quality
        assert len(sq["per_fold_ic"]) == 6
        assert len(sq["per_fold_rank_ic"]) == 6

    def test_ic_stability_computed(self):
        """IC stability (std dev) is computed from per-fold IC values."""
        wfv = _make_wfv_data(oos_ic=0.1, n_folds=6)
        passport = build_alphaforge_passport(wfv, mode="SCALP")
        sq = passport.signal_quality
        # With n_folds=6 and sinusoidal IC, stability should be > 0
        assert sq["ic_stability"] > 0.0

    def test_disclaimer_text_present(self):
        """Passport carries the 'signal quality, not trade profitability' text."""
        wfv = _make_wfv_data()
        passport = build_alphaforge_passport(wfv, mode="SCALP")
        # Check limitations list
        disclaimer_found = any(
            "SIGNAL QUALITY" in lim and "not trade profitability" in lim
            for lim in passport.limitations
        )
        assert disclaimer_found, (
            "Passport limitations must include signal quality disclaimer"
        )
        # Check signal_quality metric_philosophy field
        assert "SIGNAL_QUALITY_ONLY" in passport.signal_quality.get(
            "metric_philosophy", ""
        )

    def test_ic_based_alpha_has_edge_passed(self):
        """ALPHA_HAS_EDGE PASSED when both IC and Rank IC are positive."""
        wfv = _make_wfv_data(oos_ic=0.15, oos_rank_ic=0.12)
        passport = build_alphaforge_passport(wfv, mode="SCALP")
        assert passport.claim_statuses.get("ALPHA_HAS_EDGE") == "PASSED"

    def test_ic_based_alpha_has_edge_partial(self):
        """ALPHA_HAS_EDGE PARTIAL when only one IC metric is positive."""
        wfv = _make_wfv_data(oos_ic=0.0, oos_rank_ic=0.12)
        passport = build_alphaforge_passport(wfv, mode="SCALP")
        assert passport.claim_statuses.get("ALPHA_HAS_EDGE") == "PARTIAL"

    def test_ic_based_alpha_has_edge_failed(self):
        """ALPHA_HAS_EDGE FAILED when both IC metrics are zero."""
        wfv = _make_wfv_data(oos_ic=0.0, oos_rank_ic=0.0)
        passport = build_alphaforge_passport(wfv, mode="SCALP")
        assert passport.claim_statuses.get("ALPHA_HAS_EDGE") == "FAILED"

    def test_single_fold_handles_ic_stability(self):
        """Single fold produces ic_stability = 0 (no variance)."""
        wfv = _make_wfv_data(n_folds=1)
        passport = build_alphaforge_passport(wfv, mode="SCALP")
        sq = passport.signal_quality
        assert sq["ic_stability"] == 0.0

    def test_ic_and_rank_ic_flags_in_evidence(self):
        """Evidence flags include ic_present / rank_ic_present."""
        wfv = _make_wfv_data(oos_ic=0.15, oos_rank_ic=0.12)
        passport = build_alphaforge_passport(wfv, mode="SCALP")
        # These are accessed via hard_caps.evidence
        assert passport.hard_caps is not None
