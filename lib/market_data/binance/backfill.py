"""
Backfill orchestrator for Binance market data.

Ties together KlinesService, FundingService, StorageWriter,
DataCatalog, BinanceRateLimiter, and BackfillCheckpoint into
a single backfill workflow.

Usage:
    orchestrator = BackfillOrchestrator(
        klines_service=klines_service,
        funding_service=funding_service,
        storage_writer=storage_writer,
        catalog=catalog,
        rate_limiter=rate_limiter,
        checkpoint=checkpoint,
    )
    stats = orchestrator.backfill(
        symbols=["BTCUSDT", "ETHUSDT"],
        intervals=["1h"],
        start_time=1700000000000,
        end_time=1700086400000,
    )
"""

import hashlib
import logging
from typing import Optional

from lib.market_data.binance.client import BinanceClient
from lib.market_data.binance.klines_service import KlinesService
from lib.market_data.binance.funding_service import FundingService, FundingRecord
from lib.market_data.binance.rate_limiter import BinanceRateLimiter
from lib.market_data.binance.checkpoint import BackfillCheckpoint
from lib.market_data.storage import StorageWriter
from lib.market_data.catalog import DataCatalog
from lib.market_data.contracts import KlineRecord

logger = logging.getLogger(__name__)

# Intervals that support funding rate fetching
_FUNDING_INTERVALS = {"1h", "2h", "4h", "6h", "8h", "12h", "1d", "3d", "1w"}


class BackfillOrchestrator:
    """Orchestrate backfill of historical market data."""

    def __init__(
        self,
        klines_service: KlinesService,
        funding_service: FundingService,
        storage_writer: StorageWriter,
        catalog: DataCatalog,
        rate_limiter: BinanceRateLimiter,
        checkpoint: BackfillCheckpoint,
    ) -> None:
        self._klines = klines_service
        self._funding = funding_service
        self._storage = storage_writer
        self._catalog = catalog
        self._limiter = rate_limiter
        self._checkpoint = checkpoint

    def backfill(
        self,
        symbols: list[str],
        intervals: list[str],
        start_time: int,
        end_time: int,
        batch_size: int = 50000,
    ) -> dict:
        """Execute a backfill for the given symbols and intervals.

        Args:
            symbols: List of trading pair symbols (e.g. ["BTCUSDT"]).
            intervals: List of kline intervals (e.g. ["1h", "4h"]).
            start_time: Start timestamp in milliseconds.
            end_time: End timestamp in milliseconds.
            batch_size: Number of klines per batch (default 50000).

        Returns:
            Dict with summary statistics:
                {"total_symbols": int, "total_intervals": int,
                 "total_records": int, "errors": list[str]}
        """
        stats: dict = {
            "total_symbols": len(symbols),
            "total_intervals": len(intervals),
            "total_records": 0,
            "errors": [],
        }

        for symbol in symbols:
            for interval in intervals:
                try:
                    n = self._backfill_one(symbol, interval, start_time, end_time, batch_size)
                    stats["total_records"] += n
                except Exception as e:
                    msg = f"{symbol}/{interval}: {e}"
                    logger.error(msg)
                    stats["errors"].append(msg)

        self._catalog.save()
        return stats

    def _backfill_one(
        self,
        symbol: str,
        interval: str,
        start_time: int,
        end_time: int,
        batch_size: int,
    ) -> int:
        """Backfill a single symbol/interval combination.

        Returns:
            Number of records written.
        """
        logger.info("Backfilling %s %s [%d, %d)", symbol, interval, start_time, end_time)

        # Check checkpoint
        if self._checkpoint.is_completed(symbol, interval, start_time, end_time):
            logger.info("Skipping %s %s (already completed)", symbol, interval)
            return 0

        # Fetch klines (KlinesService handles pagination internally)
        self._limiter.acquire(weight=2)  # klines weight
        records, quality = self._klines.fetch(symbol, interval, start_time, end_time)
        logger.info(
            "Fetched %d records for %s %s (quality: %s)",
            len(records), symbol, interval,
            "complete" if quality.is_complete else f"gaps={quality.gap_count} dups={quality.duplicate_count}",
        )

        if not records:
            logger.warning("No records returned for %s %s", symbol, interval)
            return 0

        # Write raw Parquet
        raw_path = self._storage.write_raw_klines(
            records, symbol, interval, records[0].timestamp, records[-1].timestamp,
        )

        # Write normalized Parquet
        norm_path = self._storage.write_normalized_klines(
            records, symbol, interval, records[0].timestamp, records[-1].timestamp,
        )

        # Fetch funding rates if applicable
        if interval in _FUNDING_INTERVALS:
            try:
                self._limiter.acquire(weight=1)
                funding_records = self._funding.fetch(
                    symbol,
                    start_time=start_time,
                    end_time=end_time,
                )
                if funding_records:
                    self._storage.write_funding(
                        funding_records, symbol,
                        funding_records[0].timestamp, funding_records[-1].timestamp,
                    )
                    logger.info("Wrote %d funding records for %s", len(funding_records), symbol)
            except Exception as e:
                logger.warning("Failed to fetch funding for %s: %s", symbol, e)

        # Compute checksum for the raw file
        checksum = self._compute_checksum(raw_path)

        # Update catalog
        self._catalog.add_entry(
            symbol=symbol,
            interval=interval,
            start_ts=start_time,
            end_ts=end_time,
            row_count=len(records),
            checksum=checksum,
        )

        # Update checkpoint
        completed_ranges = [{"start": start_time, "end": end_time}]
        self._checkpoint.save(
            symbol, interval, start_time, end_time, completed_ranges,
        )

        logger.info(
            "Completed %s %s: %d records",
            symbol, interval, len(records),
        )
        return len(records)

    @staticmethod
    def _compute_checksum(file_path: str) -> str:
        """Compute SHA-256 checksum of a file."""
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                sha256.update(chunk)
        return sha256.hexdigest()
