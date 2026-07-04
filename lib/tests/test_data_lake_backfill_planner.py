"""
Tests for BackfillPlanner — gap-driven manifest generation.
"""

import os
import tempfile
from datetime import datetime, timezone

from lib.data_lake.backfill_planner import (
    BackfillPlanner,
    DownloadEntry,
    DownloadManifest,
    chunk_manifest,
)
from lib.data_lake.catalog import DataCatalog
from lib.data_lake.spec import DatasetSpec


def _spec(**kw):
    """Build a valid DatasetSpec with overridable defaults."""
    defaults = dict(
        dataset_id="test-backfill-001",
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
# DownloadEntry and DownloadManifest basics
# ---------------------------------------------------------------------------


def test_download_entry_defaults():
    """DownloadEntry uses sensible defaults for estimated_rows and source_url."""
    entry = DownloadEntry(
        symbol="BTCUSDT",
        interval="1h",
        data_type="klines",
        start_ms=1640995200000,
        end_ms=1641081600000,
    )
    assert entry.estimated_rows == 0
    assert entry.source_url == ""


def test_download_entry_frozen():
    """DownloadEntry cannot be modified after creation."""
    entry = DownloadEntry(
        symbol="BTCUSDT",
        interval="1h",
        data_type="klines",
        start_ms=1640995200000,
        end_ms=1641081600000,
    )
    try:
        entry.symbol = "ETHUSDT"  # type: ignore[misc]
        assert False, "Should have raised"
    except Exception:
        pass


def test_download_manifest_frozen():
    """DownloadManifest cannot be modified after creation."""
    entry = DownloadEntry(
        symbol="BTCUSDT",
        interval="1h",
        data_type="klines",
        start_ms=1640995200000,
        end_ms=1641081600000,
    )
    manifest = DownloadManifest(
        manifest_id="test-uuid",
        dataset_spec={"source": "binance"},
        entries=(entry,),
        total_entries=1,
        total_estimated_rows=24,
        source="binance",
        generated_at="2026-01-01T00:00:00",
    )
    try:
        manifest.entries = ()  # type: ignore[misc]
        assert False, "Should have raised"
    except Exception:
        pass


# ---------------------------------------------------------------------------
# BackfillPlanner.plan
# ---------------------------------------------------------------------------


def test_plan_empty_catalog():
    """Empty catalog → full range reported as DownloadEntries."""
    spec = _spec()
    cat = _catalog()
    manifest = BackfillPlanner.plan(spec, cat)

    assert manifest.source == "binance"
    assert manifest.total_entries > 0
    assert manifest.total_estimated_rows > 0
    assert len(manifest.entries) == manifest.total_entries

    # 2 symbols × 1 interval = at least 2 entries (full gaps)
    assert manifest.total_entries >= 2

    # Each entry should cover the full spec range for its symbol
    start_ms = int(spec.start.timestamp() * 1000)
    end_ms = int(spec.end.timestamp() * 1000)
    for entry in manifest.entries:
        assert entry.symbol in ("BTCUSDT", "ETHUSDT")
        assert entry.interval == "1h"
        assert entry.data_type == "klines"
        assert entry.start_ms >= start_ms
        assert entry.end_ms <= end_ms
        assert entry.estimated_rows > 0


def test_plan_partial_catalog():
    """Partial catalog → only missing ranges reported."""
    spec = _spec()
    start_ms = int(spec.start.timestamp() * 1000)
    mid_ms = start_ms + 3600_000  # +1h

    # Only BTCUSDT has partial coverage (1h), ETHUSDT has nothing
    cat = _catalog([
        {"symbol": "BTCUSDT", "interval": "1h",
         "start_ts": start_ms, "end_ts": mid_ms,
         "row_count": 1, "checksum": "a"},
    ])

    manifest = BackfillPlanner.plan(spec, cat)

    # We should have entries for:
    # - BTCUSDT: gap from mid_ms → end_ms
    # - ETHUSDT: full gap from start_ms → end_ms
    assert manifest.total_entries >= 2

    btc_entries = [e for e in manifest.entries if e.symbol == "BTCUSDT"]
    eth_entries = [e for e in manifest.entries if e.symbol == "ETHUSDT"]

    assert len(btc_entries) >= 1
    assert len(eth_entries) >= 1

    # BTCUSDT gap should start at mid_ms
    assert btc_entries[0].start_ms >= mid_ms
    # ETHUSDT gap should start at start_ms
    assert eth_entries[0].start_ms == start_ms


def test_plan_full_coverage():
    """Full coverage → empty (zero-entry) manifest."""
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

    manifest = BackfillPlanner.plan(spec, cat)
    assert manifest.total_entries == 0
    assert manifest.entries == ()
    assert manifest.total_estimated_rows == 0


def test_plan_manifest_id_is_uuid():
    """Manifest ID is a valid UUID string."""
    spec = _spec()
    cat = _catalog()
    manifest = BackfillPlanner.plan(spec, cat)
    # Should be a valid UUID (36 chars, 4 hyphens)
    assert len(manifest.manifest_id) == 36
    assert manifest.manifest_id.count("-") == 4


def test_plan_dataset_spec_preserved():
    """Dataset spec is preserved in the manifest as a dict."""
    spec = _spec()
    cat = _catalog()
    manifest = BackfillPlanner.plan(spec, cat)
    ds = manifest.dataset_spec
    assert ds["dataset_id"] == "test-backfill-001"
    assert ds["source"] == "binance"
    assert ds["market"] == "um_futures"
    assert ds["symbols"] == ["BTCUSDT", "ETHUSDT"]
    assert ds["intervals"] == ["1h"]
    assert ds["data_types"] == ["klines"]


def test_plan_generated_at_is_set():
    """generated_at is a non-empty ISO string."""
    spec = _spec()
    cat = _catalog()
    manifest = BackfillPlanner.plan(spec, cat)
    assert isinstance(manifest.generated_at, str)
    assert len(manifest.generated_at) > 0


# ---------------------------------------------------------------------------
# estimate_size
# ---------------------------------------------------------------------------


def test_estimate_size_basic():
    """Estimate scales with total rows (~1 KB per 1000 bars)."""
    entries = tuple(
        DownloadEntry(symbol="X", interval="1h", data_type="k",
                      start_ms=0, end_ms=3600_000 * 1000,
                      estimated_rows=1000)
        for _ in range(10)
    )
    manifest = DownloadManifest(
        manifest_id="test",
        dataset_spec={},
        entries=entries,
        total_entries=10,
        total_estimated_rows=10_000,
        source="binance",
        generated_at="2026-01-01T00:00:00",
    )
    # 10 000 bars → ~10 KB (10*1024=10240)
    size = BackfillPlanner.estimate_size(manifest)
    assert size == 10240


def test_estimate_size_min_one():
    """Even empty manifests estimate at least 1 byte."""
    manifest = DownloadManifest(
        manifest_id="test",
        dataset_spec={},
        entries=(),
        total_entries=0,
        total_estimated_rows=0,
        source="binance",
        generated_at="2026-01-01T00:00:00",
    )
    assert BackfillPlanner.estimate_size(manifest) >= 1


# ---------------------------------------------------------------------------
# chunk_manifest
# ---------------------------------------------------------------------------


def test_chunk_manifest():
    """100 entries → 2 chunks of 50."""
    entries = tuple(
        DownloadEntry(
            symbol=f"SYM{i}", interval="1h", data_type="k",
            start_ms=0, end_ms=3600_000,
            estimated_rows=i,
        )
        for i in range(100)
    )
    manifest = DownloadManifest(
        manifest_id="big-manifest",
        dataset_spec={"source": "binance"},
        entries=entries,
        total_entries=100,
        total_estimated_rows=sum(i for i in range(100)),
        source="binance",
        generated_at="2026-01-01T00:00:00",
    )

    chunks = chunk_manifest(manifest, chunk_size=50)
    assert len(chunks) == 2
    assert chunks[0].total_entries == 50
    assert chunks[1].total_entries == 50
    # Each chunk has its own UUID
    assert chunks[0].manifest_id != chunks[1].manifest_id
    # Total rows preserved across chunks
    total_chunked = chunks[0].total_estimated_rows + chunks[1].total_estimated_rows
    assert total_chunked == manifest.total_estimated_rows


def test_chunk_manifest_small():
    """Fewer entries than chunk_size → single chunk."""
    entries = tuple(
        DownloadEntry(
            symbol="X", interval="1h", data_type="k",
            start_ms=0, end_ms=3600_000,
        )
        for _ in range(3)
    )
    manifest = DownloadManifest(
        manifest_id="small", dataset_spec={},
        entries=entries, total_entries=3,
        total_estimated_rows=0, source="binance",
        generated_at="now",
    )
    chunks = chunk_manifest(manifest, chunk_size=50)
    assert len(chunks) == 1
    assert chunks[0].total_entries == 3


def test_chunk_manifest_empty():
    """Empty manifest → single empty chunk."""
    manifest = DownloadManifest(
        manifest_id="empty", dataset_spec={},
        entries=(), total_entries=0,
        total_estimated_rows=0, source="binance",
        generated_at="now",
    )
    chunks = chunk_manifest(manifest)
    assert len(chunks) == 1
    assert chunks[0].total_entries == 0


def test_chunk_manifest_uneven():
    """Uneven split: 75 entries with chunk_size=50 → 2 chunks (50 + 25)."""
    entries = tuple(
        DownloadEntry(
            symbol=f"S{i}", interval="1h", data_type="k",
            start_ms=0, end_ms=3600_000,
        )
        for i in range(75)
    )
    manifest = DownloadManifest(
        manifest_id="uneven", dataset_spec={},
        entries=entries, total_entries=75,
        total_estimated_rows=0, source="binance",
        generated_at="now",
    )
    chunks = chunk_manifest(manifest, chunk_size=50)
    assert len(chunks) == 2
    assert chunks[0].total_entries == 50
    assert chunks[1].total_entries == 25


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_manifest_frozen():
    """Cannot modify manifest after creation (frozen dataclass)."""
    spec = _spec()
    cat = _catalog()
    manifest = BackfillPlanner.plan(spec, cat)
    try:
        manifest.manifest_id = "new-id"  # type: ignore[misc]
        assert False, "Should have raised"
    except Exception:
        pass
