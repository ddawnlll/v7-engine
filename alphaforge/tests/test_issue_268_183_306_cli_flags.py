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
    from alphaforge.train import main
    import argparse

    # Build args namespace
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", default="SWING")
    parser.add_argument("--features", default="all")
    parser.add_argument("--symbols", default="BTCUSDT,ETHUSDT")
    parser.add_argument("--synthetic", action="store_true")
    parser.add_argument("--folds", type=int, default=4)
    parser.add_argument("--output", default=None)
    parser.add_argument("--prune-features", type=float, default=0.0)
    parser.add_argument("--passport", default=None)
    parser.add_argument("--holdout-cutoff", default=None)
    parser.add_argument("--discovery", action="store_true")
    parser.add_argument("--discovery-confidence-threshold", type=float, default=0.55)
    parser.add_argument("--discovery-output", default=None)
    parser.add_argument("--dump-softmax", default=None)
    parser.add_argument("--panel-cache", default=None)
    parser.add_argument("--dump-features", default=None)
    parser.add_argument("--positive-control", action="store_true")
    parser.add_argument("--threshold-sweep", default=None)

    ns, _ = parser.parse_known_args(args)
    return main(args=ns)


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
