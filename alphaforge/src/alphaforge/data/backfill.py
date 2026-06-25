"""AlphaForge market data backfill pipeline.

Wraps the shared ``lib.market_data`` service to fetch Binance klines,
persist raw/normalized Parquet files, and validate stored integrity.
Large artifacts are written outside the repository (default ``~/v7-data``)
per ``alphaforge/docs/storage_policy.md``.

This module is the AlphaForge-owned entry point for real market data
ingestion. It does NOT issue trades or make policy decisions.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from alphaforge.data.integrity import IntegrityReport, validate_kline_parquet
from alphaforge.errors import AlphaForgeError
from lib.market_data.binance.backfill import BackfillOrchestrator
from lib.market_data.binance.checkpoint import BackfillCheckpoint
from lib.market_data.binance.client import BinanceClient
from lib.market_data.binance.funding_service import FundingService
from lib.market_data.binance.klines_service import KlinesService
from lib.market_data.binance.rate_limiter import BinanceRateLimiter
from lib.market_data.catalog import DataCatalog
from lib.market_data.storage import StorageWriter

logger = logging.getLogger(__name__)

DEFAULT_SYMBOLS: tuple[str, ...] = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
DEFAULT_INTERVALS: tuple[str, ...] = ("1h", "4h", "1d")
_DEFAULT_LOOKBACK_DAYS: int = 30


class BackfillError(AlphaForgeError):
    """Raised when the backfill configuration or execution is invalid."""

    pass


@dataclass
class BackfillConfig:
    """Configuration for one AlphaForge backfill run."""

    symbols: tuple[str, ...]
    intervals: tuple[str, ...]
    start_time_ms: int
    end_time_ms: int
    data_dir: str
    rate_limit_max_weight_per_minute: int = 1200

    def __post_init__(self) -> None:
        if not self.symbols:
            raise BackfillError("At least one symbol is required")
        if not self.intervals:
            raise BackfillError("At least one interval is required")
        if self.end_time_ms <= self.start_time_ms:
            raise BackfillError("end_time must be after start_time")
        os.makedirs(self.data_dir, exist_ok=True)

    @property
    def checkpoint_path(self) -> str:
        return os.path.join(self.data_dir, "backfill_checkpoint.json")

    @property
    def catalog_path(self) -> str:
        return os.path.join(self.data_dir, "catalog.json")

    def to_dict(self) -> dict:
        """Serialize config to a plain dict for reports / logging."""
        return {
            "symbols": list(self.symbols),
            "intervals": list(self.intervals),
            "start_time_ms": self.start_time_ms,
            "end_time_ms": self.end_time_ms,
            "data_dir": self.data_dir,
            "rate_limit_max_weight_per_minute": self.rate_limit_max_weight_per_minute,
        }


@dataclass
class BackfillResult:
    """Result of a backfill run, including execution stats and integrity checks."""

    config: BackfillConfig
    stats: dict
    integrity_reports: list[IntegrityReport] = field(default_factory=list)
    ok: bool = False

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "config": self.config.to_dict(),
            "stats": self.stats,
            "integrity": [r.to_dict() for r in self.integrity_reports],
        }


class AlphaForgeBackfillPipeline:
    """High-level AlphaForge entry point for historical market data backfill.

    Usage:
        pipeline = AlphaForgeBackfillPipeline()
        config = AlphaForgeBackfillPipeline.default_config()
        result = pipeline.run(config)
        if not result.ok:
            raise SystemExit(1)
    """

    def __init__(self, client: Optional[BinanceClient] = None) -> None:
        """Initialize pipeline.

        Args:
            client: Optional BinanceClient instance. When omitted, a default
                client is created. Pass a mock client in tests.
        """
        self._client = client

    @classmethod
    def default_config(
        cls,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        symbols: Optional[list[str]] = None,
        intervals: Optional[list[str]] = None,
        data_dir: Optional[str] = None,
    ) -> BackfillConfig:
        """Build a sensible default backfill configuration.

        Defaults:
          - symbols: BTCUSDT, ETHUSDT, SOLUSDT
          - intervals: 1h, 4h, 1d
          - range: last 30 days
          - data_dir: ``$V7_DATA_DIR`` or ``~/v7-data``
        """
        now = datetime.now(timezone.utc)
        if end is None:
            end = now
        if start is None:
            start = datetime.fromtimestamp(
                now.timestamp() - (_DEFAULT_LOOKBACK_DAYS * 86_400),
                tz=timezone.utc,
            )

        resolved_data_dir = data_dir or os.environ.get("V7_DATA_DIR")
        if not resolved_data_dir:
            resolved_data_dir = os.path.expanduser("~/v7-data")

        return BackfillConfig(
            symbols=tuple(symbols or DEFAULT_SYMBOLS),
            intervals=tuple(intervals or DEFAULT_INTERVALS),
            start_time_ms=int(start.timestamp() * 1_000),
            end_time_ms=int(end.timestamp() * 1_000),
            data_dir=resolved_data_dir,
        )

    def run(self, config: BackfillConfig) -> BackfillResult:
        """Execute the backfill and validate every artifact that was written.

        Args:
            config: Backfill configuration.

        Returns:
            BackfillResult with stats and per-file integrity reports.
        """
        client = self._client if self._client is not None else BinanceClient()

        klines_service = KlinesService(client)
        funding_service = FundingService(client)
        storage_writer = StorageWriter(base_dir=config.data_dir)
        catalog = DataCatalog(catalog_path=config.catalog_path)
        rate_limiter = BinanceRateLimiter(
            max_weight_per_minute=config.rate_limit_max_weight_per_minute,
        )
        checkpoint = BackfillCheckpoint(file_path=config.checkpoint_path)

        orchestrator = BackfillOrchestrator(
            klines_service=klines_service,
            funding_service=funding_service,
            storage_writer=storage_writer,
            catalog=catalog,
            rate_limiter=rate_limiter,
            checkpoint=checkpoint,
        )

        logger.info(
            "Starting AlphaForge backfill: symbols=%s intervals=%s range=[%d, %d)",
            config.symbols,
            config.intervals,
            config.start_time_ms,
            config.end_time_ms,
        )

        stats = orchestrator.backfill(
            symbols=list(config.symbols),
            intervals=list(config.intervals),
            start_time=config.start_time_ms,
            end_time=config.end_time_ms,
        )

        integrity_reports = self._validate_catalog(catalog, config.data_dir)

        ok = not stats.get("errors") and all(r.ok for r in integrity_reports)

        logger.info(
            "Backfill complete: ok=%s records=%d errors=%d integrity_reports=%d",
            ok,
            stats.get("total_records", 0),
            len(stats.get("errors", [])),
            len(integrity_reports),
        )

        return BackfillResult(
            config=config,
            stats=stats,
            integrity_reports=integrity_reports,
            ok=ok,
        )

    def _validate_catalog(
        self,
        catalog: DataCatalog,
        data_dir: str,
    ) -> list[IntegrityReport]:
        """Validate every raw kline file recorded in the catalog."""
        reports: list[IntegrityReport] = []
        for entry in catalog.query():
            symbol = entry["symbol"]
            interval = entry["interval"]
            start_ts = entry["start_ts"]
            end_ts = entry["end_ts"]

            raw_path = os.path.join(
                data_dir,
                "raw",
                symbol,
                f"{symbol}_{interval}_{start_ts}_{end_ts}.parquet",
            )

            report = validate_kline_parquet(
                raw_path,
                interval,
                expected_start=start_ts,
                expected_end=end_ts,
            )
            reports.append(report)

            if not report.ok:
                logger.warning("Integrity failed for %s/%s: %s", symbol, interval, report.warnings)

        return reports
