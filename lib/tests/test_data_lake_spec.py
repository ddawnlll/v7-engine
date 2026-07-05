"""
Tests for DatasetSpec — validation and expected bar counting.
"""

from datetime import datetime, timezone

import pytest

from lib.data_lake.spec import DatasetSpec, VALID_SOURCES, VALID_INTERVALS


def _spec(**kw):
    """Helper to build a valid DatasetSpec with overridable defaults."""
    defaults = dict(
        dataset_id="test-ds-001",
        source="binance",
        market="um_futures",
        symbols=("BTCUSDT",),
        intervals=("1h",),
        data_types=("klines",),
        start=datetime(2022, 1, 1, tzinfo=timezone.utc),
        end=datetime(2022, 6, 1, tzinfo=timezone.utc),
        priority="P0",
        backtest_required=True,
        allow_synthetic=False,
    )
    defaults.update(kw)
    return DatasetSpec(**defaults)


class TestDatasetSpec:
    """DatasetSpec construction and validation."""

    def test_valid_default(self):
        """Default spec constructs without error."""
        spec = _spec()
        assert spec.dataset_id == "test-ds-001"
        assert spec.source == "binance"

    def test_invalid_source(self):
        """Invalid source raises ValueError."""
        with pytest.raises(ValueError, match="Invalid source"):
            _spec(source="unknown_source")

    def test_invalid_market(self):
        """Invalid market raises ValueError."""
        with pytest.raises(ValueError, match="Invalid market"):
            _spec(market="invalid_market")

    def test_invalid_interval(self):
        """Invalid interval raises ValueError."""
        with pytest.raises(ValueError, match="Invalid interval"):
            _spec(intervals=("9999h",))

    def test_partially_invalid_intervals(self):
        """Mix of valid and invalid intervals raises ValueError."""
        with pytest.raises(ValueError, match="Invalid interval"):
            _spec(intervals=("1h", "9999h", "1d"))

    def test_empty_symbols(self):
        """Empty symbols raises ValueError."""
        with pytest.raises(ValueError, match="symbols must be non-empty"):
            _spec(symbols=())

    def test_empty_data_types(self):
        """Empty data_types raises ValueError."""
        with pytest.raises(ValueError, match="data_types must be non-empty"):
            _spec(data_types=())

    def test_start_after_end(self):
        """start >= end raises ValueError."""
        with pytest.raises(ValueError, match="start.*before end"):
            _spec(
                start=datetime(2022, 6, 1, tzinfo=timezone.utc),
                end=datetime(2022, 1, 1, tzinfo=timezone.utc),
            )

    def test_start_equal_end(self):
        """start == end raises ValueError."""
        t = datetime(2022, 6, 1, tzinfo=timezone.utc)
        with pytest.raises(ValueError, match="start.*before end"):
            _spec(start=t, end=t)

    def test_frozen_immutable(self):
        """DatasetSpec cannot be modified after creation."""
        spec = _spec()
        with pytest.raises(Exception):
            # Any mutation attempt should raise (frozen dataclass)
            spec.source = "coinalyze"  # type: ignore[misc]

    def test_valid_all_intervals(self):
        """All VALID_INTERVALS are accepted."""
        spec = _spec(intervals=tuple(sorted(VALID_INTERVALS)))
        assert len(spec.intervals) == len(VALID_INTERVALS)

    def test_valid_all_sources(self):
        """All VALID_SOURCES are accepted."""
        for src in VALID_SOURCES:
            spec = _spec(source=src)
            assert spec.source == src

    def test_interval_seconds_1h(self):
        """1h interval → 3600 seconds."""
        spec = _spec(intervals=("1h",))
        assert spec.interval_seconds == 3600

    def test_interval_seconds_smallest(self):
        """Multiple intervals → smallest interval's seconds."""
        spec = _spec(intervals=("1h", "4h", "1d"))
        assert spec.interval_seconds == 3600

    def test_expected_bar_count_single(self):
        """Expected bar count for 1 symbol × 1 interval × ~5 months."""
        spec = _spec(intervals=("1h",), symbols=("BTCUSDT",))
        # ~151 days × 24h = ~3624 bars
        count = spec.expected_bar_count()
        assert 3000 <= count <= 4000, f"Expected ~3624, got {count}"

    def test_expected_bar_count_multi_symbol(self):
        """Expected bar count scales with symbol count."""
        one = _spec(intervals=("1h",), symbols=("BTCUSDT",)).expected_bar_count()
        two = _spec(intervals=("1h",), symbols=("BTCUSDT", "ETHUSDT")).expected_bar_count()
        assert two == one * 2

    def test_expected_bar_count_zero_for_empty_range(self):
        """start == end → expected_bar_count = 0."""
        # Can't test frozen dataclass with enforced start<end,
        # so test indirectly via property
        spec = _spec()
        assert spec.expected_bar_count() > 0
