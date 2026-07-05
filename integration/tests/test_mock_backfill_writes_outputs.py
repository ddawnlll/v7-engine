"""
Integration test for backfill orchestration with mocked BinanceClient.

Verifies the full backfill pipeline:
  - mock BinanceClient -> BackfillOrchestrator
  - 2 symbols x 1 interval
  - raw/.parquet, normalized/.parquet, .sha256 sidecars
  - catalog updated
  - No real network calls
"""

import os
import tempfile
from unittest.mock import Mock

import pytest

from lib.market_data.binance.client import BinanceClient
from lib.market_data.binance.klines_service import KlinesService
from lib.market_data.binance.funding_service import FundingService
from lib.market_data.binance.backfill import BackfillOrchestrator
from lib.market_data.binance.rate_limiter import BinanceRateLimiter
from lib.market_data.binance.checkpoint import BackfillCheckpoint
from lib.market_data.storage import StorageWriter
from lib.market_data.catalog import DataCatalog

SAMPLE_KLINE_RAW = [
    1_500_000_000_000,
    "50000.0",
    "51000.0",
    "49000.0",
    "50500.0",
    "100.0",
    1_500_000_000_999,
    "5000000.0",
    1000,
    "55.0",
    "2750000.0",
    "0",
]

SAMPLE_KLINE_RAW_2 = [
    1_500_003_600_000,
    "50100.0",
    "51100.0",
    "49100.0",
    "50600.0",
    "101.0",
    1_500_004_600_000,
    "5000000.0",
    1001,
    "56.0",
    "2760000.0",
    "0",
]

SAMPLE_FUNDING_RAW = [[1_500_000_000_000, "0.0001"]]


@pytest.mark.integration
class TestMockBackfillWritesOutputs:
    def test_backfill_two_symbols_one_interval(self):
        """Run backfill with mocked client, verify all outputs."""
        mock_client = Mock(spec=BinanceClient)

        # Return data for BTCUSDT and ETHUSDT klines (2 klines each)
        def mock_get_klines(symbol, interval, **kwargs):
            if symbol == "BTCUSDT":
                return [SAMPLE_KLINE_RAW, SAMPLE_KLINE_RAW_2]
            elif symbol == "ETHUSDT":
                return [SAMPLE_KLINE_RAW, SAMPLE_KLINE_RAW_2]
            return []

        mock_client.get_klines.side_effect = mock_get_klines
        mock_client.get_funding_rate.return_value = SAMPLE_FUNDING_RAW

        klines_service = KlinesService(mock_client)
        funding_service = FundingService(mock_client)

        with tempfile.TemporaryDirectory() as tmp_dir:
            writer = StorageWriter(base_dir=tmp_dir)
            catalog = DataCatalog(catalog_path=os.path.join(tmp_dir, "catalog.json"))

            with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as cp_file:
                checkpoint_path = cp_file.name

            try:
                checkpoint = BackfillCheckpoint(file_path=checkpoint_path)
                limiter = BinanceRateLimiter()

                orchestrator = BackfillOrchestrator(
                    klines_service=klines_service,
                    funding_service=funding_service,
                    storage_writer=writer,
                    catalog=catalog,
                    rate_limiter=limiter,
                    checkpoint=checkpoint,
                )

                stats = orchestrator.backfill(
                    symbols=["BTCUSDT", "ETHUSDT"],
                    intervals=["1h"],
                    start_time=1_500_000_000_000,
                    end_time=1_500_007_200_000,
                )

                # ---- Assertions ----

                # 1. Stats
                assert stats["total_symbols"] == 2
                assert stats["total_records"] > 0
                assert stats["errors"] == []

                # 2. Raw parquet files exist for both symbols
                for symbol in ["BTCUSDT", "ETHUSDT"]:
                    raw_dir = os.path.join(tmp_dir, "raw", symbol)
                    norm_dir = os.path.join(tmp_dir, "normalized", symbol)

                    assert os.path.isdir(raw_dir), f"Missing raw dir for {symbol}"
                    assert os.path.isdir(norm_dir), f"Missing normalized dir for {symbol}"

                    raw_files = [f for f in os.listdir(raw_dir)
                                 if f.endswith(".parquet")]
                    norm_files = [f for f in os.listdir(norm_dir)
                                  if f.endswith(".parquet")]

                    assert len(raw_files) >= 1, f"No raw parquet for {symbol}"
                    assert len(norm_files) >= 1, f"No normalized parquet for {symbol}"

                # 3. SHA-256 sidecars exist
                for symbol in ["BTCUSDT", "ETHUSDT"]:
                    raw_dir = os.path.join(tmp_dir, "raw", symbol)
                    for fname in os.listdir(raw_dir):
                        if fname.endswith(".sha256"):
                            with open(os.path.join(raw_dir, fname)) as f:
                                checksum = f.read().strip()
                                assert len(checksum) == 64
                                break
                    else:
                        pytest.fail(f"No .sha256 sidecar found for {symbol}")

                # 4. Catalog entries updated
                bt_entries = catalog.query(symbol="BTCUSDT")
                eth_entries = catalog.query(symbol="ETHUSDT")
                assert len(bt_entries) >= 1
                assert len(eth_entries) >= 1

                # 5. Catalog persisted to disk
                catalog.save()
                assert os.path.exists(os.path.join(tmp_dir, "catalog.json"))

                # 6. Checksums on raw files verify
                for symbol in ["BTCUSDT", "ETHUSDT"]:
                    raw_dir = os.path.join(tmp_dir, "raw", symbol)
                    for fname in os.listdir(raw_dir):
                        if fname.endswith(".parquet"):
                            assert writer.verify_checksum(os.path.join(raw_dir, fname))

            finally:
                if os.path.exists(checkpoint_path):
                    os.unlink(checkpoint_path)
