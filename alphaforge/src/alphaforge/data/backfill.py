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
