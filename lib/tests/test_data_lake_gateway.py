"""Tests for DataGateway — unified read interface for the data lake."""

from __future__ import annotations

import os
import pathlib
import tempfile
from datetime import datetime, timezone

import pandas as pd
import pytest

from lib.data_lake.catalog import DataCatalog
from lib.data_lake.gateway import KLINES_COLUMNS, DataGateway
from lib.data_lake.spec import DatasetSpec


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _spec(**kw: object) -> DatasetSpec:
    """Build a valid DatasetSpec with overridable defaults."""
    defaults: dict = dict(
        dataset_id="test-gw-001",
        source="binance",
        market="um_futures",
        symbols=("BTCUSDT",),
        intervals=("1h",),
        data_types=("klines",),
        start=datetime(2024, 1, 1, tzinfo=timezone.utc),
        end=datetime(2024, 1, 3, tzinfo=timezone.utc),
        priority="P0",
        backtest_required=True,
        allow_synthetic=False,
    )
    defaults.update(kw)
    return DatasetSpec(**defaults)


def _catalog(tmpdir: str, entries: list[dict] | None = None) -> DataCatalog:
    """Create an isolated DataCatalog backed by a temp file path."""
    cat = DataCatalog(catalog_path=os.path.join(tmpdir, "test_catalog.json"))
    if entries:
        for e in entries:
            cat.add_entry(**e)
    return cat


def _make_parquet(
    directory: pathlib.Path,
    filename: str,
    rows: list[dict],
) -> pathlib.Path:
    """Write a small parquet file at *directory* / *filename* with *rows*."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / filename
    df = pd.DataFrame(rows)
    df.to_parquet(path, index=False)
    return path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestListAvailableSymbols:
    """list_available_symbols scans the bronze klines directory tree."""

    def test_finds_existing_symbols(self):
        """Directories under bronze/binance/um/klines are discovered."""
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = pathlib.Path(tmpdir)

            # Create bronze klines directories for two symbols
            base = data_dir / "bronze" / "binance" / "um" / "klines"
            (base / "BTCUSDT" / "1h").mkdir(parents=True)
            (base / "ETHUSDT" / "15m").mkdir(parents=True)

            gateway = DataGateway(data_dir=str(data_dir))
            symbols = gateway.list_available_symbols("klines")

            assert symbols == ["BTCUSDT", "ETHUSDT"]

    def test_empty_when_no_data(self):
        """Empty data lake returns empty list."""
        with tempfile.TemporaryDirectory() as tmpdir:
            gateway = DataGateway(data_dir=tmpdir)
            assert gateway.list_available_symbols("klines") == []

    def test_caching(self):
        """Second call returns cached result without re-scanning."""
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = pathlib.Path(tmpdir)
            base = data_dir / "bronze" / "binance" / "um" / "klines"
            (base / "BTCUSDT" / "1h").mkdir(parents=True)

            gateway = DataGateway(data_dir=str(data_dir))
            assert gateway.list_available_symbols("klines") == ["BTCUSDT"]

            # Add a new directory AFTER the first listing
            (base / "ETHUSDT" / "15m").mkdir(parents=True)

            # Without cache invalidation, the old result is returned
            assert gateway.list_available_symbols("klines") == ["BTCUSDT"]

            # After invalidation, the new directory is visible
            gateway.invalidate_cache()
            assert sorted(gateway.list_available_symbols("klines")) == [
                "BTCUSDT",
                "ETHUSDT",
            ]

    def test_funding_rate_symbols(self):
        """list_available_symbols works with funding_rate data type."""
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = pathlib.Path(tmpdir)
            base = data_dir / "raw" / "binance" / "um" / "fundingRate"
            (base / "BTCUSDT").mkdir(parents=True)
            (base / "ETHUSDT").mkdir(parents=True)

            gateway = DataGateway(data_dir=str(data_dir))
            symbols = gateway.list_available_symbols("funding_rate")

            assert sorted(symbols) == ["BTCUSDT", "ETHUSDT"]

    def test_unknown_data_type_returns_empty(self):
        """Unknown data_type returns empty list without crashing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            gateway = DataGateway(data_dir=tmpdir)
            assert gateway.list_available_symbols("unknown_type") == []


class TestResolvePath:
    """resolve_path returns correct directory paths."""

    def test_bronze_klines(self):
        """Bronze klines path matches expected structure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            gateway = DataGateway(data_dir=tmpdir)
            p = gateway.resolve_path("BTCUSDT", "1h", "klines", "bronze")

            expected = (
                pathlib.Path(tmpdir)
                / "bronze" / "binance" / "um" / "klines"
                / "BTCUSDT" / "1h"
            )
            assert p == expected
            assert not p.exists()  # directory not created by resolve

    def test_raw_klines(self):
        """Raw klines path resolves correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            gateway = DataGateway(data_dir=tmpdir)
            p = gateway.resolve_path("ETHUSDT", "15m", "klines", "raw")

            expected = (
                pathlib.Path(tmpdir)
                / "raw" / "binance" / "um" / "klines"
                / "ETHUSDT" / "15m"
            )
            assert p == expected

    def test_funding_rate(self):
        """Funding rate path (no interval) resolves correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            gateway = DataGateway(data_dir=tmpdir)
            p = gateway.resolve_path(
                "BTCUSDT", "", "funding_rate", "raw"
            )

            expected = (
                pathlib.Path(tmpdir)
                / "raw" / "binance" / "um" / "fundingRate"
                / "BTCUSDT"
            )
            assert p == expected

    def test_unknown_layer_raises(self):
        """Unknown layer raises ValueError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            gateway = DataGateway(data_dir=tmpdir)
            with pytest.raises(ValueError, match="Unknown layer"):
                gateway.resolve_path("BTCUSDT", "1h", "klines", "unknown_layer")

    def test_unknown_data_type_raises(self):
        """Unknown data_type raises ValueError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            gateway = DataGateway(data_dir=tmpdir)
            with pytest.raises(ValueError, match="Unknown data_type"):
                gateway.resolve_path("BTCUSDT", "1h", "invalid_type", "bronze")

    def test_symbol_uppercased(self):
        """Symbol is uppercased in the resolved path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            gateway = DataGateway(data_dir=tmpdir)
            p = gateway.resolve_path("btcusdt", "1h", "klines", "bronze")
            assert "BTCUSDT" in p.parts
            assert "btcusdt" not in p.parts


class TestCoverageSummary:
    """coverage_summary delegates to DataCatalog.to_summary."""

    def test_returns_expected_keys(self):
        """Coverage summary contains required metadata keys."""
        with tempfile.TemporaryDirectory() as tmpdir:
            spec = _spec()
            catalog = _catalog(tmpdir)
            gateway = DataGateway(data_dir=tmpdir, catalog=catalog)

            summary = gateway.coverage_summary(spec)

            assert isinstance(summary, dict)
            assert "source" in summary
            assert "symbols" in summary
            assert "intervals" in summary
            assert "data_types" in summary
            assert "coverage_pct" in summary
            assert "gap_count" in summary
            assert "expected_bar_count" in summary
            assert "backtest_required" in summary
            assert "allow_synthetic" in summary
            assert summary["source"] == "binance"
            assert summary["symbols"] == ["BTCUSDT"]
            assert summary["coverage_pct"] == 0.0
            assert summary["gap_count"] > 0

    def test_with_catalog_entries(self):
        """Coverage summary reflects populated catalog entries."""
        with tempfile.TemporaryDirectory() as tmpdir:
            spec = _spec()
            start_ms = int(spec.start.timestamp() * 1000)
            end_ms = int(spec.end.timestamp() * 1000)
            catalog = _catalog(tmpdir, [
                {"symbol": "BTCUSDT", "interval": "1h",
                 "start_ts": start_ms, "end_ts": end_ms,
                 "row_count": 48, "checksum": "abc"},
            ])
            gateway = DataGateway(data_dir=tmpdir, catalog=catalog)

            summary = gateway.coverage_summary(spec)

            assert summary["coverage_pct"] == 100.0
            assert summary["gap_count"] == 0


class TestEmptyCatalog:
    """Graceful fallback when no catalog is provided."""

    def test_default_catalog_created(self):
        """Gateway creates an in-memory catalog when none is given."""
        with tempfile.TemporaryDirectory() as tmpdir:
            gateway = DataGateway(data_dir=tmpdir)
            assert gateway._catalog is not None
            # Default catalog should be usable
            assert gateway._catalog.query() == []

    def test_coverage_with_default_catalog(self):
        """coverage_summary works with the auto-created catalog."""
        with tempfile.TemporaryDirectory() as tmpdir:
            spec = _spec()
            gateway = DataGateway(data_dir=tmpdir)
            summary = gateway.coverage_summary(spec)
            assert isinstance(summary, dict)
            assert summary["coverage_pct"] == 0.0

    def test_coverage_with_empty_explicit_catalog(self):
        """coverage_summary works with an explicit empty catalog."""
        with tempfile.TemporaryDirectory() as tmpdir:
            spec = _spec()
            catalog = _catalog(tmpdir)
            gateway = DataGateway(data_dir=tmpdir, catalog=catalog)

            summary = gateway.coverage_summary(spec)
            assert summary["coverage_pct"] == 0.0
            assert summary["gap_count"] > 0


class TestReadRaisesOnMissingSymbol:
    """read_klines / read_funding_rate raise FileNotFoundError."""

    def test_read_klines_missing_symbol(self):
        """FileNotFoundError when symbol has no data in bronze or raw."""
        with tempfile.TemporaryDirectory() as tmpdir:
            gateway = DataGateway(data_dir=tmpdir)
            start = datetime(2024, 1, 1, tzinfo=timezone.utc)
            end = datetime(2024, 2, 1, tzinfo=timezone.utc)

            with pytest.raises(FileNotFoundError, match="No klines data"):
                gateway.read_klines("NONEXISTENT", "1h", start, end)

    def test_read_funding_rate_missing_symbol(self):
        """FileNotFoundError when symbol has no funding rate data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            gateway = DataGateway(data_dir=tmpdir)
            start = datetime(2024, 1, 1, tzinfo=timezone.utc)
            end = datetime(2024, 2, 1, tzinfo=timezone.utc)

            with pytest.raises(FileNotFoundError, match="No funding rate data"):
                gateway.read_funding_rate("NONEXISTENT", start, end)

    def test_read_klines_invalid_source_layer(self):
        """Invalid source layer raises ValueError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            gateway = DataGateway(data_dir=tmpdir)
            start = datetime(2024, 1, 1, tzinfo=timezone.utc)
            end = datetime(2024, 2, 1, tzinfo=timezone.utc)

            with pytest.raises(ValueError, match="Unknown source layer"):
                gateway.read_klines("BTCUSDT", "1h", start, end, source="invalid")


class TestReadActualData:
    """Happy-path: read_klines with actual parquet files."""

    def test_read_bronze_klines(self):
        """Successfully reads and filters klines from bronze parquet files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = pathlib.Path(tmpdir)
            gateway = DataGateway(data_dir=str(data_dir))

            start = datetime(2024, 1, 1, tzinfo=timezone.utc)
            end = datetime(2024, 1, 3, tzinfo=timezone.utc)
            start_ms = int(start.timestamp() * 1000)
            end_ms = int(end.timestamp() * 1000)

            # Create three parquet files with hourly klines spanning 48 hours
            rows = [
                {
                    "timestamp": start_ms + i * 3600_000,
                    "open": 40000.0 + i,
                    "high": 40100.0 + i,
                    "low": 39900.0 + i,
                    "close": 40050.0 + i,
                    "volume": 100.0 + i,
                    "quote_volume": 4_000_000.0,
                    "trade_count": 1000 + i,
                    "taker_buy_base_volume": 50.0 + i,
                    "taker_buy_quote_volume": 2_000_000.0,
                }
                for i in range(48)
            ]

            # January data goes into 2024/01.parquet
            jan_rows = [r for r in rows if r["timestamp"] < start_ms + 31 * 24 * 3600_000]
            _make_parquet(
                data_dir / "bronze" / "binance" / "um" / "klines" / "BTCUSDT" / "1h" / "2024",
                "01.parquet",
                jan_rows,
            )

            df = gateway.read_klines("BTCUSDT", "1h", start, end)

            assert isinstance(df, pd.DataFrame)
            assert list(df.columns) == KLINES_COLUMNS
            # 48 hours from Jan 1 to Jan 3 = 48 rows
            assert len(df) == 48

            # All timestamps within [start, end)
            assert df["timestamp"].min() >= start_ms
            assert df["timestamp"].max() < end_ms

            # Sorted by timestamp
            assert df["timestamp"].is_monotonic_increasing

    def test_fallback_to_raw(self):
        """Falls back to raw when bronze has no data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = pathlib.Path(tmpdir)
            gateway = DataGateway(data_dir=str(data_dir))

            start = datetime(2024, 1, 1, tzinfo=timezone.utc)
            end = datetime(2024, 1, 2, tzinfo=timezone.utc)
            start_ms = int(start.timestamp() * 1000)

            raw_rows = [
                {
                    "timestamp": start_ms + i * 3600_000,
                    "open": 40000.0,
                    "high": 40100.0,
                    "low": 39900.0,
                    "close": 40050.0,
                    "volume": 100.0,
                    "quote_volume": 4_000_000.0,
                    "trade_count": 1000,
                    "taker_buy_base_volume": 50.0,
                    "taker_buy_quote_volume": 2_000_000.0,
                }
                for i in range(24)
            ]
            _make_parquet(
                data_dir / "raw" / "binance" / "um" / "klines" / "BTCUSDT" / "1h" / "2024",
                "01.parquet",
                raw_rows,
            )

            df = gateway.read_klines("BTCUSDT", "1h", start, end)
            assert len(df) == 24

    def test_read_funding_rate(self):
        """Successfully reads funding rate parquet files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = pathlib.Path(tmpdir)
            gateway = DataGateway(data_dir=str(data_dir))

            start = datetime(2024, 1, 1, tzinfo=timezone.utc)
            end = datetime(2024, 1, 8, tzinfo=timezone.utc)
            start_ms = int(start.timestamp() * 1000)

            # Funding rate every 8 hours
            fr_rows = [
                {
                    "timestamp": start_ms + i * 8 * 3600_000,
                    "funding_rate": 0.0001 * (i % 3 - 1),
                    "mark_price": 40000.0 + i * 100,
                }
                for i in range(21)  # 7 days * 3 per day
            ]
            _make_parquet(
                data_dir / "raw" / "binance" / "um" / "fundingRate" / "BTCUSDT" / "2024",
                "01.parquet",
                fr_rows,
            )

            df = gateway.read_funding_rate("BTCUSDT", start, end)

            assert isinstance(df, pd.DataFrame)
            assert list(df.columns) == ["timestamp", "funding_rate", "mark_price"]
            assert len(df) == 21
            assert df["timestamp"].is_monotonic_increasing


class TestMonthlyParquetPath:
    """_monthly_parquet_path builds correct file-level paths."""

    def test_bronze_klines(self):
        """Bronze klines path includes symbol, interval, year, month."""
        with tempfile.TemporaryDirectory() as tmpdir:
            gateway = DataGateway(data_dir=tmpdir)
            p = gateway._monthly_parquet_path(
                "BTCUSDT", "1h", 2024, 3, "klines", "bronze"
            )
            expected = (
                pathlib.Path(tmpdir)
                / "bronze" / "binance" / "um" / "klines"
                / "BTCUSDT" / "1h" / "2024" / "03.parquet"
            )
            assert p == expected

    def test_raw_funding_rate(self):
        """Raw funding rate path (no interval)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            gateway = DataGateway(data_dir=tmpdir)
            p = gateway._monthly_parquet_path(
                "ETHUSDT", "", 2025, 12, "funding_rate", "raw"
            )
            expected = (
                pathlib.Path(tmpdir)
                / "raw" / "binance" / "um" / "fundingRate"
                / "ETHUSDT" / "2025" / "12.parquet"
            )
            assert p == expected

    def test_unknown_data_type_raises(self):
        """Unknown data_type raises ValueError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            gateway = DataGateway(data_dir=tmpdir)
            with pytest.raises(ValueError, match="Unknown data_type"):
                gateway._monthly_parquet_path(
                    "BTCUSDT", "1h", 2024, 1, "invalid_type", "bronze"
                )
