"""
Tests for DataCatalog — gap analysis and coverage computation.
"""

import os
import tempfile
from datetime import datetime, timezone

from lib.data_lake.catalog import DataCatalog
from lib.data_lake.spec import DatasetSpec


def _spec(**kw):
    """Helper to build a valid DatasetSpec."""
    defaults = dict(
        dataset_id="test-ds-002",
        source="binance",
        market="um_futures",
        symbols=("BTCUSDT", "ETHUSDT"),
        intervals=("1h",),
        data_types=("klines",),
        start=datetime(2022, 1, 1, tzinfo=timezone.utc),
        end=datetime(2022, 1, 3, tzinfo=timezone.utc),
        priority="P0",
        backtest_required=True,
        allow_synthetic=False,
    )
    defaults.update(kw)
    return DatasetSpec(**defaults)


def _catalog(entries=None):
    """Create an isolated DataCatalog backed by a temp file path."""
    tmp = os.path.join(tempfile.mkdtemp(), "test_catalog.json")
    cat = DataCatalog(catalog_path=tmp)
    if entries:
        for e in entries:
            cat.add_entry(**e)
    return cat


# ---------------------------------------------------------------------------
# Basic query and add
# ---------------------------------------------------------------------------


def test_empty_catalog_no_entries():
    """Fresh catalog has no entries."""
    cat = _catalog()
    assert cat.query() == []


def test_add_and_query_symbol():
    """Entry is queryable by symbol filter."""
    cat = _catalog()
    cat.add_entry("BTCUSDT", "1h", 1640995200000, 1641081600000, 24, "abc")
    results = cat.query(symbol="BTCUSDT")
    assert len(results) == 1
    assert results[0]["symbol"] == "BTCUSDT"


# ---------------------------------------------------------------------------
# Gap analysis
# ---------------------------------------------------------------------------


def test_find_gaps_empty_catalog():
    """Empty catalog → full range reported as gap."""
    spec = _spec()
    cat = _catalog()
    gaps = cat.find_gaps(spec)
    assert len(gaps) > 0
    # Two symbols × 1 interval = at least 2 gap entries
    assert len(gaps) >= 2


def test_find_gaps_complete_coverage():
    """Full coverage → no gaps."""
    spec = _spec()
    start_ms = int(spec.start.timestamp() * 1000)
    end_ms = int(spec.end.timestamp() * 1000)
    cat = _catalog([
        {"symbol": "BTCUSDT", "interval": "1h",
         "start_ts": start_ms, "end_ts": end_ms,
         "row_count": 48, "checksum": "a"},
        {"symbol": "ETHUSDT", "interval": "1h",
         "start_ts": start_ms, "end_ts": end_ms,
         "row_count": 48, "checksum": "b"},
    ])
    gaps = cat.find_gaps(spec)
    assert gaps == [], f"Expected no gaps, got {gaps}"


def test_find_gaps_partial_coverage():
    """Partial coverage → correct gaps reported."""
    spec = _spec()
    start_ms = int(spec.start.timestamp() * 1000)
    mid_ms = start_ms + 3600_000  # +1h

    cat = _catalog([
        {"symbol": "BTCUSDT", "interval": "1h",
         "start_ts": start_ms, "end_ts": mid_ms,
         "row_count": 1, "checksum": "a"},
        # ETHUSDT has no entries — full gap expected
    ])

    gaps = cat.find_gaps(spec)
    # BTCUSDT: gap from mid → end
    # ETHUSDT: full gap from start → end
    btc_gaps = [g for g in gaps if g["symbol"] == "BTCUSDT"]
    eth_gaps = [g for g in gaps if g["symbol"] == "ETHUSDT"]

    assert len(btc_gaps) >= 1
    assert len(eth_gaps) >= 1


def test_find_gaps_multiple_intervals():
    """Multiple intervals are each checked independently."""
    spec = _spec(intervals=("1h", "4h"))
    cat = _catalog([
        {"symbol": "BTCUSDT", "interval": "1h",
         "start_ts": 1640995200000, "end_ts": 1641168000000,
         "row_count": 48, "checksum": "a"},
    ])
    gaps = cat.find_gaps(spec)
    # 1h BTCUSDT is covered; 4h BTCUSDT is a gap; ETHUSDT 1h + 4h are gaps
    assert len(gaps) >= 3


# ---------------------------------------------------------------------------
# Coverage percentage
# ---------------------------------------------------------------------------


def test_coverage_pct_zero_when_empty():
    """Empty catalog → 0% coverage."""
    spec = _spec()
    cat = _catalog()
    assert cat.coverage_pct(spec) == 0.0


def test_coverage_pct_100_when_full():
    """Full coverage → 100%."""
    spec = _spec()
    start_ms = int(spec.start.timestamp() * 1000)
    end_ms = int(spec.end.timestamp() * 1000)
    cat = _catalog([
        {"symbol": "BTCUSDT", "interval": "1h",
         "start_ts": start_ms, "end_ts": end_ms,
         "row_count": 48, "checksum": "a"},
        {"symbol": "ETHUSDT", "interval": "1h",
         "start_ts": start_ms, "end_ts": end_ms,
         "row_count": 48, "checksum": "b"},
    ])
    assert cat.coverage_pct(spec) == 100.0


def test_coverage_pct_partial():
    """Partial coverage → fractional percentage."""
    spec = _spec()
    start_ms = int(spec.start.timestamp() * 1000)
    mid_ms = start_ms + 3600_000  # 1h covered

    cat = _catalog([
        {"symbol": "BTCUSDT", "interval": "1h",
         "start_ts": start_ms, "end_ts": mid_ms,
         "row_count": 1, "checksum": "a"},
    ])
    pct = cat.coverage_pct(spec)
    # Coverage should be > 0 but well under 100%
    assert 0 < pct < 100


# ---------------------------------------------------------------------------
# to_summary
# ---------------------------------------------------------------------------


def test_to_summary_structure():
    """to_summary returns expected keys."""
    spec = _spec()
    cat = _catalog()
    summary = cat.to_summary(spec)
    assert "source" in summary
    assert "symbols" in summary
    assert "coverage_pct" in summary
    assert "gap_count" in summary
    assert summary["source"] == "binance"
    assert summary["symbols"] == ["BTCUSDT", "ETHUSDT"]
    assert summary["coverage_pct"] == 0.0
    assert summary["gap_count"] > 0


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_overlapping_entries():
    """Overlapping entries do not cause negative gaps."""
    spec = _spec(symbols=("BTCUSDT",), intervals=("1h",))
    start_ms = int(spec.start.timestamp() * 1000)
    end_ms = int(spec.end.timestamp() * 1000)

    cat = _catalog([
        {"symbol": "BTCUSDT", "interval": "1h",
         "start_ts": start_ms, "end_ts": start_ms + 7200_000,
         "row_count": 2, "checksum": "a"},
        # Overlapping entry
        {"symbol": "BTCUSDT", "interval": "1h",
         "start_ts": start_ms + 3600_000, "end_ts": end_ms,
         "row_count": 2, "checksum": "b"},
    ])
    gaps = cat.find_gaps(spec)
    # Gap should start from end_ms of first entry (which extends to +2h),
    # then jump to max(end_ms, second_entry.end_ts)
    # If spec end is exactly end_ms, there should be no gap
    assert len(gaps) == 0 or gaps[0]["symbol"] != "BTCUSDT"
