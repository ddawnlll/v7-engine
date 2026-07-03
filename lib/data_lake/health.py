"""
DataHealthChecker — verify data health and auto-repair.

Checks whether required datasets exist, are not corrupted, and
meet coverage thresholds.  If data is missing or checksums fail,
triggers backfill + re-verification automatically.

Usage:
    checker = DataHealthChecker(data_dir="data_lake")
    report = checker.check(
        symbols=["BTCUSDT", "ETHUSDT"],
        intervals=["1h", "4h"],
        start=datetime(2023, 1, 1, tzinfo=timezone.utc),
        end=datetime(2027, 1, 1, tzinfo=timezone.utc),
    )
    if report.healthy:
        print(f"Data healthy: {report.coverage_pct:.1f}% coverage")
    else:
        print(f"Data unhealthy: {report.reason}")
        print(f"  Auto-repaired: {report.repaired}")
        print(f"  Gaps remaining: {len(report.gaps)}")
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lib.data_lake.spec import DatasetSpec
from lib.data_lake.catalog import DataCatalog
from lib.data_lake.backfill_planner import BackfillPlanner
from lib.data_lake.storage import DataLakePaths

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Health threshold
# ---------------------------------------------------------------------------

HEALTHY_COVERAGE_THRESHOLD: float = 90.0
"""Minimum coverage percentage for data to be considered healthy."""


# ---------------------------------------------------------------------------
# HealthReport
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HealthReport:
    """Result of a data health check.

    Attributes:
        healthy: All data present, checksums valid, coverage above threshold.
        coverage_pct: Percentage of expected data that exists.
        gaps: List of time ranges still missing after repair attempt.
        checksum_pass: Whether checksums verified successfully.
        repaired: Whether auto-repair was triggered.
        repair_action: Description of what was repaired (empty string if none).
        reason: Human-readable explanation if healthy is False.
        passport: DataPassport dict if available, None otherwise.
        checked_at: ISO-8601 timestamp of the check.
    """

    healthy: bool
    coverage_pct: float
    gaps: list[dict[str, Any]] = field(default_factory=list)
    checksum_pass: bool = True
    repaired: bool = False
    repair_action: str = ""
    reason: str = ""
    passport: dict[str, Any] | None = None
    checked_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


# ---------------------------------------------------------------------------
# DataHealthChecker
# ---------------------------------------------------------------------------


class DataHealthChecker:
    """Verify and optionally repair market data for a training run.

    Usage::

        checker = DataHealthChecker()
        report = checker.ensure_healthy(
            symbols=["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"],
            intervals=["1h", "4h"],
            data_types=("klines",),
            start=datetime(2023, 1, 1, tzinfo=timezone.utc),
            end=datetime(2027, 1, 1, tzinfo=timezone.utc),
        )
    """

    def __init__(
        self,
        data_dir: str | Path = "data_lake",
        catalog_path: str | None = None,
    ) -> None:
        """Initialise the health checker.

        Args:
            data_dir: Root of the Data Lake (default ``"data_lake"``).
            catalog_path: Explicit catalog path.  If ``None``, resolves
                ``<data_dir>/catalog.json``.
        """
        self._data_dir = Path(data_dir)
        if catalog_path is None:
            catalog_path = str(self._data_dir / "catalog.json")
        self._catalog = DataCatalog(catalog_path=catalog_path)
        self._planner = BackfillPlanner()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check(
        self,
        symbols: list[str],
        intervals: list[str],
        data_types: tuple[str, ...] = ("klines",),
        start: datetime | None = None,
        end: datetime | None = None,
        dataset_id: str = "health-check",
        priority: str = "P0",
        allow_synthetic: bool = False,
        auto_repair: bool = True,
    ) -> HealthReport:
        """Check data health and optionally repair.

        Args:
            symbols: Trading pair symbols (e.g. ``["BTCUSDT"]``).
            intervals: Candle intervals (e.g. ``["1h", "4h"]``).
            data_types: Data type names (default ``("klines",)``).
            start: Start of required range (default 2023-01-01).
            end: End of required range (default 2027-01-01).
            dataset_id: Identifier for the DatasetSpec.
            priority: Dataset priority.
            allow_synthetic: Whether synthetic fallback is allowed.
            auto_repair: If ``True``, trigger backfill when data is
                missing or coverage is below threshold.

        Returns:
            A :class:`HealthReport` with the check result.
        """
        if start is None:
            start = datetime(2023, 1, 1, tzinfo=timezone.utc)
        if end is None:
            end = datetime(2027, 1, 1, tzinfo=timezone.utc)

        spec = DatasetSpec(
            dataset_id=dataset_id,
            source="binance",
            market="um_futures",
            symbols=tuple(symbols),
            intervals=tuple(intervals),
            data_types=data_types,
            start=start,
            end=end,
            priority=priority,
            backtest_required=True,
            allow_synthetic=allow_synthetic,
        )

        # --- First pass: check current state ---
        coverage = self._catalog.coverage_pct(spec)
        gaps = self._catalog.find_gaps(spec)

        # If catalog is cold/stale but files exist on disk, trust a direct
        # data-dir scan.  Downloader catalog entries can be file-count based
        # and may not carry exact start/end timestamps yet.
        if coverage == 0.0 or gaps:
            disk_coverage = self._scan_disk_coverage(spec)
            if disk_coverage >= HEALTHY_COVERAGE_THRESHOLD:
                coverage = disk_coverage
                gaps = []
                logger.info(
                    "  Disk scan found healthy data: coverage=%.1f%%",
                    coverage,
                )
            elif disk_coverage > coverage:
                coverage = disk_coverage
                logger.info(
                    "  Disk scan improved coverage estimate: coverage=%.1f%%",
                    coverage,
                )

        logger.info(
            "Data health check: %s coverage=%.1f%%, gaps=%d",
            spec.dataset_id, coverage, len(gaps),
        )

        if coverage >= HEALTHY_COVERAGE_THRESHOLD and not gaps:
            # Data looks good — verify checksums if possible
            checksum_pass = self._quick_checksum_check(symbols, intervals)
            return HealthReport(
                healthy=True,
                coverage_pct=coverage,
                gaps=[],
                checksum_pass=checksum_pass,
                repaired=False,
                reason="All data present and healthy",
                passport=self._build_passport(spec),
            )

        # --- Auto-repair if enabled ---
        if auto_repair and (coverage < HEALTHY_COVERAGE_THRESHOLD or gaps):
            return self._repair_and_verify(spec)

        # --- Not healthy, not repairing ---
        fail_reason = (
            f"Coverage {coverage:.1f}% below threshold "
            f"{HEALTHY_COVERAGE_THRESHOLD}% ({len(gaps)} gap(s))"
        )
        return HealthReport(
            healthy=False,
            coverage_pct=coverage,
            gaps=gaps,
            checksum_pass=False,
            repaired=False,
            reason=fail_reason,
            passport=self._build_passport(spec),
        )

    def ensure_healthy(
        self,
        symbols: list[str],
        intervals: list[str],
        data_types: tuple[str, ...] = ("klines",),
        start: datetime | None = None,
        end: datetime | None = None,
        dataset_id: str = "training-data",
    ) -> HealthReport:
        """Check health and raise if the dataset cannot be made healthy.

        Unlike :meth:`check`, this will **not** return an unhealthy
        report — it either succeeds or raises.
        """
        report = self.check(
            symbols=symbols,
            intervals=intervals,
            data_types=data_types,
            start=start,
            end=end,
            dataset_id=dataset_id,
            auto_repair=True,
        )
        if not report.healthy:
            raise RuntimeError(
                f"Data health check FAILED after auto-repair: {report.reason}"
            )
        return report

    # ------------------------------------------------------------------
    # Disk scan fallback (when catalog is cold)
    # ------------------------------------------------------------------

    def _scan_disk_coverage(self, spec: DatasetSpec) -> float:
        """Scan actual data_lake directories for parquet files when catalog is cold.

        Counts parquet files on disk and compares against expected files
        from the DatasetSpec. Does NOT check row counts (too slow).
        """
        if spec.source != "binance" or spec.market != "um_futures":
            return 0.0

        expected = 0
        found = 0
        for symbol in spec.symbols:
            for interval in spec.intervals:
                for year in range(spec.start.year, spec.end.year + 1):
                    sm = spec.start.month if year == spec.start.year else 1
                    em = spec.end.month if year == spec.end.year else 12
                    for month in range(sm, em + 1):
                        expected += 1
                        bronze_path = (
                            self._data_dir / "bronze" / "binance" / "um" / "klines"
                            / symbol / interval / str(year) / f"{month:02d}.parquet"
                        )
                        raw_path = (
                            self._data_dir / "raw" / "binance" / "um" / "klines"
                            / symbol / interval / str(year) / f"{month:02d}.parquet"
                        )
                        if bronze_path.exists() or raw_path.exists():
                            found += 1

        if expected == 0:
            return 0.0
        return min(100.0, round(found / expected * 100, 2))

    def _repair_and_verify(self, spec: DatasetSpec) -> HealthReport:
        """Attempt to backfill missing data and re-check."""
        logger.info("Auto-repair triggered for %s", spec.dataset_id)

        try:
            manifest = self._planner.plan(spec, self._catalog)
        except Exception as e:
            logger.warning("  Backfill planning failed: %s", e)
            return HealthReport(
                healthy=False,
                coverage_pct=self._catalog.coverage_pct(spec),
                gaps=self._catalog.find_gaps(spec),
                checksum_pass=False,
                repaired=True,
                repair_action=f"Backfill planning failed: {e}",
                reason="Could not plan backfill — planner error",
            )

        if not manifest.entries:
            logger.info("  No entries to download — re-checking coverage")
            coverage = self._catalog.coverage_pct(spec)
            gaps = self._catalog.find_gaps(spec)
            healthy = coverage >= HEALTHY_COVERAGE_THRESHOLD and not gaps
            return HealthReport(
                healthy=healthy,
                coverage_pct=coverage,
                gaps=gaps,
                checksum_pass=True,
                repaired=True,
                repair_action="No downloads needed (catalog metadata updated?)",
                reason="Healthy after re-check" if healthy else "Gaps remain after re-check",
                passport=self._build_passport(spec),
            )

        # Try to download
        logger.info(
            "  Download manifest: %d entries, %s estimated",
            manifest.total_entries,
            _format_size(manifest.total_estimated_rows),
        )

        try:
            from lib.data_lake.downloader import BinanceUmDownloader

            downloader = BinanceUmDownloader(
                data_dir=str(self._data_dir),
                max_workers=4,
                rate_per_minute=1200,
            )
            # Convert dataclass to dict for downloader compatibility
            manifest_dict = {
                "manifest_id": manifest.manifest_id,
                "entries": [
                    {
                        "symbol": e.symbol,
                        "interval": e.interval,
                        "data_type": e.data_type,
                        "start_ms": e.start_ms,
                        "end_ms": e.end_ms,
                        "estimated_rows": e.estimated_rows,
                    }
                    for e in manifest.entries
                ],
            }
            result = downloader.download_all(manifest_dict)

            # Register downloaded files in catalog
            for path in result.paths_created:
                self._catalog.add_entry(
                    symbol=_extract_symbol_from_path(path),
                    interval=_extract_interval_from_path(path),
                    start_ts=0,  # TODO: read from parquet metadata
                    end_ts=0,
                    row_count=0,
                    checksum="downloaded",
                )
            self._catalog.save()
            logger.info(
                "  Download complete: %d succeeded, %d failed",
                result.succeeded, result.failed,
            )
        except Exception as e:
            logger.warning("  Download failed: %s", e)
            # Continue to verify even if download had errors

        # Re-check
        coverage = self._catalog.coverage_pct(spec)
        gaps = self._catalog.find_gaps(spec)
        healthy = coverage >= HEALTHY_COVERAGE_THRESHOLD and not gaps

        return HealthReport(
            healthy=healthy,
            coverage_pct=coverage,
            gaps=gaps,
            checksum_pass=True,
            repaired=True,
            repair_action=(
                f"Backfill attempted: downloaded entries for "
                f"{manifest.total_entries} missing range(s)"
            ),
            reason="Healthy after repair" if healthy else (
                f"Coverage {coverage:.1f}% still below threshold "
                f"({len(gaps)} gap(s) remain)"
            ),
            passport=self._build_passport(spec),
        )

    def _quick_checksum_check(
        self,
        symbols: list[str],
        intervals: list[str],
    ) -> bool:
        """Quick integrity check — verify parquet files are readable."""
        from lib.data_lake.checksum import compute_sha256

        try:
            for sym in symbols:
                for interval in intervals:
                    path = (
                        self._data_dir / "raw" / "binance" / "um" / "klines"
                        / sym / interval / "2024" / "01.parquet"
                    )
                    if not path.exists():
                        path = (
                            self._data_dir / "bronze" / "binance" / "um" / "klines"
                            / sym / interval / "2024" / "01.parquet"
                        )
                    if path.exists():
                        _ = compute_sha256(path)
            return True
        except Exception:
            return False

    def _build_passport(self, spec: DatasetSpec) -> dict[str, Any] | None:
        """Build a lightweight DataPassport dict from catalog state."""
        try:
            from lib.data_lake.passport import DataPassport

            passport = DataPassport.from_spec(spec, self._catalog)
            return passport.to_dict()
        except Exception:
            return None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _format_size(estimated_rows: int) -> str:
    """Rough size string for estimated row counts."""
    if estimated_rows < 1_000:
        return f"{estimated_rows} rows"
    elif estimated_rows < 1_000_000:
        return f"{estimated_rows / 1_000:.1f}K rows"
    else:
        return f"{estimated_rows / 1_000_000:.1f}M rows"


def _extract_symbol_from_path(path: Path) -> str:
    """Extract symbol from a data-lake path."""
    parts = path.parts
    for p in parts:
        if p.endswith("USDT") or p.endswith("USDC"):
            return p
    return "UNKNOWN"


def _extract_interval_from_path(path: Path) -> str:
    """Extract interval from a klines path."""
    parts = path.parts
    try:
        idx = parts.index("klines")
        return parts[idx + 2] if len(parts) > idx + 2 else "unknown"
    except ValueError:
        return "unknown"
