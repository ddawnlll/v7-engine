"""Tests for alphaforge.data.integrity validation."""

from __future__ import annotations

import os

import pytest

from alphaforge.data.integrity import validate_kline_parquet
from lib.market_data.contracts import KlineRecord
from lib.market_data.storage import StorageWriter


def _kline(ts: int, symbol: str = "BTCUSDT", interval: str = "1h") -> KlineRecord:
    return KlineRecord(
        symbol=symbol,
        timestamp=ts,
        open=50_000.0,
        high=51_000.0,
        low=49_000.0,
        close=50_500.0,
        volume=100.0,
        quote_volume=5_000_000.0,
        trade_count=1_000,
        taker_buy_volume=55.0,
        taker_buy_quote_volume=2_750_000.0,
        interval=interval,
        source="binance",
        is_closed=True,
    )


class TestValidateKlineParquet:
    def test_valid_file_passes(self, tmp_path):
        writer = StorageWriter(base_dir=str(tmp_path))
        records = [_kline(1_500_000_000_000), _kline(1_500_003_600_000)]
        path = writer.write_raw_klines(
            records, "BTCUSDT", "1h", 1_500_000_000_000, 1_500_007_200_000
        )

        report = validate_kline_parquet(
            path, "1h", expected_start=1_500_000_000_000, expected_end=1_500_007_200_000
        )

        assert report.ok is True
        assert report.checksum_ok is True
        assert report.sorted_ok is True
        assert report.no_duplicates is True
        assert report.no_gaps is True
        assert report.row_count == 2
        assert report.warnings == []

    def test_missing_file_fails(self, tmp_path):
        path = str(tmp_path / "missing.parquet")
        report = validate_kline_parquet(path, "1h")
        assert report.ok is False
        assert any("missing" in w.lower() for w in report.warnings)

    def test_missing_checksum_fails(self, tmp_path):
        writer = StorageWriter(base_dir=str(tmp_path))
        records = [_kline(1_500_000_000_000)]
        path = writer.write_raw_klines(
            records, "BTCUSDT", "1h", 1_500_000_000_000, 1_500_003_600_000
        )
        os.unlink(path + ".sha256")

        report = validate_kline_parquet(path, "1h")
        assert report.ok is False
        assert report.checksum_ok is False
        assert any("checksum" in w.lower() for w in report.warnings)

    def test_gap_detection(self, tmp_path):
        writer = StorageWriter(base_dir=str(tmp_path))
        # Skip one hour between records
        records = [_kline(1_500_000_000_000), _kline(1_500_007_200_000)]
        path = writer.write_raw_klines(
            records, "BTCUSDT", "1h", 1_500_000_000_000, 1_500_010_800_000
        )

        report = validate_kline_parquet(path, "1h")
        assert report.ok is False
        assert report.no_gaps is False
        assert any("gap" in w.lower() for w in report.warnings)

    def test_duplicate_detection(self, tmp_path):
        writer = StorageWriter(base_dir=str(tmp_path))
        records = [_kline(1_500_000_000_000), _kline(1_500_000_000_000)]
        path = writer.write_raw_klines(
            records, "BTCUSDT", "1h", 1_500_000_000_000, 1_500_003_600_000
        )

        report = validate_kline_parquet(path, "1h")
        assert report.ok is False
        assert report.no_duplicates is False
        assert any("duplicate" in w.lower() for w in report.warnings)

    def test_unsorted_detection(self, tmp_path):
        writer = StorageWriter(base_dir=str(tmp_path))
        records = [_kline(1_500_003_600_000), _kline(1_500_000_000_000)]
        path = writer.write_raw_klines(
            records, "BTCUSDT", "1h", 1_500_000_000_000, 1_500_007_200_000
        )

        report = validate_kline_parquet(path, "1h")
        assert report.ok is False
        assert report.sorted_ok is False
        assert any("sort" in w.lower() for w in report.warnings)

    def test_expected_count_mismatch(self, tmp_path):
        writer = StorageWriter(base_dir=str(tmp_path))
        records = [_kline(1_500_000_000_000)]
        path = writer.write_raw_klines(
            records, "BTCUSDT", "1h", 1_500_000_000_000, 1_500_007_200_000
        )

        report = validate_kline_parquet(
            path, "1h", expected_start=1_500_000_000_000, expected_end=1_500_007_200_000
        )
        assert report.ok is True  # structural checks still pass
        assert any("expected 2 records" in w.lower() for w in report.warnings)
