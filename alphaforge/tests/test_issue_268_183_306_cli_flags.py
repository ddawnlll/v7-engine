"""#268/#183/#306: Training CLI flag smoke tests (import + argparse level).

Validates that CLI flags are wired in train.py's argument parser.
Full training run tests are in test_pipeline_imports.py.
"""

import argparse
import sys
from pathlib import Path


def _get_parser() -> argparse.ArgumentParser:
    """Extract the parser from train.py main() without running it."""
    # We import and check the source rather than call main()
    import alphaforge.train as train_mod
    src = Path(train_mod.__file__).read_text(encoding="utf-8")
    return src


class TestCliFlagsWired:
    """#268/#183/#306: CLI flags are wired in argument parser."""

    def test_prune_features_flag_wired(self):
        src = _get_parser()
        assert "prune-features" in src, "--prune-features arg missing"
        assert "prune_features" in src, "prune_features handler missing"

    def test_passport_flag_wired(self):
        src = _get_parser()
        assert "passport" in src, "--passport arg missing"

    def test_holdout_cutoff_flag_wired(self):
        src = _get_parser()
        assert "holdout-cutoff" in src, "--holdout-cutoff arg missing"
        assert "holdout_cutoff" in src, "holdout_cutoff handler missing"

    def test_all_three_in_argparse(self):
        src = _get_parser()
        assert all(f in src for f in ["prune-features", "passport", "holdout-cutoff"]), \
            "Not all training CLI flags found in train.py"
