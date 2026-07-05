"""
Tests for lib/market_data/storage.py

Uses temporary directories for Parquet write verification.
"""

import os
import tempfile

import pandas as pd
import pyarrow.parquet as pq
import pytest

from lib.market_data.storage import StorageWriter
from lib.market_data.contracts import KlineRecord
from lib.market_data.binance.funding_service import FundingRecord


def _make_kline(
    ts: int,
    symbol: str = "BTCUSDT",
    interval: str = "1h",
) -> KlineRecord:
    return KlineRecord(
        symbol=symbol,
        timestamp=ts,
        open=50000.0,
        high=51000.0,
        low=49000.0,
        close=50500.0,
        volume=100.0,
        quote_volume=5_000_000.0,
        trade_count=1000,
        taker_buy_volume=55.0,
        taker_buy_quote_volume=2_750_000.0,
        interval=interval,
        source="binance",
        is_closed=True,
    )


def _make_funding(
    ts: int,
    symbol: str = "BTCUSDT",
    rate: float = 0.0001,
) -> FundingRecord:
    return FundingRecord(
        symbol=symbol,
        timestamp=ts,
        funding_rate=rate,
    )


class TestStorageWriter:
    def test_write_raw_klines(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            writer = StorageWriter(base_dir=tmp_dir)
            records = [_make_kline(1000), _make_kline(3600000)]
            path = writer.write_raw_klines(records, "BTCUSDT", "1h", 1000, 7200000)

            assert os.path.exists(path)
            assert path.endswith(".parquet")
            assert "BTCUSDT" in path
            assert "raw" in path

            # Read back and verify
            table = pq.read_table(path)
            df = table.to_pandas()
            assert len(df) == 2
            assert df.iloc[0]["symbol"] == "BTCUSDT"

    def test_write_normalized_klines(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            writer = StorageWriter(base_dir=tmp_dir)
            records = [_make_kline(1000)]
            path = writer.write_normalized_klines(records, "BTCUSDT", "1h", 1000, 7200000)

            assert os.path.exists(path)
            assert "normalized" in path

    def test_write_funding(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            writer = StorageWriter(base_dir=tmp_dir)
            records = [_make_funding(1000), _make_funding(3600000)]
            path = writer.write_funding(records, "BTCUSDT", 1000, 7200000)

            assert os.path.exists(path)
            assert "funding" in path

            table = pq.read_table(path)
            df = table.to_pandas()
            assert len(df) == 2
            assert df.iloc[0]["funding_rate"] == 0.0001

    def test_checksum_sidecar(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            writer = StorageWriter(base_dir=tmp_dir)
            records = [_make_kline(1000)]
            path = writer.write_raw_klines(records, "BTCUSDT", "1h", 1000, 7200000)

            checksum_path = path + ".sha256"
            assert os.path.exists(checksum_path)

            with open(checksum_path, "r") as f:
                checksum = f.read().strip()
            assert len(checksum) == 64  # SHA-256 hex length
            assert all(c in "0123456789abcdef" for c in checksum)

    def test_verify_checksum_valid(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            writer = StorageWriter(base_dir=tmp_dir)
            records = [_make_kline(1000)]
            path = writer.write_raw_klines(records, "BTCUSDT", "1h", 1000, 7200000)

            assert writer.verify_checksum(path) is True

    def test_verify_checksum_missing_sidecar(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            writer = StorageWriter(base_dir=tmp_dir)
            records = [_make_kline(1000)]
            path = writer.write_raw_klines(records, "BTCUSDT", "1h", 1000, 7200000)

            # Remove sidecar
            os.unlink(path + ".sha256")
            assert writer.verify_checksum(path) is False

    def test_write_empty_records(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            writer = StorageWriter(base_dir=tmp_dir)
            path = writer.write_raw_klines([], "BTCUSDT", "1h", 1000, 2000)
            # Should return the path but not create the file
            assert path is not None

    def test_file_naming_convention(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            writer = StorageWriter(base_dir=tmp_dir)
            records = [_make_kline(1000)]
            path = writer.write_raw_klines(records, "BTCUSDT", "1h", 1000, 7200000)

            fname = os.path.basename(path)
            assert fname == "BTCUSDT_1h_1000_7200000.parquet"

    def test_file_naming_funding(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            writer = StorageWriter(base_dir=tmp_dir)
            records = [_make_funding(1000)]
            path = writer.write_funding(records, "BTCUSDT", 1000, 7200000)

            fname = os.path.basename(path)
            assert fname == "funding_BTCUSDT_1000_7200000.parquet"

    def test_directory_creation(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            writer = StorageWriter(base_dir=tmp_dir)
            records = [_make_kline(1000)]
            path = writer.write_raw_klines(records, "BTCUSDT", "1h", 1000, 7200000)

            # Directory should be created automatically
            assert os.path.exists(os.path.dirname(path))
