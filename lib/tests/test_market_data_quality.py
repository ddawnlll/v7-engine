"""
Tests for lib/market_data/quality.py
"""

import pytest
from lib.market_data.quality import (
    compute_expected_count,
    detect_gaps,
    detect_duplicates,
    build_quality_report,
)
from lib.market_data.contracts import KlineRecord


def _kl(ts: int) -> KlineRecord:
    return KlineRecord(
        symbol="T",
        timestamp=ts,
        open=1, high=2, low=1, close=1.5,
        volume=10, quote_volume=15,
        trade_count=10, taker_buy_volume=5, taker_buy_quote_volume=7.5,
        interval="1h", source="binance", is_closed=True,
    )


class TestComputeExpectedCount:
    def test_exact_range(self):
        # 1h interval: 2 hours = 2 candles
        count = compute_expected_count(1_000_000_000_000, 1_000_000_000_000 + 120 * 60_000, 60)
        assert count == 2

    def test_single_candle(self):
        count = compute_expected_count(1_000_000_000_000, 1_000_000_000_000 + 60 * 60_000, 60)
        assert count == 1

    def test_zero_duration(self):
        count = compute_expected_count(1_000_000_000_000, 1_000_000_000_000, 60)
        assert count == 0

    def test_large_range(self):
        # 365 days at 1h = 8760 candles
        ms_per_day = 86_400_000
        count = compute_expected_count(1_000_000_000_000, 1_000_000_000_000 + 365 * ms_per_day, 60)
        assert count == 8760

    def test_15m_interval(self):
        count = compute_expected_count(1_000_000_000_000, 1_000_000_000_000 + 60 * 60_000, 15)
        assert count == 4


class TestDetectGaps:
    def test_no_gaps(self):
        base = 1_000_000_000_000
        records = [_kl(base + i * 3600_000) for i in range(5)]
        gaps = detect_gaps(records, 60)
        assert gaps == []

    def test_single_gap(self):
        base = 1_000_000_000_000
        records = [
            _kl(base),
            _kl(base + 2 * 3600_000),  # skip 1h
        ]
        gaps = detect_gaps(records, 60)
        assert len(gaps) == 1
        assert gaps[0] == (base + 3600_000, base + 2 * 3600_000)

    def test_multiple_gaps(self):
        base = 1_000_000_000_000
        records = [
            _kl(base),
            _kl(base + 2 * 3600_000),   # gap of 1h
            _kl(base + 5 * 3600_000),   # gap of 2h
        ]
        gaps = detect_gaps(records, 60)
        assert len(gaps) == 2
        assert gaps[0] == (base + 3600_000, base + 2 * 3600_000)
        assert gaps[1] == (base + 3 * 3600_000, base + 5 * 3600_000)

    def test_empty_records(self):
        gaps = detect_gaps([], 60)
        assert gaps == []

    def test_single_record(self):
        gaps = detect_gaps([_kl(1_000_000_000_000)], 60)
        assert gaps == []

    def test_back_to_back_no_gap(self):
        base = 1_000_000_000_000
        records = [_kl(base + i * 3600_000) for i in range(3)]
        gaps = detect_gaps(records, 60)
        assert gaps == []


class TestDetectDuplicates:
    def test_no_duplicates(self):
        base = 1_000_000_000_000
        records = [_kl(base + i * 3600_000) for i in range(5)]
        dups = detect_duplicates(records)
        assert dups == []

    def test_one_duplicate(self):
        base = 1_000_000_000_000
        records = [_kl(base), _kl(base), _kl(base + 3600_000)]
        dups = detect_duplicates(records)
        assert dups == [1]

    def test_multiple_duplicates(self):
        base = 1_000_000_000_000
        records = [
            _kl(base),
            _kl(base),
            _kl(base + 3600_000),
            _kl(base + 3600_000),  # duplicate again
        ]
        dups = detect_duplicates(records)
        assert dups == [1, 3]

    def test_all_duplicates(self):
        base = 1_000_000_000_000
        records = [_kl(base) for _ in range(5)]
        dups = detect_duplicates(records)
        assert dups == [1, 2, 3, 4]

    def test_empty(self):
        assert detect_duplicates([]) == []

    def test_single(self):
        assert detect_duplicates([_kl(1_000_000_000_000)]) == []


class TestBuildQualityReport:
    def test_complete(self):
        base = 1_000_000_000_000
        records = [_kl(base + i * 3600_000) for i in range(5)]
        report = build_quality_report(records, 60, expected_count=5)
        assert report.is_complete
        assert report.gap_count == 0
        assert report.total_received == 5
        assert report.total_expected == 5

    def test_with_gaps(self):
        base = 1_000_000_000_000
        records = [_kl(base), _kl(base + 2 * 3600_000)]
        report = build_quality_report(records, 60, expected_count=3)
        assert not report.is_complete
        assert report.gap_count == 1
        assert len(report.warnings) >= 1
        assert any("gap" in w.lower() for w in report.warnings)

    def test_with_duplicates(self):
        base = 1_000_000_000_000
        records = [_kl(base), _kl(base), _kl(base + 3600_000)]
        report = build_quality_report(records, 60, expected_count=2)
        assert report.duplicate_count == 1
        assert any("duplicate" in w.lower() for w in report.warnings)

    def test_missing_records(self):
        records = []
        report = build_quality_report(records, 60, expected_count=10)
        assert not report.is_complete
        assert report.total_received == 0
        assert any("Expected" in w for w in report.warnings)
