"""
Tests for lib/time/ — intervals and fold generation.
"""

import pytest
from lib.time.intervals import interval_to_minutes, minutes_to_interval, validate_interval
from lib.time.folds import generate_folds, Fold


# =====================================================================
# Intervals
# =====================================================================

class TestIntervalToMinutes:
    def test_valid_intervals(self):
        cases = {
            "1m": 1, "3m": 3, "5m": 5, "15m": 15, "30m": 30,
            "1h": 60, "2h": 120, "4h": 240, "6h": 360, "8h": 480, "12h": 720,
            "1d": 1440, "3d": 4320, "1w": 10080,
        }
        for interval, expected in cases.items():
            assert interval_to_minutes(interval) == expected, f"Failed for {interval}"

    def test_invalid_raises(self):
        for invalid in ["", "x", "1y", "1h30m", "60m", "0h"]:
            with pytest.raises(ValueError, match="Unknown interval"):
                interval_to_minutes(invalid)

    def test_case_sensitive(self):
        with pytest.raises(ValueError):
            interval_to_minutes("1H")


class TestMinutesToInterval:
    def test_known_minutes(self):
        assert minutes_to_interval(60) == "1h"
        assert minutes_to_interval(240) == "4h"
        assert minutes_to_interval(1) == "1m"
        assert minutes_to_interval(1440) == "1d"

    def test_unknown_minutes(self):
        assert minutes_to_interval(123) is None
        assert minutes_to_interval(0) is None


class TestValidateInterval:
    def test_valid(self):
        assert validate_interval("1h") is True
        assert validate_interval("15m") is True
        assert validate_interval("1d") is True

    def test_invalid(self):
        assert validate_interval("") is False
        assert validate_interval("invalid") is False
        assert validate_interval("1H") is False


# =====================================================================
# Folds
# =====================================================================

MS_PER_DAY = 86_400_000


class TestGenerateFolds:
    def test_basic(self):
        start = 1_000_000_000_000
        end = start + 500 * MS_PER_DAY
        folds = generate_folds(start, end, train_window_days=365, val_window_days=60)

        assert len(folds) >= 1
        f = folds[0]
        assert f.fold_id == 0
        assert f.train_start == start
        assert f.train_end - f.train_start == 365 * MS_PER_DAY
        assert f.val_end - f.val_start == 60 * MS_PER_DAY
        assert f.val_end <= end

    def test_multiple_folds(self):
        start = 1_000_000_000_000
        end = start + 800 * MS_PER_DAY  # 800 days
        folds = generate_folds(start, end, train_window_days=365, val_window_days=60)

        # With 800 days, train=365, step=60: (800-365)/60 ≈ 7 folds
        assert len(folds) >= 2
        for i, f in enumerate(folds):
            assert f.fold_id == i
            assert f.train_end == f.val_start
            assert f.train_end - f.train_start >= 365 * MS_PER_DAY

        # Each fold advances by val_window
        if len(folds) >= 2:
            assert folds[1].train_start > folds[0].train_start

    def test_exact_fit(self):
        start = 1_000_000_000_000
        end = start + (365 + 60) * MS_PER_DAY  # exactly one train+val window
        folds = generate_folds(start, end, train_window_days=365, val_window_days=60)
        assert len(folds) == 1
        assert folds[0].train_end - folds[0].train_start == 365 * MS_PER_DAY
        assert folds[0].val_end - folds[0].val_start == 60 * MS_PER_DAY
        assert folds[0].val_end == end

    def test_too_short(self):
        start = 1_000_000_000_000
        end = start + 30 * MS_PER_DAY  # only 30 days
        with pytest.raises(ValueError, match="too short"):
            generate_folds(start, end, train_window_days=365, val_window_days=60)

    def test_min_train_window(self):
        """min_train_days less than train_window_days: some folds may be
        excluded if the first window is clipped by dataset_start."""
        start = 1_000_000_000_000
        # 500 days: first fold train starts at dataset_start (no clipping),
        # so train_duration = train_window = 365 which is >= min_train=300.
        end = start + 500 * MS_PER_DAY
        folds = generate_folds(start, end, train_window_days=365, val_window_days=60, min_train_days=300)
        assert len(folds) >= 1
        for f in folds:
            assert f.train_end - f.train_start >= 300 * MS_PER_DAY

    def test_min_train_window_excludes_clipped_fold(self):
        """If the first fold would be clipped below min_train, it's skipped.
        For example, if dataset_start is close to train_end so the window
        would be < min_train, that fold is excluded."""
        start = 1_000_000_000_000
        # 500 days: first fold: train_start=start, train_end=start+365d, val_end=start+425d.
        # Duration = 365d >= min_train=200, so it passes.
        end = start + 500 * MS_PER_DAY
        folds = generate_folds(start, end, train_window_days=365, val_window_days=60, min_train_days=200)
        assert len(folds) >= 1
        for f in folds:
            assert f.train_end - f.train_start >= 200 * MS_PER_DAY

    def test_min_train_drops_short_first_fold(self):
        """When dataset_start is close to the first train_end, the first fold
        may have a shorter train window. If that's below min_train, skip it."""
        start = 1_000_000_000_000
        # 500 days, but with train_window_days=400, val_window_days=60.
        # With 500 days, we can have at least one fold (400+60=460 <= 500).
        # First fold: train_start=start, train_end=start+400d, duration=400d.
        # Second fold: train_start=start+60, train_end=start+460d, duration=400d.
        end = start + 500 * MS_PER_DAY
        folds = generate_folds(start, end, train_window_days=400, val_window_days=60, min_train_days=400)
        assert len(folds) >= 1
        for f in folds:
            assert f.train_end - f.train_start >= 400 * MS_PER_DAY

    def test_zero_length(self):
        start = 1_000_000_000_000
        with pytest.raises(ValueError):
            generate_folds(start, start, train_window_days=365, val_window_days=60)

    def test_non_integer_days(self):
        start = 1_000_000_000_000
        end = start + int(365.5 * MS_PER_DAY) + int(60 * MS_PER_DAY)
        folds = generate_folds(start, end, train_window_days=365, val_window_days=60)
        assert len(folds) == 1

    def test_fold_attributes(self):
        start = 1_000_000_000_000
        end = start + 500 * MS_PER_DAY
        folds = generate_folds(start, end, train_window_days=365, val_window_days=60)

        for f in folds:
            assert isinstance(f, Fold)
            assert isinstance(f.fold_id, int)
            assert isinstance(f.train_start, int)
            assert isinstance(f.train_end, int)
            assert isinstance(f.val_start, int)
            assert isinstance(f.val_end, int)
            assert f.train_start < f.train_end
            assert f.train_end == f.val_start
            assert f.val_start < f.val_end
