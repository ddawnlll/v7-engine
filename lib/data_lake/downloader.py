"""
BinanceUmDownloader — multi-worker parallel downloader for Binance data.

Downloads klines (from Binance Vision ZIP archives) and funding rate data
(from REST API) with rate limiting, retry with backoff, and atomic writes.

Domain-boundary compliant: imports only stdlib, requests, pyarrow, and
``lib/data_lake/storage``.
"""

from __future__ import annotations

import calendar
import datetime
import io
import time
import threading
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import requests
import pyarrow as pa
import pyarrow.parquet as pq

from lib.data_lake.storage import DataLakePaths

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BINANCE_VISION_BASE = (
    "https://data.binance.vision/data/futures/um/monthly/klines"
)
BINANCE_REST_BASE = "https://fapi.binance.com"
FUNDING_RATE_LIMIT = 1000


# ---------------------------------------------------------------------------
# DownloadResult
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DownloadResult:
    """Immutable result of a ``download_all`` run.

    Attributes:
        manifest_id: Identifier of the manifest that was processed.
        total: Total number of download entries attempted.
        succeeded: Number of entries that downloaded successfully.
        failed: Number of entries that failed.
        failed_entries: List of dicts describing each failure.
        paths_created: List of file system paths that were created by this run.
    """

    manifest_id: str
    total: int
    succeeded: int
    failed: int
    failed_entries: list[dict]
    paths_created: list[Path]


# ---------------------------------------------------------------------------
# BinanceUmDownloader
# ---------------------------------------------------------------------------


class BinanceUmDownloader:
    """Multi-worker parallel downloader for Binance UM futures data.

    Uses a thread pool for parallel downloads and a token-bucket rate
    limiter to stay within *rate_per_minute* across all workers.

    Parameters
    ----------
    data_dir:
        Base directory for data lake storage (default ``"data_lake"``).
    max_workers:
        Maximum number of parallel download threads (default 4).
    rate_per_minute:
        Maximum API / download requests per minute (default 1200).
    """

    def __init__(
        self,
        data_dir: str = "data_lake",
        max_workers: int = 4,
        rate_per_minute: int = 1200,
    ) -> None:
        self.data_dir = Path(data_dir)
        self.max_workers = max_workers
        self.rate_per_minute = rate_per_minute
        self.session = requests.Session()

        # Wire data_dir into DataLakePaths so path helpers use our base
        DataLakePaths.BASE_DIR = self.data_dir

        # Token bucket state
        self._tokens = float(rate_per_minute)
        self._last_refill = time.monotonic()
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def download_klines(
        self,
        symbol: str,
        interval: str,
        year: int,
        months: list[int],
        callback: Callable[[str], None] | None = None,
    ) -> list[Path]:
        """Download monthly klines for *symbol* / *interval*.

        For each month in *months*:

        1. Download the monthly ZIP from Binance Vision.
        2. Extract the embedded CSV.
        3. Convert to Parquet (Zstd compressed).
        4. Write atomically (``.tmp`` suffix, then ``rename``).

        Parameters
        ----------
        symbol:
            Trading pair, e.g. ``"BTCUSDT"``.
        interval:
            Candle interval, e.g. ``"1h"``.
        year:
            Four-digit year.
        months:
            List of month numbers (1-12).
        callback:
            Optional callback invoked with the target path string after each
            successful download.

        Returns
        -------
        list[Path]
            Paths of created Parquet files.
        """
        created: list[Path] = []
        futures: dict = {}

        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            for month in months:
                target = DataLakePaths.klines_path(symbol, interval, year, month)
                url = (
                    f"{BINANCE_VISION_BASE}/{symbol}/{interval}/"
                    f"{symbol}-{interval}-{year}-{month:02d}.zip"
                )
                future = pool.submit(
                    self._download_klines_single, url, target
                )
                futures[future] = (target, month)

            for future in as_completed(futures):
                target, _month = futures[future]
                try:
                    if future.result():
                        created.append(target)
                        if callback:
                            callback(str(target))
                except Exception:
                    pass  # individual failures are surfaced inside the method

        return created

    def download_funding_rate(
        self,
        symbol: str,
        year: int,
        months: list[int],
    ) -> list[Path]:
        """Download monthly funding rate data via Binance REST API.

        Paginates through ``/fapi/v1/fundingRate`` (max 1000/call) to
        cover each entire month.

        Parameters
        ----------
        symbol:
            Trading pair, e.g. ``"BTCUSDT"``.
        year:
            Four-digit year.
        months:
            List of month numbers (1-12).

        Returns
        -------
        list[Path]
            Paths of created Parquet files.
        """
        created: list[Path] = []
        futures: dict = {}

        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            for month in months:
                target = DataLakePaths.funding_rate_path(symbol, year, month)
                future = pool.submit(
                    self._download_funding_single, symbol, target, year, month
                )
                futures[future] = (target, month)

            for future in as_completed(futures):
                target, _month = futures[future]
                try:
                    if future.result():
                        created.append(target)
                except Exception:
                    pass

        return created

    def download_all(self, manifest: dict) -> DownloadResult:
        """Dispatch downloads based on a manifest dict.

        The *manifest* should contain:

        =================== =============================================
        Key                  Description
        =================== =============================================
        ``manifest_id``      (str) Unique identifier for this batch.
        ``entries``          (list[dict]) One entry per download task.
        =================== =============================================

        Each entry supports:

        =================== =============================================
        ``data_type``        ``"klines"`` or ``"funding_rate"``
        ``symbol``           Trading pair (e.g. ``"BTCUSDT"``).
        ``interval``         Candle interval (klines only, default ``"1h"``).
        ``year``             Four-digit year.
        ``months``           List of month numbers (1-12).
        =================== =============================================

        Parameters
        ----------
        manifest:
            Download manifest dict.

        Returns
        -------
        DownloadResult
            Summary of the run.
        """
        manifest_id = manifest.get("manifest_id", "unknown")
        entries = manifest.get("entries", [])
        failed_entries: list[dict] = []
        all_paths: list[Path] = []

        for entry in entries:
            data_type = entry.get("data_type")
            symbol = entry.get("symbol", "")
            year = entry.get("year")
            months = entry.get("months", [])
            interval = entry.get("interval", "1h")

            if not symbol or not year or not months:
                failed_entries.append({
                    **entry,
                    "error": "Missing required fields: symbol, year, months",
                })
                continue

            try:
                if data_type == "klines":
                    paths = self.download_klines(symbol, interval, year, months)
                    all_paths.extend(paths)
                elif data_type == "funding_rate":
                    paths = self.download_funding_rate(symbol, year, months)
                    all_paths.extend(paths)
                else:
                    failed_entries.append({
                        **entry,
                        "error": f"Unknown data_type: {data_type}",
                    })
            except Exception as exc:
                failed_entries.append({
                    **entry,
                    "error": str(exc),
                })

            total = len(entries)
            succeeded = total - len(failed_entries)

        return DownloadResult(
            manifest_id=manifest_id,
            total=len(entries),
            succeeded=len(entries) - len(failed_entries),
            failed=len(failed_entries),
            failed_entries=failed_entries,
            paths_created=all_paths,
        )

    # ------------------------------------------------------------------
    # Rate limiting
    # ------------------------------------------------------------------

    def _rate_limit(self) -> None:
        """Block the calling thread if the rate limit has been exceeded.

        Uses a token-bucket algorithm refilled at *rate_per_minute* tokens
        per 60 seconds.  Sleeps **outside** the lock so that other worker
        threads can continue while the current thread waits.
        """
        sleep_time = 0.0
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_refill
            self._tokens = min(
                self.rate_per_minute,
                self._tokens + elapsed * (self.rate_per_minute / 60.0),
            )
            self._last_refill = now

            if self._tokens < 1:
                sleep_time = (1.0 - self._tokens) / (self.rate_per_minute / 60.0)
                self._tokens = 0.0
            else:
                self._tokens -= 1.0

        if sleep_time > 0:
            time.sleep(sleep_time)

    # ------------------------------------------------------------------
    # Internal: klines download + convert
    # ------------------------------------------------------------------

    def _download_klines_single(self, url: str, target: Path) -> bool:
        """Download a single monthly klines ZIP and convert to Parquet.

        Returns ``True`` on success, ``False`` if the file already exists
        or the download / conversion failed.
        """
        if target.exists():
            return False
        return self._download_and_convert_zip(url, target)

    def _download_and_convert_zip(self, url: str, target_path: Path) -> bool:
        """Download a ZIP from *url*, extract CSV, convert to Parquet.

        Writes atomically: content goes to ``target_path.suffix + ".tmp"``
        first, then is renamed to *target_path*.

        Returns ``True`` on success, ``False`` on failure.
        """
        target_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = target_path.with_suffix(target_path.suffix + ".tmp")

        try:
            # Download ZIP
            resp = self._request_with_retry(url, stream=True)
            if resp is None:
                return False

            # Parse ZIP in memory
            zip_bytes = io.BytesIO(resp.content)
            with zipfile.ZipFile(zip_bytes) as zf:
                csv_names = [n for n in zf.namelist() if n.endswith(".csv")]
                if not csv_names:
                    return False
                csv_data = zf.read(csv_names[0]).decode("utf-8")

            # Parse CSV → pyarrow Table
            table = self._csv_to_klines_table(csv_data)
            if table.num_rows == 0:
                return False

            # Write Parquet (Zstd) atomically
            pq.write_table(table, str(tmp_path), compression="zstd")
            tmp_path.rename(target_path)
            return True

        except Exception:
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
            return False

    @staticmethod
    def _csv_to_klines_table(csv_data: str) -> pa.Table:
        """Convert a klines CSV string into a pyarrow Table.

        The CSV is expected to have 12 comma-separated columns matching
        the Binance Vision klines format.
        """
        rows: list[dict] = []
        for line in csv_data.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split(",")
            if len(parts) < 12:
                continue
            rows.append({
                "open_time": int(parts[0]),
                "open": float(parts[1]),
                "high": float(parts[2]),
                "low": float(parts[3]),
                "close": float(parts[4]),
                "volume": float(parts[5]),
                "close_time": int(parts[6]),
                "quote_volume": float(parts[7]),
                "trade_count": int(parts[8]),
                "taker_buy_volume": float(parts[9]),
                "taker_buy_quote_volume": float(parts[10]),
                "ignore": float(parts[11]) if parts[11].strip() else 0.0,
            })

        if not rows:
            schema = pa.schema([
                pa.field("open_time", pa.int64()),
                pa.field("open", pa.float64()),
                pa.field("high", pa.float64()),
                pa.field("low", pa.float64()),
                pa.field("close", pa.float64()),
                pa.field("volume", pa.float64()),
                pa.field("close_time", pa.int64()),
                pa.field("quote_volume", pa.float64()),
                pa.field("trade_count", pa.int64()),
                pa.field("taker_buy_volume", pa.float64()),
                pa.field("taker_buy_quote_volume", pa.float64()),
                pa.field("ignore", pa.float64()),
            ])
            return pa.Table.from_arrays([pa.array([], type=t) for _, t in zip(schema.names, schema.types)], schema=schema)

        return pa.Table.from_pylist(rows)

    # ------------------------------------------------------------------
    # Internal: funding rate download
    # ------------------------------------------------------------------

    def _download_funding_single(
        self,
        symbol: str,
        target: Path,
        year: int,
        month: int,
    ) -> bool:
        """Download funding rate data for one month via REST API.

        Paginates through ``/fapi/v1/fundingRate`` (max 1000/call).
        Returns ``True`` on success, ``False`` if the file already exists
        or the download failed.
        """
        if target.exists():
            return False

        target.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = target.with_suffix(target.suffix + ".tmp")

        start_ms, end_ms = _month_bounds(year, month)

        try:
            all_records: list[dict] = []
            cursor = start_ms

            while cursor < end_ms:
                resp = self._request_with_retry(
                    f"{BINANCE_REST_BASE}/fapi/v1/fundingRate",
                    params={
                        "symbol": symbol,
                        "startTime": cursor,
                        "endTime": end_ms,
                        "limit": FUNDING_RATE_LIMIT,
                    },
                )
                if resp is None:
                    return False

                data = resp.json()
                if not data:
                    break

                for item in data:
                    all_records.append({
                        "symbol": str(item.get("symbol", "")),
                        "funding_rate": float(item.get("fundingRate", 0)),
                        "funding_time": int(item.get("fundingTime", 0)),
                        "mark_price": float(item.get("markPrice", 0)),
                    })

                last_time = data[-1].get("fundingTime", cursor)
                if last_time <= cursor:
                    break  # no progress — avoid infinite loop
                cursor = last_time + 1

            if not all_records:
                return False

            schema = pa.schema([
                pa.field("symbol", pa.string()),
                pa.field("funding_rate", pa.float64()),
                pa.field("funding_time", pa.int64()),
                pa.field("mark_price", pa.float64()),
            ])
            table = pa.Table.from_pylist(all_records, schema=schema)

            pq.write_table(table, str(tmp_path), compression="zstd")
            tmp_path.rename(target)
            return True

        except Exception:
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
            return False

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    def _request_with_retry(
        self,
        url: str,
        params: dict | None = None,
        stream: bool = False,
        max_retries: int = 3,
    ) -> requests.Response | None:
        """Make a GET request with rate limiting and exponential backoff.

        Parameters
        ----------
        url:
            Request URL.
        params:
            Optional query parameters.
        stream:
            Whether to stream the response body.
        max_retries:
            Maximum retry attempts (default 3).

        Returns
        -------
        requests.Response or None
            ``None`` is returned when all retries are exhausted, the server
            returns 404, or a non-recoverable error occurs.
        """
        for attempt in range(max_retries):
            self._rate_limit()
            try:
                resp = self.session.get(
                    url, params=params, stream=stream, timeout=60
                )
                if resp.status_code == 429:
                    time.sleep(2.0 ** (attempt + 1))
                    continue
                if resp.status_code == 404:
                    return None
                resp.raise_for_status()
                return resp
            except requests.RequestException:
                if attempt == max_retries - 1:
                    return None
                time.sleep(2.0**attempt)  # exponential backoff
        return None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _month_bounds(year: int, month: int) -> tuple[int, int]:
    """Return ``(start_ms, end_ms)`` for a given year/month in UTC.

    *start_ms* is the first millisecond of the month.
    *end_ms* is the first millisecond of the next month (exclusive).
    """
    start_dt = datetime.datetime(year, month, 1, tzinfo=datetime.timezone.utc)
    if month == 12:
        end_dt = datetime.datetime(
            year + 1, 1, 1, tzinfo=datetime.timezone.utc
        )
    else:
        end_dt = datetime.datetime(
            year, month + 1, 1, tzinfo=datetime.timezone.utc
        )

    start_ms = int(start_dt.timestamp() * 1000)
    end_ms = int(end_dt.timestamp() * 1000)
    return start_ms, end_ms
