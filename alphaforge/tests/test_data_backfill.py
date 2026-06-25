"""Tests for alphaforge.data.backfill pipeline wrapper."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from unittest.mock import Mock

import pytest

from alphaforge.data.backfill import (
    AlphaForgeBackfillPipeline,
    BackfillConfig,
    BackfillError,
)
from alphaforge.data.integrity import validate_kline_parquet
from lib.market_data.binance.client import BinanceClient

SAMPLE_KLINE_RAW = [
    1_500_000_000_000,  # open time
    "50000.0",          # open
    "51000.0",          # high
    "49000.0",          # low
    "50500.0",          # close
    "100.0",            # volume
    1_500_000_000_999,  # close time
    "5000000.0",        # quote volume
    1000,               # trade count
    "55.0",             # taker buy volume
    "2750000.0",        # taker buy quote volume
    "0",                # ignore
]

SAMPLE_FUNDING_RAW = [[1_500_000_000_000, "0.0001"]]


def _mock_binance_client() -> Mock:
    """Return a mock BinanceClient that returns one kline per request."""
    client = Mock(spec=BinanceClient)
    client.get_klines.return_value = [SAMPLE_KLINE_RAW]
    client.get_funding_rate.return_value = SAMPLE_FUNDING_RAW
    return client


class TestBackfillConfig:
    def test_valid_config(self, tmp_path):
        config = BackfillConfig(
            symbols=("BTCUSDT",),
            intervals=("1h",),
            start_time_ms=1_500_000_000_000,
            end_time_ms=1_500_003_600_000,
            data_dir=str(tmp_path),
        )
        assert config.checkpoint_path == os.path.join(str(tmp_path), "backfill_checkpoint.json")
        assert config.catalog_path == os.path.join(str(tmp_path), "catalog.json")

    def test_invalid_range_raises(self, tmp_path):
        with pytest.raises(BackfillError):
            BackfillConfig(
                symbols=("BTCUSDT",),
                intervals=("1h",),
                start_time_ms=1_500_003_600_000,
                end_time_ms=1_500_000_000_000,
                data_dir=str(tmp_path),
            )

    def test_missing_symbols_raises(self, tmp_path):
        with pytest.raises(BackfillError):
            BackfillConfig(
                symbols=(),
                intervals=("1h",),
                start_time_ms=1_500_000_000_000,
                end_time_ms=1_500_003_600_000,
                data_dir=str(tmp_path),
            )


class TestAlphaForgeBackfillPipeline:
    def test_default_config_uses_last_30_days(self):
        config = AlphaForgeBackfillPipeline.default_config()
        assert config.symbols == ("BTCUSDT", "ETHUSDT", "SOLUSDT")
        assert config.intervals == ("1h", "4h", "1d")
        span_ms = config.end_time_ms - config.start_time_ms
        # Allow a little tolerance for test execution time
        assert 29 * 86_400_000 < span_ms <= 31 * 86_400_000

    def test_default_config_with_dates(self, tmp_path):
        start = datetime(2025, 1, 1, tzinfo=timezone.utc)
        end = datetime(2025, 1, 2, tzinfo=timezone.utc)
        config = AlphaForgeBackfillPipeline.default_config(
            start=start,
            end=end,
            symbols=["BTCUSDT"],
            intervals=["1h"],
            data_dir=str(tmp_path),
        )
        assert config.start_time_ms == int(start.timestamp() * 1_000)
        assert config.end_time_ms == int(end.timestamp() * 1_000)
        assert config.symbols == ("BTCUSDT",)

    def test_run_with_mock_client(self, tmp_path):
        client = _mock_binance_client()
        pipeline = AlphaForgeBackfillPipeline(client=client)
        config = AlphaForgeBackfillPipeline.default_config(
            start=datetime(2025, 1, 1, tzinfo=timezone.utc),
            end=datetime(2025, 1, 1, 1, tzinfo=timezone.utc),
            symbols=["BTCUSDT"],
            intervals=["1h"],
            data_dir=str(tmp_path),
        )

        result = pipeline.run(config)

        assert result.ok is True
        assert result.stats["total_symbols"] == 1
        assert result.stats["total_records"] >= 1
        assert result.stats["errors"] == []
        assert len(result.integrity_reports) == 1
        assert result.integrity_reports[0].ok is True
        assert os.path.exists(result.integrity_reports[0].path)

    def test_run_reports_integrity_failure(self, tmp_path):
        """If the stored file has a gap, the pipeline reports it."""
        gap_kline = list(SAMPLE_KLINE_RAW)
        gap_kline[0] = 1_500_007_200_000  # skip one hour
        client = Mock(spec=BinanceClient)
        client.get_klines.return_value = [SAMPLE_KLINE_RAW, gap_kline]
        client.get_funding_rate.return_value = SAMPLE_FUNDING_RAW

        pipeline = AlphaForgeBackfillPipeline(client=client)
        config = AlphaForgeBackfillPipeline.default_config(
            start=datetime(2025, 1, 1, tzinfo=timezone.utc),
            end=datetime(2025, 1, 1, 2, tzinfo=timezone.utc),
            symbols=["BTCUSDT"],
            intervals=["1h"],
            data_dir=str(tmp_path),
        )

        result = pipeline.run(config)

        assert result.ok is False
        assert len(result.integrity_reports) == 1
        assert result.integrity_reports[0].ok is False
        assert any("gap" in w.lower() for w in result.integrity_reports[0].warnings)

    def test_run_respects_checkpoint(self, tmp_path):
        client = _mock_binance_client()
        pipeline = AlphaForgeBackfillPipeline(client=client)
        config = AlphaForgeBackfillPipeline.default_config(
            start=datetime(2025, 1, 1, tzinfo=timezone.utc),
            end=datetime(2025, 1, 1, 1, tzinfo=timezone.utc),
            symbols=["BTCUSDT"],
            intervals=["1h"],
            data_dir=str(tmp_path),
        )

        result1 = pipeline.run(config)
        assert result1.stats["total_records"] >= 1

        # Second run with same config should skip already-completed range
        result2 = pipeline.run(config)
        assert result2.stats["total_records"] == 0


class TestValidateCatalogIntegration:
    def test_validate_catalog_after_run(self, tmp_path):
        client = _mock_binance_client()
        pipeline = AlphaForgeBackfillPipeline(client=client)
        config = AlphaForgeBackfillPipeline.default_config(
            start=datetime(2025, 1, 1, tzinfo=timezone.utc),
            end=datetime(2025, 1, 1, 1, tzinfo=timezone.utc),
            symbols=["BTCUSDT"],
            intervals=["1h"],
            data_dir=str(tmp_path),
        )

        result = pipeline.run(config)
        entry = result.integrity_reports[0]
        direct = validate_kline_parquet(
            entry.path, "1h", expected_start=config.start_time_ms, expected_end=config.end_time_ms
        )
        assert direct.ok is True
