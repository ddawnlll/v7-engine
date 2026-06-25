"""
Tests for lib/market_data/binance/backfill.py

Uses mocked dependencies to avoid real network calls.
"""

import tempfile
from unittest.mock import Mock, create_autospec

import pytest

from lib.market_data.binance.backfill import BackfillOrchestrator
from lib.market_data.binance.klines_service import KlinesService
from lib.market_data.binance.funding_service import FundingService
from lib.market_data.binance.rate_limiter import BinanceRateLimiter
from lib.market_data.binance.checkpoint import BackfillCheckpoint
from lib.market_data.storage import StorageWriter
from lib.market_data.catalog import DataCatalog
from lib.market_data.contracts import KlineRecord

SAMPLE_KLINE_RAW = [
    1_500_000_000_000,   # open time
    "50000.0",           # open
    "51000.0",           # high
    "49000.0",           # low
    "50500.0",           # close
    "100.0",             # volume
    1_500_000_000_999,   # close time
    "5000000.0",         # quote volume
    1000,                # trade count
    "55.0",              # taker buy volume
    "2750000.0",         # taker buy quote volume
    "0",                 # ignore
]

SAMPLE_FUNDING_RAW = [[1_500_000_000_000, "0.0001"]]


class TestBackfillOrchestrator:
    def test_backfill_single_symbol_interval(self):
        """Basic backfill for a single symbol and interval."""
        mock_client = Mock()
        mock_client.get_klines.return_value = [SAMPLE_KLINE_RAW]
        mock_client.get_funding_rate.return_value = SAMPLE_FUNDING_RAW

        klines = KlinesService(mock_client)
        funding = FundingService(mock_client)

        with tempfile.TemporaryDirectory() as tmp_dir:
            writer = StorageWriter(base_dir=tmp_dir)
            catalog = DataCatalog(catalog_path=f"{tmp_dir}/catalog.json")
            limiter = BinanceRateLimiter()
            checkpoint = BackfillCheckpoint(file_path=f"{tmp_dir}/checkpoint.json")

            orchestrator = BackfillOrchestrator(
                klines_service=klines,
                funding_service=funding,
                storage_writer=writer,
                catalog=catalog,
                rate_limiter=limiter,
                checkpoint=checkpoint,
            )

            stats = orchestrator.backfill(
                symbols=["BTCUSDT"],
                intervals=["1h"],
                start_time=1_500_000_000_000,
                end_time=1_500_003_600_000,
            )

            assert stats["total_symbols"] == 1
            assert stats["total_records"] == 1
            assert stats["errors"] == []

    def test_backfill_multiple_symbols(self):
        """Backfill across multiple symbols."""
        mock_client = Mock()
        mock_client.get_klines.return_value = [SAMPLE_KLINE_RAW]
        mock_client.get_funding_rate.return_value = SAMPLE_FUNDING_RAW

        klines = KlinesService(mock_client)
        funding = FundingService(mock_client)

        with tempfile.TemporaryDirectory() as tmp_dir:
            writer = StorageWriter(base_dir=tmp_dir)
            catalog = DataCatalog(catalog_path=f"{tmp_dir}/catalog.json")
            limiter = BinanceRateLimiter()
            checkpoint = BackfillCheckpoint(file_path=f"{tmp_dir}/checkpoint.json")

            orchestrator = BackfillOrchestrator(
                klines_service=klines,
                funding_service=funding,
                storage_writer=writer,
                catalog=catalog,
                rate_limiter=limiter,
                checkpoint=checkpoint,
            )

            stats = orchestrator.backfill(
                symbols=["BTCUSDT", "ETHUSDT"],
                intervals=["1h"],
                start_time=1_500_000_000_000,
                end_time=1_500_003_600_000,
            )

            assert stats["total_symbols"] == 2
            assert stats["total_records"] == 2  # 1 record each

    def test_backfill_skips_completed(self):
        """Backfill should skip symbols/intervals already checkpointed."""
        mock_client = Mock()
        mock_client.get_klines.return_value = [SAMPLE_KLINE_RAW]
        mock_client.get_funding_rate.return_value = SAMPLE_FUNDING_RAW

        klines = KlinesService(mock_client)
        funding = FundingService(mock_client)

        with tempfile.TemporaryDirectory() as tmp_dir:
            writer = StorageWriter(base_dir=tmp_dir)
            catalog = DataCatalog(catalog_path=f"{tmp_dir}/catalog.json")
            limiter = BinanceRateLimiter()
            checkpoint = BackfillCheckpoint(file_path=f"{tmp_dir}/checkpoint.json")

            # Mark as completed first
            checkpoint.save("BTCUSDT", "1h", 1_500_000_000_000, 1_500_003_600_000, [])

            orchestrator = BackfillOrchestrator(
                klines_service=klines,
                funding_service=funding,
                storage_writer=writer,
                catalog=catalog,
                rate_limiter=limiter,
                checkpoint=checkpoint,
            )

            stats = orchestrator.backfill(
                symbols=["BTCUSDT"],
                intervals=["1h"],
                start_time=1_500_000_000_000,
                end_time=1_500_003_600_000,
            )

            assert stats["total_records"] == 0  # Skipped
            # Client should not have been called
            # (checkpoint skips before any fetch)

    def test_backfill_handles_client_error(self):
        """Backfill should continue on error with the next symbol/interval."""
        mock_client = Mock()
        mock_client.get_klines.side_effect = Exception("API error")
        mock_client.get_funding_rate.return_value = SAMPLE_FUNDING_RAW

        klines = KlinesService(mock_client)
        funding = FundingService(mock_client)

        with tempfile.TemporaryDirectory() as tmp_dir:
            writer = StorageWriter(base_dir=tmp_dir)
            catalog = DataCatalog(catalog_path=f"{tmp_dir}/catalog.json")
            limiter = BinanceRateLimiter()
            checkpoint = BackfillCheckpoint(file_path=f"{tmp_dir}/checkpoint.json")

            orchestrator = BackfillOrchestrator(
                klines_service=klines,
                funding_service=funding,
                storage_writer=writer,
                catalog=catalog,
                rate_limiter=limiter,
                checkpoint=checkpoint,
            )

            stats = orchestrator.backfill(
                symbols=["BTCUSDT", "ETHUSDT"],
                intervals=["1h"],
                start_time=1_500_000_000_000,
                end_time=1_500_003_600_000,
            )

            assert stats["total_records"] == 0
            assert len(stats["errors"]) == 2  # Both fail
            assert all("API error" in e for e in stats["errors"])

    def test_backfill_updates_catalog(self):
        """Backfill should add entries to the catalog."""
        mock_client = Mock()
        mock_client.get_klines.return_value = [SAMPLE_KLINE_RAW]
        mock_client.get_funding_rate.return_value = SAMPLE_FUNDING_RAW

        klines = KlinesService(mock_client)
        funding = FundingService(mock_client)

        with tempfile.TemporaryDirectory() as tmp_dir:
            writer = StorageWriter(base_dir=tmp_dir)
            catalog = DataCatalog(catalog_path=f"{tmp_dir}/catalog.json")
            limiter = BinanceRateLimiter()
            checkpoint = BackfillCheckpoint(file_path=f"{tmp_dir}/checkpoint.json")

            orchestrator = BackfillOrchestrator(
                klines_service=klines,
                funding_service=funding,
                storage_writer=writer,
                catalog=catalog,
                rate_limiter=limiter,
                checkpoint=checkpoint,
            )

            orchestrator.backfill(
                symbols=["BTCUSDT"],
                intervals=["1h"],
                start_time=1_500_000_000_000,
                end_time=1_500_003_600_000,
            )

            entries = catalog.query()
            assert len(entries) == 1
            assert entries[0]["symbol"] == "BTCUSDT"
            assert entries[0]["interval"] == "1h"
            assert entries[0]["row_count"] == 1

    def test_backfill_writes_raw_and_normalized(self):
        """Backfill should write both raw and normalized files."""
        mock_client = Mock()
        mock_client.get_klines.return_value = [SAMPLE_KLINE_RAW]
        mock_client.get_funding_rate.return_value = SAMPLE_FUNDING_RAW

        klines = KlinesService(mock_client)
        funding = FundingService(mock_client)

        with tempfile.TemporaryDirectory() as tmp_dir:
            writer = StorageWriter(base_dir=tmp_dir)
            catalog = DataCatalog(catalog_path=f"{tmp_dir}/catalog.json")
            limiter = BinanceRateLimiter()
            checkpoint = BackfillCheckpoint(file_path=f"{tmp_dir}/checkpoint.json")

            orchestrator = BackfillOrchestrator(
                klines_service=klines,
                funding_service=funding,
                storage_writer=writer,
                catalog=catalog,
                rate_limiter=limiter,
                checkpoint=checkpoint,
            )

            stats = orchestrator.backfill(
                symbols=["BTCUSDT"],
                intervals=["1h"],
                start_time=1_500_000_000_000,
                end_time=1_500_003_600_000,
            )

            assert stats["total_records"] > 0

            # Check files exist
            import os
            raw_dir = os.path.join(tmp_dir, "raw", "BTCUSDT")
            norm_dir = os.path.join(tmp_dir, "normalized", "BTCUSDT")

            assert os.path.exists(raw_dir)
            assert os.path.exists(norm_dir)

            # Should have .parquet files
            raw_files = [f for f in os.listdir(raw_dir) if f.endswith(".parquet")]
            norm_files = [f for f in os.listdir(norm_dir) if f.endswith(".parquet")]
            assert len(raw_files) >= 1
            assert len(norm_files) >= 1
