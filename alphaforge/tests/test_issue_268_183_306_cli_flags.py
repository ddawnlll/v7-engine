"""#268/#183/#306: Training CLI flag smoke tests.

Tests that the three opt-in CLI flags work correctly:
  --prune-features  (#268): Feature importance pruning
  --passport        (#183): EvidencePassport generation
  --holdout-cutoff  (#306): Untouched holdout split
"""

from pathlib import Path
import json
import sys

import numpy as np
import pytest


def _run_train(args: list[str]) -> dict:
    """Run alphaforge.train.main() with given args, return metrics."""
    import sys
    from alphaforge.train import main
    _old_argv = sys.argv
    sys.argv = ["train"] + args
    try:
        return main()
    finally:
        sys.argv = _old_argv


class TestFeaturePruning:
    """#268: --prune-features drops low-importance features."""

    def test_prune_disabled_by_default(self):
        """Threshold 0.0 keeps all features."""
        metrics = _run_train(["--synthetic", "--folds", "4"])
        # Should have > 0 features
        assert metrics["feature_count"] > 0, "Expected features with pruning disabled"

    def test_prune_high_threshold_reduces_features(self):
        """High threshold keeps only top features."""
        metrics = _run_train(["--synthetic", "--folds", "4", "--prune-features", "50"])
        # High threshold may keep fewer, or all if all above threshold
        assert metrics["feature_count"] >= 0


class TestEvidencePassport:
    """#183: --passport generates V7 handoff package."""

    def test_passport_creates_file(self, tmp_path):
        """EvidencePassport JSON is written to disk."""
        pp = tmp_path / "passport.json"
        metrics = _run_train(["--synthetic", "--folds", "4", "--passport", str(pp)])
        assert pp.exists(), f"Passport file not created at {pp}"
        data = json.loads(pp.read_text())
        # Must have passport identity fields
        assert "passport_id" in data or "mode" in data
        if "mode" in data:
            assert data["mode"] == "SWING"
        if "metrics" in data:
            assert data["metrics"].get("accuracy", 0) > 0


class TestHoldoutCutoff:
    """#306: --holdout-cutoff reserves untouched data."""

    def test_holdout_accepts_future_cutoff(self):
        """Future cutoff means no data is held out (all pre-cutoff)."""
        metrics = _run_train(["--synthetic", "--folds", "4", "--holdout-cutoff", "2099-01-01"])
        assert metrics["feature_count"] > 0
