"""
Tests for lib/data_lake/downloader.py — BinanceUmDownloader.

Uses mocked HTTP to avoid real network calls.
"""

from __future__ import annotations

import io
import os
import tempfile
import time
import zipfile
from pathlib import Path
from unittest.mock import Mock, patch

import pyarrow.parquet as pq

from lib.data_lake.downloader import (
    BinanceUmDownloader,
    DownloadResult,
    _month_bounds,
)
from lib.data_lake.storage import DataLakePaths


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_fake_zip(csv_content: str = "") -> bytes:
    """Create an in-memory ZIP containing ``klines.csv``."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("klines.csv", csv_content or _SAMPLE_CSV)
    return buf.getvalue()


_SAMPLE_CSV = (
    "1704067200000,43200.0,43300.0,43100.0,43250.0,100.0,1704153599999,"
    "4325000.0,1000,50.0,2162500.0,0\n"
    "1704153600000,43250.0,43400.0,43200.0,43350.0,150.0,1704239999999,"
    "6502500.0,1500,75.0,3251250.0,0\n"
)


def _mock_session(zip_bytes: bytes | None = None, status: int = 200):
    """Build a mock ``requests.Session`` that returns *zip_bytes*."""
    session = Mock()
    resp = Mock()
    resp.status_code = status
    resp.content = zip_bytes or _make_fake_zip()
    resp.ok = status < 400
    if status >= 400 and status != 404:
        resp.raise_for_status.side_effect = IOError(f"HTTP {status}")
    session.get.return_value = resp
    return session


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------


class TestInitialization:
    """Construction with default and custom parameters."""

    def test_default_params(self) -> None:
        """Default params produce expected values."""
        d = BinanceUmDownloader()
        assert d.max_workers == 4
        assert d.rate_per_minute == 1200
        assert d.data_dir == Path("data_lake")
        assert d._tokens == 1200.0

    def test_custom_params(self) -> None:
        """Custom params are reflected in instance attributes."""
        d = BinanceUmDownloader(
            data_dir="/custom/path", max_workers=8, rate_per_minute=600
        )
        assert d.max_workers == 8
        assert d.rate_per_minute == 600
        assert d.data_dir == Path("/custom/path")
        assert d._tokens == 600.0

    def test_session_created(self) -> None:
        """A requests.Session is created."""
        d = BinanceUmDownloader()
        assert hasattr(d, "session")
        assert d.session is not None


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------


class TestRateLimit:
    """Token-bucket rate limiter behaviour."""

    def test_burst_does_not_block(self) -> None:
        """Burst of calls within the rate limit is near-instant."""
        d = BinanceUmDownloader(rate_per_minute=1200)
        start = time.monotonic()
        for _ in range(100):
            d._rate_limit()
        elapsed = time.monotonic() - start
        assert elapsed < 2.0, (
            f"100 calls at 1200/min should be fast, took {elapsed:.3f}s"
        )

    def test_enforces_upper_bound(self) -> None:
        """Calls beyond the burst limit are throttled."""
        d = BinanceUmDownloader(rate_per_minute=60)  # 1 token/sec
        # Exhaust the burst tokens
        for _ in range(60):
            d._rate_limit()
        # The 61st call should block (~1 second)
        start = time.monotonic()
        d._rate_limit()
        elapsed = time.monotonic() - start
        assert elapsed >= 0.5, (
            f"Should have blocked for ~1s, got {elapsed:.3f}s"
        )

    def test_initial_tokens_full(self) -> None:
        """Start with a full bucket."""
        d = BinanceUmDownloader(rate_per_minute=500)
        assert d._tokens == 500.0

    def test_consumes_token(self) -> None:
        """Each call consumes one token."""
        d = BinanceUmDownloader(rate_per_minute=100)
        before = d._tokens
        d._rate_limit()
        assert d._tokens == before - 1.0


# ---------------------------------------------------------------------------
# DownloadResult frozen dataclass
# ---------------------------------------------------------------------------


class TestDownloadResult:
    """DownloadResult — immutable result container."""

    def test_counts(self) -> None:
        """Correctly tracks total / succeeded / failed."""
        r = DownloadResult(
            manifest_id="m1",
            total=10,
            succeeded=7,
            failed=3,
            failed_entries=[{"symbol": "X", "error": "e"}],
            paths_created=[Path("/tmp/a.parquet")],
        )
        assert r.total == 10
        assert r.succeeded == 7
        assert r.failed == 3
        assert len(r.failed_entries) == 1
        assert len(r.paths_created) == 1

    def test_empty_lists(self) -> None:
        """Empty failed_entries and paths_created are fine."""
        r = DownloadResult(
            manifest_id="m2",
            total=0,
            succeeded=0,
            failed=0,
            failed_entries=[],
            paths_created=[],
        )
        assert r.failed_entries == []
        assert r.paths_created == []

    def test_frozen(self) -> None:
        """DownloadResult cannot be mutated."""
        r = DownloadResult(
            manifest_id="m3",
            total=5,
            succeeded=5,
            failed=0,
            failed_entries=[],
            paths_created=[Path("x.parquet")],
        )
        import pytest

        with pytest.raises(AttributeError):
            r.total = 99  # type: ignore[misc]


# ---------------------------------------------------------------------------
# _month_bounds
# ---------------------------------------------------------------------------


class TestMonthBounds:
    """Helper that computes month time range in milliseconds."""

    def test_january(self) -> None:
        start_ms, end_ms = _month_bounds(2024, 1)
        # 2024-01-01 00:00:00 UTC
        assert start_ms == 1704067200000
        # 2024-02-01 00:00:00 UTC
        assert end_ms == 1706745600000

    def test_december(self) -> None:
        start_ms, end_ms = _month_bounds(2024, 12)
        # 2024-12-01 00:00:00 UTC
        assert start_ms == 1733011200000
        # 2025-01-01 00:00:00 UTC
        assert end_ms == 1735689600000

    def test_range_duration(self) -> None:
        """The range spans the full month."""
        start_ms, end_ms = _month_bounds(2024, 2)  # February (leap year)
        days = 29
        assert (end_ms - start_ms) == days * 86_400_000


# ---------------------------------------------------------------------------
# CSV → Parquet conversion
# ---------------------------------------------------------------------------


class TestCsvToKlinesTable:
    """Static CSV-to-pyarrow conversion."""

    def test_parses_valid_csv(self) -> None:
        table = BinanceUmDownloader._csv_to_klines_table(_SAMPLE_CSV)
        assert table.num_rows == 2
        assert table.column_names == [
            "open_time",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "close_time",
            "quote_volume",
            "trade_count",
            "taker_buy_volume",
            "taker_buy_quote_volume",
            "ignore",
        ]
        # First row open_time
        assert table.column("open_time")[0].as_py() == 1704067200000

    def test_empty_lines_skipped(self) -> None:
        csv = "\n\n" + _SAMPLE_CSV + "\n\n"
        table = BinanceUmDownloader._csv_to_klines_table(csv)
        assert table.num_rows == 2

    def test_short_rows_skipped(self) -> None:
        csv = "1,2,3\n" + _SAMPLE_CSV
        table = BinanceUmDownloader._csv_to_klines_table(csv)
        assert table.num_rows == 2

    def test_empty_csv_returns_empty_table(self) -> None:
        table = BinanceUmDownloader._csv_to_klines_table("")
        assert table.num_rows == 0
        assert len(table.column_names) == 12

    def test_ignore_field_empty_string(self) -> None:
        """Empty 'ignore' column is parsed as 0.0."""
        row = "1704067200000,1,2,3,4,5,1704153599999,7,8,9,10,"
        table = BinanceUmDownloader._csv_to_klines_table(row)
        assert table.num_rows == 1
        assert table.column("ignore")[0].as_py() == 0.0


# ---------------------------------------------------------------------------
# _download_and_convert_zip
# ---------------------------------------------------------------------------


class TestDownloadAndConvertZip:
    """ZIP download → CSV extraction → Parquet conversion."""

    def test_successful_download_and_convert(self) -> None:
        """Happy path: ZIP downloaded, CSV extracted, Parquet written."""
        with tempfile.TemporaryDirectory() as tmp:
            d = BinanceUmDownloader(data_dir=tmp)
            d.session = _mock_session()

            target = Path(tmp) / "BTCUSDT-1h-2024-01.parquet"
            result = d._download_and_convert_zip(
                "https://example.com/data.zip", target
            )

            assert result is True
            assert target.exists()

            # Round-trip the Parquet
            table = pq.read_table(str(target))
            assert table.num_rows == 2
            assert table.column("open")[0].as_py() == 43200.0

    def test_404_returns_false(self) -> None:
        """A 404 response returns False without crashing."""
        with tempfile.TemporaryDirectory() as tmp:
            d = BinanceUmDownloader(data_dir=tmp)
            d.session = _mock_session(status=404)

            target = Path(tmp) / "missing.parquet"
            result = d._download_and_convert_zip(
                "https://example.com/missing.zip", target
            )
            assert result is False
            assert not target.exists()

    def test_server_error_returns_false(self) -> None:
        """A 500 response after retries returns False."""
        with tempfile.TemporaryDirectory() as tmp:
            d = BinanceUmDownloader(data_dir=tmp)
            d.session = _mock_session(status=500)

            target = Path(tmp) / "error.parquet"
            result = d._download_and_convert_zip(
                "https://example.com/error.zip", target
            )
            assert result is False
            assert not target.exists()

    def test_cleanup_temp_on_failure(self) -> None:
        """Temp file is removed when conversion fails mid-way."""
        with tempfile.TemporaryDirectory() as tmp:
            d = BinanceUmDownloader(data_dir=tmp)

            # Mock session returns valid content, but break the CSV parsing
            # by returning invalid data
            bad_zip = _make_fake_zip(csv_content="not,enough,cols\n")
            d.session = _mock_session(zip_bytes=bad_zip)

            target = Path(tmp) / "bad.parquet"
            result = d._download_and_convert_zip(
                "https://example.com/bad.zip", target
            )
            assert result is False
            # Temp file should be gone
            tmp_path = target.with_suffix(target.suffix + ".tmp")
            assert not tmp_path.exists()

    def test_target_already_exists_skipped(self) -> None:
        """_download_klines_single returns False when target exists."""
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "existing.parquet"
            target.touch()

            d = BinanceUmDownloader(data_dir=tmp)
            result = d._download_klines_single(
                "https://example.com/data.zip", target
            )
            assert result is False


# ---------------------------------------------------------------------------
# download_all
# ---------------------------------------------------------------------------


class TestDownloadAll:
    """Manifest dispatch via ``download_all``."""

    def test_empty_manifest(self) -> None:
        """An empty manifest produces zero-count result."""
        d = BinanceUmDownloader()
        result = d.download_all({"manifest_id": "empty", "entries": []})
        assert result.total == 0
        assert result.succeeded == 0
        assert result.failed == 0
        assert result.failed_entries == []
        assert result.paths_created == []

    def test_missing_required_fields(self) -> None:
        """Entries missing symbol / year / months are recorded as failures."""
        d = BinanceUmDownloader()
        manifest = {
            "manifest_id": "bad-entry",
            "entries": [
                {
                    "data_type": "klines",
                    "symbol": "",
                    "year": 2024,
                    "months": [],
                }
            ],
        }
        result = d.download_all(manifest)
        assert result.total == 1
        assert result.failed == 1
        assert len(result.failed_entries) == 1
        assert "Missing required fields" in result.failed_entries[0]["error"]

    def test_unknown_data_type(self) -> None:
        """Unknown data_type entries are recorded as failures."""
        d = BinanceUmDownloader()
        manifest = {
            "manifest_id": "bad-type",
            "entries": [
                {
                    "data_type": "unknown_data_type",
                    "symbol": "BTCUSDT",
                    "year": 2024,
                    "months": [1],
                }
            ],
        }
        result = d.download_all(manifest)
        assert result.total == 1
        assert result.failed == 1
        assert "Unknown data_type" in result.failed_entries[0]["error"]

    @patch.object(BinanceUmDownloader, "download_klines")
    def test_dispatches_klines(self, mock_dl) -> None:
        """download_all calls download_klines for klines entries."""
        mock_dl.return_value = [Path("/tmp/test.parquet")]
        d = BinanceUmDownloader()
        manifest = {
            "manifest_id": "k-test",
            "entries": [
                {
                    "data_type": "klines",
                    "symbol": "BTCUSDT",
                    "interval": "1h",
                    "year": 2024,
                    "months": [1, 2],
                }
            ],
        }
        result = d.download_all(manifest)
        mock_dl.assert_called_once_with("BTCUSDT", "1h", 2024, [1, 2])
        assert result.total == 1
        assert result.succeeded == 1
        assert len(result.paths_created) == 1

    @patch.object(BinanceUmDownloader, "download_funding_rate")
    def test_dispatches_funding_rate(self, mock_dl) -> None:
        """download_all calls download_funding_rate for funding_rate entries."""
        mock_dl.return_value = [Path("/tmp/funding.parquet")]
        d = BinanceUmDownloader()
        manifest = {
            "manifest_id": "fr-test",
            "entries": [
                {
                    "data_type": "funding_rate",
                    "symbol": "ETHUSDT",
                    "year": 2024,
                    "months": [3],
                }
            ],
        }
        result = d.download_all(manifest)
        mock_dl.assert_called_once_with("ETHUSDT", 2024, [3])
        assert result.total == 1
        assert result.succeeded == 1


# ---------------------------------------------------------------------------
# download_klines (integration-style with mocked session)
# ---------------------------------------------------------------------------


class TestDownloadKlines:
    """``download_klines`` with mocked HTTP."""

    def test_downloads_all_months(self) -> None:
        """All requested months are downloaded and paths returned."""
        with tempfile.TemporaryDirectory() as tmp:
            d = BinanceUmDownloader(data_dir=tmp)
            zip_data = _make_fake_zip()
            d.session = _mock_session(zip_bytes=zip_data)

            paths = d.download_klines("BTCUSDT", "1h", 2024, [1, 2])

            # Two Parquet files should exist
            assert len(paths) == 2
            for p in paths:
                assert p.exists()
                tbl = pq.read_table(str(p))
                assert tbl.num_rows == 2

    def test_callback_invoked(self) -> None:
        """The callback is called with each target path."""
        called: list[str] = []

        def cb(path: str) -> None:
            called.append(path)

        with tempfile.TemporaryDirectory() as tmp:
            d = BinanceUmDownloader(data_dir=tmp)
            d.session = _mock_session()

            d.download_klines("BTCUSDT", "1h", 2024, [1], callback=cb)

            assert len(called) == 1
            assert called[0].endswith(".parquet")

    def test_existing_files_skipped(self) -> None:
        """Already-downloaded months are skipped."""
        with tempfile.TemporaryDirectory() as tmp:
            # Set BASE_DIR to tmp first so the pre-created file lands
            # at the same place the downloader will look.
            original_base = DataLakePaths.BASE_DIR
            DataLakePaths.BASE_DIR = Path(tmp)

            try:
                p1 = DataLakePaths.klines_path("BTCUSDT", "1h", 2024, 1)
                p1.parent.mkdir(parents=True, exist_ok=True)
                p1.touch()

                d = BinanceUmDownloader(data_dir=str(tmp))
                zip_data = _make_fake_zip()
                d.session = _mock_session(zip_bytes=zip_data)

                paths = d.download_klines("BTCUSDT", "1h", 2024, [1, 2])

                # Only month 2 should be downloaded (month 1 existed already)
                assert len(paths) == 1
                assert paths[0].name == "02.parquet"
            finally:
                DataLakePaths.BASE_DIR = original_base


# ---------------------------------------------------------------------------
# download_funding_rate (mocked)
# ---------------------------------------------------------------------------


class TestDownloadFundingRate:
    """``download_funding_rate`` with mocked REST API."""

    def test_empty_response_returns_no_paths(self) -> None:
        """Zero funding records for a month returns no paths."""
        with tempfile.TemporaryDirectory() as tmp:
            d = BinanceUmDownloader(data_dir=tmp)
            d.session = _mock_session(zip_bytes=b"[]")

            paths = d.download_funding_rate("BTCUSDT", 2024, [1])
            assert paths == []

    def test_single_month_success(self) -> None:
        """One month of funding data is saved as Parquet."""
        funding_data = [
            {
                "symbol": "BTCUSDT",
                "fundingTime": 1704067200000,
                "fundingRate": "0.00010000",
                "markPrice": "43250.00",
            }
        ]
        import json

        session = Mock()
        resp = Mock()
        resp.status_code = 200
        resp.ok = True
        resp.json.return_value = funding_data
        session.get.return_value = resp

        with tempfile.TemporaryDirectory() as tmp:
            d = BinanceUmDownloader(data_dir=tmp)
            d.session = session

            paths = d.download_funding_rate("BTCUSDT", 2024, [1])

            assert len(paths) == 1
            table = pq.read_table(str(paths[0]))
            assert table.num_rows == 1
            assert (
                table.column("funding_rate")[0].as_py() == 0.0001
            )
            assert table.column("symbol")[0].as_py() == "BTCUSDT"
