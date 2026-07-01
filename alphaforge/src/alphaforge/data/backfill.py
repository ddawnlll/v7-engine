"""AlphaForge Data Backfill Pipeline.

Orchestrates market data backfill from Binance through the shared lib-level
BackfillOrchestrator and produces a deterministic DataManifest for
reproducibility.

The pipeline:
  1. Validates backfill configuration (symbols, intervals, time range).
  2. Delegates actual fetching to lib.level backfill.
  3. Produces an AlphaForge DataManifest anchored to the backfill run.
  4. Validates integrity (checksums, completeness) via the storage writer.

Usage:
    pipeline = BackfillPipeline(
        klines_service=klines_service,
        funding_service=funding_service,
        storage_writer=storage_writer,
        catalog=catalog,
        rate_limiter=rate_limiter,
        checkpoint=checkpoint,
    )
    result = pipeline.run(
        symbols=["BTCUSDT", "ETHUSDT"],
        intervals=["1h", "4h"],
        start_time=1700000000000,
        end_time=1700086400000,
        mode="SWING",
    )
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from alphaforge.data.manifest import DataManifest, build_manifest
from alphaforge.errors import AlphaForgeError
from lib.market_data.binance.backfill import BackfillOrchestrator

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Domain error
# ---------------------------------------------------------------------------


class BackfillError(AlphaForgeError):
    """A backfill pipeline step failed."""

    def __init__(self, step: str, detail: str) -> None:
        self.step = step
        self.detail = detail
        super().__init__(f"Backfill [{step}]: {detail}")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


VALID_BACKFILL_MODES = frozenset({"SCALP", "AGGRESSIVE_SCALP", "SWING"})
VALID_BACKFILL_INTERVALS = frozenset({"15m", "1h", "4h", "1d"})

# ---------------------------------------------------------------------------
# Binance Vision (data.binance.vision) — public S3 mirror
# ---------------------------------------------------------------------------

SYMBOLS_20: List[str] = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT",
    "SOLUSDT", "DOTUSDT", "MATICUSDT", "AVAXUSDT", "UNIUSDT",
    "LINKUSDT", "ATOMUSDT", "LTCUSDT", "BCHUSDT", "DOGEUSDT",
    "FILUSDT", "APTUSDT", "ARBUSDT", "OPUSDT", "SUIUSDT",
]

VALID_VISION_INTERVALS: frozenset[str] = frozenset({"1m", "5m", "15m", "1h"})

BINANCE_VISION_BASE: str = (
    "https://data.binance.vision/data/futures/um/monthly/klines"
)


@dataclass(frozen=True)
class BackfillConfig:
    """Immutable configuration for a single AlphaForge backfill run.

    All fields are frozen so two identical configs produce identical results.
    """

    symbols: tuple[str, ...]
    intervals: tuple[str, ...]
    start_time: int  # Unix ms
    end_time: int  # Unix ms
    mode: str  # SCALP | AGGRESSIVE_SCALP | SWING
    primary_interval: str  # mode's primary timeframe
    batch_size: int = 50000
    created_at: str = field(default="")  # overridden in create_backfill_config

    def __post_init__(self) -> None:
        if not self.symbols:
            raise BackfillError("config", "symbols must be non-empty")
        if not self.intervals:
            raise BackfillError("config", "intervals must be non-empty")
        if self.start_time >= self.end_time:
            raise BackfillError(
                "config",
                f"start_time ({self.start_time}) must be < end_time ({self.end_time})",
            )
        if self.mode not in VALID_BACKFILL_MODES:
            raise BackfillError(
                "config",
                f"mode must be one of {sorted(VALID_BACKFILL_MODES)}, got {self.mode!r}",
            )
        if self.primary_interval not in VALID_BACKFILL_INTERVALS:
            raise BackfillError(
                "config",
                f"primary_interval must be one of {sorted(VALID_BACKFILL_INTERVALS)}, "
                f"got {self.primary_interval!r}",
            )
        if self.batch_size < 1 or self.batch_size > 100_000:
            raise BackfillError(
                "config",
                f"batch_size must be 1–100000, got {self.batch_size}",
            )


def create_backfill_config(
    symbols: List[str],
    intervals: List[str],
    start_time: int,
    end_time: int,
    mode: str,
    primary_interval: str,
    batch_size: int = 50000,
) -> BackfillConfig:
    """Factory for BackfillConfig with frozen-tuple conversion and timestamp.

    Args:
        symbols: Trading pair symbols (e.g. ["BTCUSDT"]).
        intervals: Kline intervals (e.g. ["1h", "4h"]).
        start_time: Start timestamp in milliseconds.
        end_time: End timestamp in milliseconds.
        mode: Trading mode (SCALP, AGGRESSIVE_SCALP, SWING).
        primary_interval: The mode's primary timeframe.
        batch_size: Number of klines per batch.

    Returns:
        A validated, frozen BackfillConfig.
    """
    return BackfillConfig(
        symbols=tuple(s.upper() for s in symbols),
        intervals=tuple(intervals),
        start_time=start_time,
        end_time=end_time,
        mode=mode.upper(),
        primary_interval=primary_interval,
        batch_size=batch_size,
        created_at=datetime.now(timezone.utc).isoformat(),
    )


# ---------------------------------------------------------------------------
# Binance Vision config
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BinanceVisionConfig:
    """Immutable configuration for downloading from data.binance.vision.

    All fields are frozen — two identical configs produce identical downloads.
    The public S3 mirror (data.binance.vision) requires no API key.
    """

    symbols: tuple[str, ...]
    intervals: tuple[str, ...]
    output_dir: str
    start_year: int
    start_month: int
    end_year: int
    end_month: int

    def __post_init__(self) -> None:
        if not self.symbols:
            raise BackfillError("vision_config", "symbols must be non-empty")
        for sym in self.symbols:
            if not re.fullmatch(r"[A-Z0-9]+", sym.upper()):
                raise BackfillError(
                    "vision_config",
                    f"invalid symbol {sym!r} — only uppercase alphanumeric allowed",
                )
        if not self.intervals:
            raise BackfillError("vision_config", "intervals must be non-empty")
        for interval in self.intervals:
            if interval not in VALID_VISION_INTERVALS:
                raise BackfillError(
                    "vision_config",
                    f"interval must be one of {sorted(VALID_VISION_INTERVALS)}, "
                    f"got {interval!r}",
                )
        if self.start_year < 2022:
            raise BackfillError(
                "vision_config",
                f"start_year must be >= 2022, got {self.start_year}",
            )
        start_valid = self.start_year > 0 and 1 <= self.start_month <= 12
        end_valid = self.end_year > 0 and 1 <= self.end_month <= 12
        if not start_valid:
            raise BackfillError(
                "vision_config",
                f"invalid start ({self.start_year}-{self.start_month:02d})",
            )
        if not end_valid:
            raise BackfillError(
                "vision_config",
                f"invalid end ({self.end_year}-{self.end_month:02d})",
            )
        if self.start_year > self.end_year or (
            self.start_year == self.end_year and self.start_month > self.end_month
        ):
            raise BackfillError(
                "vision_config",
                f"start ({self.start_year}-{self.start_month:02d}) must be <= "
                f"end ({self.end_year}-{self.end_month:02d})",
            )


def create_binance_vision_config(
    symbols: List[str],
    intervals: List[str],
    output_dir: str | Path,
    start_year: int = 2022,
    start_month: int = 1,
    end_year: int | None = None,
    end_month: int | None = None,
) -> BinanceVisionConfig:
    """Factory for BinanceVisionConfig with frozen-tuple conversion.

    Args:
        symbols: Trading pair symbols (e.g. ``["BTCUSDT"]``).
        intervals: Kline intervals — one or more of ``1m``, ``5m``, ``15m``, ``1h``.
        output_dir: Root directory for partitioned Parquet output.
        start_year: First year to download (default 2022).
        start_month: First month to download (default January).
        end_year: Last year to download (default current year).
        end_month: Last month to download (default current month).

    Returns:
        A validated, frozen :class:`BinanceVisionConfig`.
    """
    _today = datetime.now(timezone.utc)
    return BinanceVisionConfig(
        symbols=tuple(s.upper() for s in symbols),
        intervals=tuple(intervals),
        output_dir=str(output_dir),
        start_year=start_year,
        start_month=start_month,
        end_year=end_year if end_year is not None else _today.year,
        end_month=end_month if end_month is not None else _today.month,
    )


# ---------------------------------------------------------------------------
# Pipeline result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BackfillResult:
    """Structured result from a backfill pipeline run."""

    config: BackfillConfig
    stats: Dict[str, Any]
    manifest: Optional[DataManifest]  # None if dry-run or no data
    integrity_passed: bool
    integrity_details: Dict[str, Any]
    errors: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


class BackfillPipeline:
    """AlphaForge backfill pipeline — wraps lib-level orchestrator.

    Provides AlphaForge-specific validation, DataManifest generation, and
    integrity checks on top of the shared lib-level backfill.
    """

    def __init__(
        self,
        klines_service: Any,
        funding_service: Any,
        storage_writer: Any,
        catalog: Any,
        rate_limiter: Any,
        checkpoint: Any,
    ) -> None:
        self._orchestrator = BackfillOrchestrator(
            klines_service=klines_service,
            funding_service=funding_service,
            storage_writer=storage_writer,
            catalog=catalog,
            rate_limiter=rate_limiter,
            checkpoint=checkpoint,
        )
        self._storage_writer = storage_writer

    def run(self, config: BackfillConfig) -> BackfillResult:
        """Execute a full backfill pipeline run.

        Args:
            config: Validated BackfillConfig.

        Returns:
            BackfillResult with stats, manifest, and integrity status.
        """
        logger.info(
            "Starting AlphaForge backfill: mode=%s symbols=%s intervals=%s",
            config.mode, list(config.symbols), list(config.intervals),
        )

        # Step 1: Run lib-level backfill
        try:
            stats = self._orchestrator.backfill(
                symbols=list(config.symbols),
                intervals=list(config.intervals),
                start_time=config.start_time,
                end_time=config.end_time,
                batch_size=config.batch_size,
            )
        except Exception as exc:
            raise BackfillError("fetch", str(exc)) from exc

        # Step 2: Build DataManifest from backfill outputs
        manifest = None
        try:
            manifest = self._build_manifest_from_config(config, stats)
        except Exception as exc:
            logger.warning("Failed to build manifest: %s", exc)

        # Step 3: Validate integrity
        integrity_passed, integrity_details = self._validate_integrity(config, stats)

        return BackfillResult(
            config=config,
            stats=stats,
            manifest=manifest,
            integrity_passed=integrity_passed,
            integrity_details=integrity_details,
            errors=stats.get("errors", []),
        )

    def run_dry(self, config: BackfillConfig) -> BackfillResult:
        """Dry-run: validate config only, no data fetched.

        Useful for pipeline pre-flight checks.
        """
        logger.info("Dry-run backfill: mode=%s symbols=%s", config.mode, list(config.symbols))

        return BackfillResult(
            config=config,
            stats={"total_symbols": len(config.symbols),
                   "total_intervals": len(config.intervals),
                   "total_records": 0,
                   "errors": []},
            manifest=None,
            integrity_passed=True,
            integrity_details={"dry_run": True},
        )

    def download_vision(self, vision_config: BinanceVisionConfig) -> Dict[str, Any]:
        """Optional step: download monthly klines from data.binance.vision.

        This is a pre-backfill download step that pulls data from the public
        Binance Vision S3 mirror (no API key required).  The downloaded files
        are written as partitioned Parquet+Zstd and can be used as input to
        the normal API-driven backfill or as a standalone data source.

        Args:
            vision_config: :class:`BinanceVisionConfig` specifying what to
                download and where to write it.

        Returns:
            Dict with download statistics (total_files, total_records, errors,
            skipped).
        """
        logger.info(
            "Binance Vision download: symbols=%s intervals=%s",
            list(vision_config.symbols), list(vision_config.intervals),
        )
        return download_from_binance_vision(vision_config)

    # -------------------------------------------------------------------
    # Manifest generation
    # -------------------------------------------------------------------

    def _build_manifest_from_config(
        self, config: BackfillConfig, stats: Dict[str, Any]
    ) -> Optional[DataManifest]:
        """Build a DataManifest from the backfill run metadata.

        Returns None if no records were written (manifest needs fixtures).
        """
        if stats.get("total_records", 0) == 0:
            return None

        # We construct a minimal manifest from config metadata.
        # Real fixture-based manifests require actual file paths;
        # this is a lightweight config-based manifest for backfill runs.
        from pathlib import Path as _Path

        # Create a temporary fixture JSON for the manifest builder.
        # This is NOT a real fixture — it is a config-derived anchor.
        import json as _json
        import tempfile as _tempfile

        fixture_data = {
            "mode": config.mode,
            "symbol": list(config.symbols)[0],
            "primary_interval": config.primary_interval,
            "total_records": stats.get("total_records", 0),
            "backfill_config": {
                "symbols": list(config.symbols),
                "intervals": list(config.intervals),
                "start_time": config.start_time,
                "end_time": config.end_time,
                "batch_size": config.batch_size,
            },
        }

        with _tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, prefix="backfill_manifest_"
        ) as tf:
            _json.dump(fixture_data, tf)
            tmp_path = tf.name

        try:
            return build_manifest([_Path(tmp_path)])
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    # -------------------------------------------------------------------
    # Integrity validation
    # -------------------------------------------------------------------

    def _validate_integrity(
        self, config: BackfillConfig, stats: Dict[str, Any]
    ) -> tuple[bool, Dict[str, Any]]:
        """Validate data integrity after backfill.

        Returns:
            (passed, details) tuple.
        """
        details: Dict[str, Any] = {
            "total_records": stats.get("total_records", 0),
            "symbols_count": stats.get("total_symbols", 0),
            "intervals_count": stats.get("total_intervals", 0),
            "errors": stats.get("errors", []),
            "checks": {},
        }

        # If there were errors, integrity is not fully confirmed
        has_errors = len(stats.get("errors", [])) > 0

        # Verify checksum files exist for each symbol
        checksum_check = True
        try:
            base_dir = getattr(self._storage_writer, "_base_dir", None)
            if base_dir:
                raw_dir = Path(base_dir) / "raw"
                if raw_dir.exists():
                    for symbol_dir in raw_dir.iterdir():
                        if symbol_dir.is_dir():
                            sha_files = list(symbol_dir.glob("*.sha256"))
                            parquet_files = list(symbol_dir.glob("*.parquet"))
                            for pf in parquet_files:
                                sf = Path(str(pf) + ".sha256")
                                if not sf.exists():
                                    checksum_check = False
                                    details["checks"][str(pf)] = "missing_sidecar"
                                else:
                                    details["checks"][str(pf)] = "ok"
        except Exception as exc:
            logger.warning("Checksum verification failed: %s", exc)
            checksum_check = False

        passed = (not has_errors) and checksum_check and stats.get("total_records", 0) > 0
        return passed, details


# ---------------------------------------------------------------------------
# Factory helper
# ---------------------------------------------------------------------------


def create_pipeline(
    klines_service: Any,
    funding_service: Any,
    storage_writer: Any,
    catalog: Any,
    rate_limiter: Any = None,
    checkpoint: Any = None,
) -> BackfillPipeline:
    """Convenience factory for BackfillPipeline with default rate limiter and checkpoint."""

    if rate_limiter is None:
        from lib.market_data.binance.rate_limiter import BinanceRateLimiter
        rate_limiter = BinanceRateLimiter()

    if checkpoint is None:
        import tempfile
        from lib.market_data.binance.checkpoint import BackfillCheckpoint
        _cp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        checkpoint = BackfillCheckpoint(file_path=_cp.name)

    return BackfillPipeline(
        klines_service=klines_service,
        funding_service=funding_service,
        storage_writer=storage_writer,
        catalog=catalog,
        rate_limiter=rate_limiter,
        checkpoint=checkpoint,
    )


# ---------------------------------------------------------------------------
# Binance Vision download — public S3 mirror (no API key required)
# ---------------------------------------------------------------------------


def _file_sha256(path: str) -> str:
    """Compute SHA-256 hex digest of a file."""
    sha = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha.update(chunk)
    return sha.hexdigest()


def _fetch_url(url: str, timeout: int = 120) -> bytes | None:
    """Fetch a URL and return bytes, or None on 404.

    Uses stdlib ``urllib.request`` — no external HTTP dependency needed
    for public S3 mirror access.
    """
    import urllib.request
    from urllib.error import HTTPError

    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.read()
    except HTTPError as exc:
        if exc.code == 404:
            return None
        raise


def _fetch_checksum(checksum_url: str) -> str | None:
    """Fetch a Binance .CHECKSUM file and extract the SHA-256 hash.

    The CHECKSUM file format is::

        <sha256_hex>  <filename>
    """
    data = _fetch_url(checksum_url)
    if data is None:
        return None
    return data.decode("utf-8").strip().split()[0]


def _parse_klines_csv(csv_text: str, interval: str) -> "Any":
    """Parse Binance kline CSV text into a pyarrow Table with typed columns.

    Args:
        csv_text: Raw CSV text (header row included).
        interval: Kline interval string stored as a column.

    Returns:
        A ``pyarrow.Table`` with int64 timestamps and float64 price/volume columns.
    """
    import csv
    import io

    import pyarrow as pa

    reader = csv.reader(io.StringIO(csv_text))

    open_times: list[int] = []
    opens: list[float] = []
    highs: list[float] = []
    lows: list[float] = []
    closes: list[float] = []
    volumes: list[float] = []
    close_times: list[int] = []
    quote_volumes: list[float] = []
    trades: list[int] = []
    taker_buy_volumes: list[float] = []
    taker_buy_quote_volumes: list[float] = []

    for i, row in enumerate(reader):
        # Skip header row (first row has text headers)
        if i == 0 and not row[0].isdigit():
            continue
        if len(row) < 11:
            continue
        open_times.append(int(row[0]))
        opens.append(float(row[1]))
        highs.append(float(row[2]))
        lows.append(float(row[3]))
        closes.append(float(row[4]))
        volumes.append(float(row[5]))
        close_times.append(int(row[6]))
        quote_volumes.append(float(row[7]))
        trades.append(int(row[8]))
        taker_buy_volumes.append(float(row[9]))
        taker_buy_quote_volumes.append(float(row[10]))

    n = len(open_times)
    return pa.table(
        {
            "open_time": pa.array(open_times, type=pa.int64()),
            "open": pa.array(opens, type=pa.float64()),
            "high": pa.array(highs, type=pa.float64()),
            "low": pa.array(lows, type=pa.float64()),
            "close": pa.array(closes, type=pa.float64()),
            "volume": pa.array(volumes, type=pa.float64()),
            "close_time": pa.array(close_times, type=pa.int64()),
            "quote_volume": pa.array(quote_volumes, type=pa.float64()),
            "trades": pa.array(trades, type=pa.int64()),
            "taker_buy_volume": pa.array(taker_buy_volumes, type=pa.float64()),
            "taker_buy_quote_volume": pa.array(taker_buy_quote_volumes, type=pa.float64()),
            "interval": pa.array([interval] * n, type=pa.string()),
        }
    )


def download_from_binance_vision(
    config: BinanceVisionConfig,
) -> Dict[str, Any]:
    """Download monthly klines from data.binance.vision and convert to Parquet+Zstd.

    Downloads ZIP files from the public Binance Vision S3 mirror, verifies
    SHA-256 checksums against ``.CHECKSUM`` sidecar files, extracts CSVs,
    and writes partitioned Parquet+Zstd files.

    Output layout::

        {output_dir}/{symbol}/{interval}/{year}/{month:02d}.parquet

    Files that already exist are skipped (safe for resume).

    Args:
        config: :class:`BinanceVisionConfig` specifying symbols, intervals,
            date range, and output directory.

    Returns:
        Dict with keys ``total_symbols``, ``total_intervals``, ``total_files``,
        ``total_records``, ``errors`` (list of error messages), and ``skipped``
        (list of paths already on disk).

    Raises:
        BackfillError: On invalid configuration or unrecoverable download failure.
    """
    import shutil
    import tempfile
    import urllib.request
    import zipfile
    from urllib.error import HTTPError

    import pyarrow.parquet as pq

    stats: Dict[str, Any] = {
        "total_symbols": len(config.symbols),
        "total_intervals": len(config.intervals),
        "total_files": 0,
        "total_records": 0,
        "errors": [],
        "skipped": [],
    }

    output_root = Path(config.output_dir)

    for symbol in config.symbols:
        for interval in config.intervals:
            url_base = f"{BINANCE_VISION_BASE}/{symbol}/{interval}/"

            for year in range(config.start_year, config.end_year + 1):
                start_m = config.start_month if year == config.start_year else 1
                end_m = config.end_month if year == config.end_year else 12

                for month in range(start_m, end_m + 1):
                    out_path = (
                        output_root
                        / symbol
                        / interval
                        / str(year)
                        / f"{month:02d}.parquet"
                    )

                    # Skip if already on disk (supports resume)
                    if out_path.exists():
                        stats["skipped"].append(str(out_path))
                        continue

                    filename = f"{symbol}-{interval}-{year}-{month:02d}.zip"
                    zip_url = url_base + filename
                    checksum_url = zip_url + ".CHECKSUM"

                    # Download ZIP to a temporary file
                    try:
                        with urllib.request.urlopen(zip_url, timeout=300) as resp:
                            with tempfile.NamedTemporaryFile(
                                delete=False, suffix=".zip"
                            ) as tmp:
                                shutil.copyfileobj(resp, tmp)
                                zip_tmp = tmp.name
                    except HTTPError as exc:
                        msg = (
                            f"{symbol}/{interval}/{year}-{month:02d}: "
                            f"HTTP {exc.code} downloading {filename}"
                        )
                        logger.warning(msg)
                        stats["errors"].append(msg)
                        continue
                    except Exception as exc:
                        msg = (
                            f"{symbol}/{interval}/{year}-{month:02d}: "
                            f"network error: {exc}"
                        )
                        logger.warning(msg)
                        stats["errors"].append(msg)
                        continue

                    # Verify checksum
                    try:
                        expected = _fetch_checksum(checksum_url)
                        if expected is not None:
                            actual = _file_sha256(zip_tmp)
                            if actual != expected:
                                msg = (
                                    f"{symbol}/{interval}/{year}-{month:02d}: "
                                    f"SHA-256 mismatch — expected {expected}, got {actual}"
                                )
                                logger.warning(msg)
                                stats["errors"].append(msg)
                                os.unlink(zip_tmp)
                                continue
                    except Exception as exc:
                        logger.warning(
                            "Checksum fetch failed for %s: %s", checksum_url, exc
                        )
                        # Proceed without checksum verification if fetch fails

                    # Extract CSV from ZIP and convert to Parquet
                    try:
                        csv_name = f"{symbol}-{interval}-{year}-{month:02d}.csv"
                        with zipfile.ZipFile(zip_tmp, "r") as zf:
                            with zf.open(csv_name) as csv_file:
                                csv_text = csv_file.read().decode("utf-8")

                        table = _parse_klines_csv(csv_text, interval)

                        out_path.parent.mkdir(parents=True, exist_ok=True)
                        pq.write_table(table, str(out_path), compression="zstd")

                        stats["total_files"] += 1
                        stats["total_records"] += len(table)
                    except KeyError:
                        # CSV not found in ZIP — try alternate names
                        msg = (
                            f"{symbol}/{interval}/{year}-{month:02d}: "
                            f"CSV {csv_name} not found in ZIP"
                        )
                        logger.warning(msg)
                        stats["errors"].append(msg)
                    except Exception as exc:
                        msg = (
                            f"{symbol}/{interval}/{year}-{month:02d}: "
                            f"extract/convert error: {exc}"
                        )
                        logger.warning(msg)
                        stats["errors"].append(msg)
                    finally:
                        # Clean up temp ZIP
                        try:
                            os.unlink(zip_tmp)
                        except OSError:
                            pass

    logger.info(
        "Binance Vision download complete: %d files, %d records, %d errors, %d skipped",
        stats["total_files"],
        stats["total_records"],
        len(stats["errors"]),
        len(stats["skipped"]),
    )
    return stats
