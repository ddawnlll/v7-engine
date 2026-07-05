"""Test suite for AlphaForge data backfill pipeline.

Covers:
  - BackfillConfig validation (construction errors)
  - create_backfill_config factory
  - Dry-run pipeline
  - Full pipeline with mocked Binance dependencies
  - Integrity validation
  - Error handling
  - Domain boundary (no imports from simulation/v7/runtime/interface)
  - Binance Vision (data.binance.vision) download
  - SYMBOLS_20 constant
  - CSV parsing and Parquet conversion
  - Checksum verification
"""

from __future__ import annotations

import hashlib
import os
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import Mock, patch

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from alphaforge.data.backfill import (
    BackfillConfig,
    BackfillError,
    BackfillPipeline,
    BackfillResult,
    BinanceVisionConfig,
    SYMBOLS_20,
    create_backfill_config,
    create_binance_vision_config,
    create_pipeline,
    download_from_binance_vision,
)
from alphaforge.data.backfill import (
    _fetch_checksum,
    _file_sha256,
    _parse_klines_csv,
)
from lib.market_data.binance.client import BinanceClient
from lib.market_data.binance.klines_service import KlinesService
from lib.market_data.binance.funding_service import FundingService
from lib.market_data.binance.rate_limiter import BinanceRateLimiter
from lib.market_data.binance.checkpoint import BackfillCheckpoint
from lib.market_data.storage import StorageWriter
from lib.market_data.catalog import DataCatalog

# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------

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

VALID_CONFIG = dict(
    symbols=["BTCUSDT"],
    intervals=["1h"],
    start_time=1_500_000_000_000,
    end_time=1_500_003_600_000,
    mode="SWING",
    primary_interval="4h",
)


# ---------------------------------------------------------------------------
# BackfillConfig validation
# ---------------------------------------------------------------------------


class TestBackfillConfigValidation:
    """Test that BackfillConfig rejects invalid configurations."""

    def test_valid_config_constructs(self):
        """A valid config should construct without error."""
        config = create_backfill_config(**VALID_CONFIG)
        assert config.mode == "SWING"
        assert config.symbols == ("BTCUSDT",)
        assert config.start_time == 1_500_000_000_000
        assert config.end_time == 1_500_003_600_000

    def test_empty_symbols_raises(self):
        """Empty symbols list should raise BackfillError."""
        with pytest.raises(BackfillError, match="symbols"):
            create_backfill_config(
                symbols=[], intervals=["1h"],
                start_time=1000, end_time=2000,
                mode="SWING", primary_interval="4h",
            )

    def test_empty_intervals_raises(self):
        """Empty intervals list should raise BackfillError."""
        with pytest.raises(BackfillError, match="intervals"):
            create_backfill_config(
                symbols=["BTCUSDT"], intervals=[],
                start_time=1000, end_time=2000,
                mode="SWING", primary_interval="4h",
            )

    def test_inverted_time_range_raises(self):
        """start_time >= end_time should raise BackfillError."""
        with pytest.raises(BackfillError, match="start_time"):
            create_backfill_config(
                symbols=["BTCUSDT"], intervals=["1h"],
                start_time=2000, end_time=1000,
                mode="SWING", primary_interval="4h",
            )

    def test_same_start_end_raises(self):
        """start_time == end_time should raise BackfillError."""
        with pytest.raises(BackfillError, match="start_time"):
            create_backfill_config(
                symbols=["BTCUSDT"], intervals=["1h"],
                start_time=1000, end_time=1000,
                mode="SWING", primary_interval="4h",
            )

    def test_invalid_mode_raises(self):
        """Unrecognized mode should raise BackfillError."""
        with pytest.raises(BackfillError, match="mode"):
            create_backfill_config(
                symbols=["BTCUSDT"], intervals=["1h"],
                start_time=1000, end_time=2000,
                mode="INVALID_MODE", primary_interval="4h",
            )

    def test_invalid_primary_interval_raises(self):
        """Unrecognized primary_interval should raise BackfillError."""
        with pytest.raises(BackfillError, match="primary_interval"):
            create_backfill_config(
                symbols=["BTCUSDT"], intervals=["1h"],
                start_time=1000, end_time=2000,
                mode="SWING", primary_interval="9h",
            )

    def test_invalid_batch_size_too_low_raises(self):
        """batch_size < 1 should raise BackfillError."""
        with pytest.raises(BackfillError, match="batch_size"):
            create_backfill_config(
                symbols=["BTCUSDT"], intervals=["1h"],
                start_time=1000, end_time=2000,
                mode="SWING", primary_interval="4h",
                batch_size=0,
            )

    def test_invalid_batch_size_too_high_raises(self):
        """batch_size > 100000 should raise BackfillError."""
        with pytest.raises(BackfillError, match="batch_size"):
            create_backfill_config(
                symbols=["BTCUSDT"], intervals=["1h"],
                start_time=1000, end_time=2000,
                mode="SWING", primary_interval="4h",
                batch_size=100_001,
            )

    def test_symbols_uppercased(self):
        """Symbol names should be uppercased."""
        config = create_backfill_config(
            symbols=["btcusdt", "ethusdt"], intervals=["1h"],
            start_time=1000, end_time=2000,
            mode="SWING", primary_interval="4h",
        )
        assert config.symbols == ("BTCUSDT", "ETHUSDT")

    def test_mode_uppercased(self):
        """Mode should be uppercased."""
        config = create_backfill_config(
            symbols=["BTCUSDT"], intervals=["1h"],
            start_time=1000, end_time=2000,
            mode="swing", primary_interval="4h",
        )
        assert config.mode == "SWING"

    def test_config_frozen(self):
        """BackfillConfig should be frozen (immutable)."""
        config = create_backfill_config(**VALID_CONFIG)
        with pytest.raises(Exception):  # dataclasses.FrozenInstanceError or AttributeError
            config.mode = "SCALP"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Dry-run
# ---------------------------------------------------------------------------


class TestBackfillPipelineDryRun:
    """Test dry-run pipeline mode."""

    def test_dry_run_no_data_fetched(self):
        """Dry-run should not fetch data."""
        config = create_backfill_config(**VALID_CONFIG)

        # Create a pipeline with mock services (should never be called)
        mock_client = Mock(spec=BinanceClient)

        with tempfile.TemporaryDirectory() as tmp_dir:
            writer = StorageWriter(base_dir=tmp_dir)
            catalog = DataCatalog(catalog_path=f"{tmp_dir}/catalog.json")
            limiter = BinanceRateLimiter()

            with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as cp_file:
                checkpoint = BackfillCheckpoint(file_path=cp_file.name)

            try:
                pipeline = BackfillPipeline(
                    klines_service=KlinesService(mock_client),
                    funding_service=FundingService(mock_client),
                    storage_writer=writer,
                    catalog=catalog,
                    rate_limiter=limiter,
                    checkpoint=checkpoint,
                )

                result = pipeline.run_dry(config)

                assert result.stats["total_records"] == 0
                assert result.manifest is None
                assert result.integrity_passed is True
                assert result.integrity_details["dry_run"] is True

                # Mock client should not have been called
                mock_client.get_klines.assert_not_called()
            finally:
                if os.path.exists(cp_file.name):
                    os.unlink(cp_file.name)


# ---------------------------------------------------------------------------
# Full pipeline with mocked dependencies
# ---------------------------------------------------------------------------


class TestBackfillPipeline:
    """Test full pipeline with mocked Binance dependencies."""

    def test_full_pipeline_single_symbol(self):
        """Run a full pipeline with mocked client and verify result."""
        mock_client = Mock(spec=BinanceClient)
        mock_client.get_klines.return_value = [SAMPLE_KLINE_RAW]
        mock_client.get_funding_rate.return_value = SAMPLE_FUNDING_RAW

        config = create_backfill_config(**VALID_CONFIG)

        with tempfile.TemporaryDirectory() as tmp_dir:
            writer = StorageWriter(base_dir=tmp_dir)
            catalog = DataCatalog(catalog_path=f"{tmp_dir}/catalog.json")
            limiter = BinanceRateLimiter()

            with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as cp_file:
                checkpoint = BackfillCheckpoint(file_path=cp_file.name)

            try:
                pipeline = BackfillPipeline(
                    klines_service=KlinesService(mock_client),
                    funding_service=FundingService(mock_client),
                    storage_writer=writer,
                    catalog=catalog,
                    rate_limiter=limiter,
                    checkpoint=checkpoint,
                )

                result = pipeline.run(config)

                # Verify stats
                assert result.stats["total_symbols"] == 1
                assert result.stats["total_records"] == 1
                assert result.stats["errors"] == []

                # Verify result is frozen
                assert isinstance(result, BackfillResult)
                assert result.config.mode == "SWING"

                # Verify files were written
                raw_dir = os.path.join(tmp_dir, "raw", "BTCUSDT")
                norm_dir = os.path.join(tmp_dir, "normalized", "BTCUSDT")
                assert os.path.isdir(raw_dir), "Missing raw dir"
                assert os.path.isdir(norm_dir), "Missing normalized dir"

                # Verify catalog updated
                entries = catalog.query(symbol="BTCUSDT")
                assert len(entries) >= 1

            finally:
                if os.path.exists(cp_file.name):
                    os.unlink(cp_file.name)

    def test_full_pipeline_multiple_symbols(self):
        """Run pipeline across multiple symbols."""
        mock_client = Mock(spec=BinanceClient)
        mock_client.get_klines.return_value = [SAMPLE_KLINE_RAW]
        mock_client.get_funding_rate.return_value = SAMPLE_FUNDING_RAW

        config = create_backfill_config(
            symbols=["BTCUSDT", "ETHUSDT"],
            intervals=["1h"],
            start_time=1_500_000_000_000,
            end_time=1_500_003_600_000,
            mode="SWING",
            primary_interval="4h",
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            writer = StorageWriter(base_dir=tmp_dir)
            catalog = DataCatalog(catalog_path=f"{tmp_dir}/catalog.json")
            limiter = BinanceRateLimiter()

            with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as cp_file:
                checkpoint = BackfillCheckpoint(file_path=cp_file.name)

            try:
                pipeline = BackfillPipeline(
                    klines_service=KlinesService(mock_client),
                    funding_service=FundingService(mock_client),
                    storage_writer=writer,
                    catalog=catalog,
                    rate_limiter=limiter,
                    checkpoint=checkpoint,
                )

                result = pipeline.run(config)

                assert result.stats["total_symbols"] == 2
                assert result.stats["total_records"] == 2  # 1 per symbol
                assert result.stats["errors"] == []

                # Both symbols should have data
                for sym in ["BTCUSDT", "ETHUSDT"]:
                    raw_dir = os.path.join(tmp_dir, "raw", sym)
                    assert os.path.isdir(raw_dir), f"Missing raw dir for {sym}"
            finally:
                if os.path.exists(cp_file.name):
                    os.unlink(cp_file.name)

    def test_pipeline_skips_completed(self):
        """Pipeline should skip symbols/intervals already completed."""
        mock_client = Mock(spec=BinanceClient)
        mock_client.get_klines.return_value = [SAMPLE_KLINE_RAW]
        mock_client.get_funding_rate.return_value = SAMPLE_FUNDING_RAW

        config = create_backfill_config(**VALID_CONFIG)

        with tempfile.TemporaryDirectory() as tmp_dir:
            writer = StorageWriter(base_dir=tmp_dir)
            catalog = DataCatalog(catalog_path=f"{tmp_dir}/catalog.json")
            limiter = BinanceRateLimiter()

            with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as cp_file:
                checkpoint = BackfillCheckpoint(file_path=cp_file.name)

            try:
                # Mark as already completed
                checkpoint.save(
                    "BTCUSDT", "1h",
                    config.start_time, config.end_time,
                    [],
                )

                pipeline = BackfillPipeline(
                    klines_service=KlinesService(mock_client),
                    funding_service=FundingService(mock_client),
                    storage_writer=writer,
                    catalog=catalog,
                    rate_limiter=limiter,
                    checkpoint=checkpoint,
                )

                result = pipeline.run(config)

                # Should skip — 0 records fetched
                assert result.stats["total_records"] == 0
            finally:
                if os.path.exists(cp_file.name):
                    os.unlink(cp_file.name)

    def test_pipeline_handles_client_error(self):
        """Pipeline should survive client errors and report them."""
        mock_client = Mock(spec=BinanceClient)
        mock_client.get_klines.side_effect = Exception("API error")
        mock_client.get_funding_rate.return_value = SAMPLE_FUNDING_RAW

        config = create_backfill_config(
            symbols=["BTCUSDT", "ETHUSDT"],
            intervals=["1h"],
            start_time=1_500_000_000_000,
            end_time=1_500_003_600_000,
            mode="SWING",
            primary_interval="4h",
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            writer = StorageWriter(base_dir=tmp_dir)
            catalog = DataCatalog(catalog_path=f"{tmp_dir}/catalog.json")
            limiter = BinanceRateLimiter()

            with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as cp_file:
                checkpoint = BackfillCheckpoint(file_path=cp_file.name)

            try:
                pipeline = BackfillPipeline(
                    klines_service=KlinesService(mock_client),
                    funding_service=FundingService(mock_client),
                    storage_writer=writer,
                    catalog=catalog,
                    rate_limiter=limiter,
                    checkpoint=checkpoint,
                )

                result = pipeline.run(config)

                assert result.stats["total_records"] == 0
                assert len(result.stats["errors"]) == 2
                assert all("API error" in e for e in result.stats["errors"])
                assert result.integrity_passed is False
            finally:
                if os.path.exists(cp_file.name):
                    os.unlink(cp_file.name)

    def test_pipeline_updates_catalog(self):
        """Catalog should be populated with backfill entries."""
        mock_client = Mock(spec=BinanceClient)
        mock_client.get_klines.return_value = [SAMPLE_KLINE_RAW]
        mock_client.get_funding_rate.return_value = SAMPLE_FUNDING_RAW

        config = create_backfill_config(**VALID_CONFIG)

        with tempfile.TemporaryDirectory() as tmp_dir:
            writer = StorageWriter(base_dir=tmp_dir)
            catalog = DataCatalog(catalog_path=f"{tmp_dir}/catalog.json")
            limiter = BinanceRateLimiter()

            with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as cp_file:
                checkpoint = BackfillCheckpoint(file_path=cp_file.name)

            try:
                pipeline = BackfillPipeline(
                    klines_service=KlinesService(mock_client),
                    funding_service=FundingService(mock_client),
                    storage_writer=writer,
                    catalog=catalog,
                    rate_limiter=limiter,
                    checkpoint=checkpoint,
                )

                pipeline.run(config)

                entries = catalog.query()
                assert len(entries) == 1
                assert entries[0]["symbol"] == "BTCUSDT"
                assert entries[0]["interval"] == "1h"
                assert entries[0]["row_count"] == 1
            finally:
                if os.path.exists(cp_file.name):
                    os.unlink(cp_file.name)

    def test_pipeline_writes_raw_and_normalized(self):
        """Both raw and normalized parquet files should be written."""
        mock_client = Mock(spec=BinanceClient)
        mock_client.get_klines.return_value = [SAMPLE_KLINE_RAW]
        mock_client.get_funding_rate.return_value = SAMPLE_FUNDING_RAW

        config = create_backfill_config(**VALID_CONFIG)

        with tempfile.TemporaryDirectory() as tmp_dir:
            writer = StorageWriter(base_dir=tmp_dir)
            catalog = DataCatalog(catalog_path=f"{tmp_dir}/catalog.json")
            limiter = BinanceRateLimiter()

            with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as cp_file:
                checkpoint = BackfillCheckpoint(file_path=cp_file.name)

            try:
                pipeline = BackfillPipeline(
                    klines_service=KlinesService(mock_client),
                    funding_service=FundingService(mock_client),
                    storage_writer=writer,
                    catalog=catalog,
                    rate_limiter=limiter,
                    checkpoint=checkpoint,
                )

                result = pipeline.run(config)
                assert result.stats["total_records"] > 0

                # Check files exist
                raw_dir = os.path.join(tmp_dir, "raw", "BTCUSDT")
                norm_dir = os.path.join(tmp_dir, "normalized", "BTCUSDT")

                raw_files = [f for f in os.listdir(raw_dir) if f.endswith(".parquet")]
                norm_files = [f for f in os.listdir(norm_dir) if f.endswith(".parquet")]
                assert len(raw_files) >= 1
                assert len(norm_files) >= 1
            finally:
                if os.path.exists(cp_file.name):
                    os.unlink(cp_file.name)


# ---------------------------------------------------------------------------
# Integrity validation
# ---------------------------------------------------------------------------


class TestBackfillIntegrity:
    """Test data integrity validation in the pipeline."""

    def test_successful_backfill_passes_integrity(self):
        """A successful backfill should pass integrity checks."""
        mock_client = Mock(spec=BinanceClient)
        mock_client.get_klines.return_value = [SAMPLE_KLINE_RAW]
        mock_client.get_funding_rate.return_value = SAMPLE_FUNDING_RAW

        config = create_backfill_config(**VALID_CONFIG)

        with tempfile.TemporaryDirectory() as tmp_dir:
            writer = StorageWriter(base_dir=tmp_dir)
            catalog = DataCatalog(catalog_path=f"{tmp_dir}/catalog.json")
            limiter = BinanceRateLimiter()

            with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as cp_file:
                checkpoint = BackfillCheckpoint(file_path=cp_file.name)

            try:
                pipeline = BackfillPipeline(
                    klines_service=KlinesService(mock_client),
                    funding_service=FundingService(mock_client),
                    storage_writer=writer,
                    catalog=catalog,
                    rate_limiter=limiter,
                    checkpoint=checkpoint,
                )

                result = pipeline.run(config)

                # Integrity should pass for successful backfill
                assert result.stats["errors"] == []
                assert result.stats["total_records"] > 0
                # Integrity passes when records > 0 and no errors
                assert result.integrity_passed is True
                assert "total_records" in result.integrity_details
            finally:
                if os.path.exists(cp_file.name):
                    os.unlink(cp_file.name)

    def test_errors_prevent_integrity_pass(self):
        """When errors occur, integrity should not pass."""
        mock_client = Mock(spec=BinanceClient)
        mock_client.get_klines.side_effect = Exception("fetch failure")
        mock_client.get_funding_rate.return_value = SAMPLE_FUNDING_RAW

        config = create_backfill_config(**VALID_CONFIG)

        with tempfile.TemporaryDirectory() as tmp_dir:
            writer = StorageWriter(base_dir=tmp_dir)
            catalog = DataCatalog(catalog_path=f"{tmp_dir}/catalog.json")
            limiter = BinanceRateLimiter()

            with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as cp_file:
                checkpoint = BackfillCheckpoint(file_path=cp_file.name)

            try:
                pipeline = BackfillPipeline(
                    klines_service=KlinesService(mock_client),
                    funding_service=FundingService(mock_client),
                    storage_writer=writer,
                    catalog=catalog,
                    rate_limiter=limiter,
                    checkpoint=checkpoint,
                )

                result = pipeline.run(config)

                assert len(result.stats["errors"]) > 0
                assert result.integrity_passed is False
            finally:
                if os.path.exists(cp_file.name):
                    os.unlink(cp_file.name)

    def test_no_records_fails_integrity(self):
        """Zero records should fail integrity (nothing was fetched)."""
        mock_client = Mock(spec=BinanceClient)
        mock_client.get_klines.return_value = [SAMPLE_KLINE_RAW]
        mock_client.get_funding_rate.return_value = SAMPLE_FUNDING_RAW

        config = create_backfill_config(**VALID_CONFIG)

        with tempfile.TemporaryDirectory() as tmp_dir:
            writer = StorageWriter(base_dir=tmp_dir)
            catalog = DataCatalog(catalog_path=f"{tmp_dir}/catalog.json")
            limiter = BinanceRateLimiter()

            with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as cp_file:
                checkpoint = BackfillCheckpoint(file_path=cp_file.name)

            try:
                # Mark completed so 0 records are fetched
                checkpoint.save(
                    "BTCUSDT", "1h",
                    config.start_time, config.end_time,
                    [],
                )

                pipeline = BackfillPipeline(
                    klines_service=KlinesService(mock_client),
                    funding_service=FundingService(mock_client),
                    storage_writer=writer,
                    catalog=catalog,
                    rate_limiter=limiter,
                    checkpoint=checkpoint,
                )

                result = pipeline.run(config)
                assert result.stats["total_records"] == 0
                assert result.integrity_passed is False
            finally:
                if os.path.exists(cp_file.name):
                    os.unlink(cp_file.name)


# ---------------------------------------------------------------------------
# Factory helper
# ---------------------------------------------------------------------------


class TestCreatePipeline:
    """Test the create_pipeline factory function."""

    def test_create_pipeline_with_defaults(self):
        """Should create a pipeline with default rate limiter and checkpoint."""
        mock_client = Mock(spec=BinanceClient)

        with tempfile.TemporaryDirectory() as tmp_dir:
            writer = StorageWriter(base_dir=tmp_dir)
            catalog = DataCatalog(catalog_path=f"{tmp_dir}/catalog.json")

            pipeline = create_pipeline(
                klines_service=KlinesService(mock_client),
                funding_service=FundingService(mock_client),
                storage_writer=writer,
                catalog=catalog,
            )

            assert isinstance(pipeline, BackfillPipeline)

            # Should be able to run dry with defaults
            config = create_backfill_config(**VALID_CONFIG)
            result = pipeline.run_dry(config)
            assert result.integrity_passed is True

    def test_create_pipeline_explicit_checkpoint(self):
        """Should accept explicit rate limiter and checkpoint."""
        mock_client = Mock(spec=BinanceClient)
        limiter = BinanceRateLimiter()

        with tempfile.TemporaryDirectory() as tmp_dir:
            writer = StorageWriter(base_dir=tmp_dir)
            catalog = DataCatalog(catalog_path=f"{tmp_dir}/catalog.json")

            with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as cp_file:
                checkpoint = BackfillCheckpoint(file_path=cp_file.name)

            try:
                pipeline = create_pipeline(
                    klines_service=KlinesService(mock_client),
                    funding_service=FundingService(mock_client),
                    storage_writer=writer,
                    catalog=catalog,
                    rate_limiter=limiter,
                    checkpoint=checkpoint,
                )

                assert isinstance(pipeline, BackfillPipeline)
            finally:
                if os.path.exists(cp_file.name):
                    os.unlink(cp_file.name)


# ---------------------------------------------------------------------------
# Domain boundary
# ---------------------------------------------------------------------------


class TestDomainBoundary:
    """Verify alphaforge backfill respects domain boundaries.

    AlphaForge must NOT import from simulation/, v7/, runtime/, or interface/.
    """

    def test_no_forbidden_imports_in_backfill_module(self):
        """Backfill module must not import forbidden domains."""
        import inspect
        import sys

        forbidden_prefixes = ("simulation.", "v7.", "runtime.", "interface.")

        # Check the module's own imports
        import alphaforge.data.backfill as mod

        for name, obj in inspect.getmembers(mod):
            if inspect.ismodule(obj) and hasattr(obj, "__name__"):
                mod_name = obj.__name__
                for prefix in forbidden_prefixes:
                    assert not mod_name.startswith(prefix), (
                        f"Forbidden import {mod_name} in alphaforge.data.backfill"
                    )

    def test_no_ml_imports_in_backfill_module(self):
        """Backfill module must not import ML libraries directly."""
        import inspect

        forbidden_ml = ("xgboost", "sklearn", "torch", "tensorflow", "lightgbm")

        import alphaforge.data.backfill as mod

        for name, obj in inspect.getmembers(mod):
            if inspect.ismodule(obj) and hasattr(obj, "__name__"):
                mod_name = obj.__name__
                for ml in forbidden_ml:
                    assert not mod_name.startswith(ml), (
                        f"ML import {mod_name} in alphaforge.data.backfill"
                    )


# ---------------------------------------------------------------------------
# Binance Vision — SYMBOLS_20
# ---------------------------------------------------------------------------


class TestBinanceVisionSymbols:
    """Test the SYMBOLS_20 constant."""

    def test_symbols_20_has_20_symbols(self):
        """SYMBOLS_20 should contain exactly 20 symbols."""
        assert len(SYMBOLS_20) == 20

    def test_symbols_20_all_uppercase(self):
        """All SYMBOLS_20 should be uppercase."""
        for sym in SYMBOLS_20:
            assert sym == sym.upper(), f"{sym} is not uppercase"

    def test_symbols_20_all_usdt(self):
        """All SYMBOLS_20 should end with USDT."""
        for sym in SYMBOLS_20:
            assert sym.endswith("USDT"), f"{sym} does not end with USDT"

    def test_symbols_20_contains_btc(self):
        """BTCUSDT should be in SYMBOLS_20."""
        assert "BTCUSDT" in SYMBOLS_20

    def test_symbols_20_contains_eth(self):
        """ETHUSDT should be in SYMBOLS_20."""
        assert "ETHUSDT" in SYMBOLS_20

    def test_symbols_20_no_duplicates(self):
        """SYMBOLS_20 should have no duplicate symbols."""
        assert len(SYMBOLS_20) == len(set(SYMBOLS_20))


# ---------------------------------------------------------------------------
# Binance Vision — BinanceVisionConfig
# ---------------------------------------------------------------------------


class TestBinanceVisionConfig:
    """Test BinanceVisionConfig validation."""

    def test_valid_config_constructs(self):
        """A valid config should construct without error."""
        config = create_binance_vision_config(
            symbols=["BTCUSDT"],
            intervals=["1h"],
            output_dir="/tmp/vision",
            start_year=2023,
            start_month=1,
            end_year=2023,
            end_month=3,
        )
        assert config.symbols == ("BTCUSDT",)
        assert config.intervals == ("1h",)
        assert config.start_year == 2023
        assert config.end_year == 2023

    def test_empty_symbols_raises(self):
        """Empty symbols should raise BackfillError."""
        with pytest.raises(BackfillError, match="symbols"):
            create_binance_vision_config(
                symbols=[], intervals=["1h"],
                output_dir="/tmp/vision",
            )

    def test_empty_intervals_raises(self):
        """Empty intervals should raise BackfillError."""
        with pytest.raises(BackfillError, match="intervals"):
            create_binance_vision_config(
                symbols=["BTCUSDT"], intervals=[],
                output_dir="/tmp/vision",
            )

    def test_invalid_interval_raises(self):
        """Unrecognized interval should raise BackfillError."""
        with pytest.raises(BackfillError, match="interval"):
            create_binance_vision_config(
                symbols=["BTCUSDT"], intervals=["4h"],
                output_dir="/tmp/vision",
            )

    def test_start_year_before_2022_raises(self):
        """start_year < 2022 should raise BackfillError."""
        with pytest.raises(BackfillError, match="start_year"):
            create_binance_vision_config(
                symbols=["BTCUSDT"], intervals=["1h"],
                output_dir="/tmp/vision",
                start_year=2021,
            )

    def test_inverted_date_range_raises(self):
        """start > end should raise BackfillError."""
        with pytest.raises(BackfillError, match="start.*must be <= end"):
            create_binance_vision_config(
                symbols=["BTCUSDT"], intervals=["1h"],
                output_dir="/tmp/vision",
                start_year=2024, start_month=6,
                end_year=2024, end_month=5,
            )

    def test_symbols_uppercased(self):
        """Symbols should be uppercased."""
        config = create_binance_vision_config(
            symbols=["btcusdt", "ethusdt"],
            intervals=["1h"],
            output_dir="/tmp/vision",
        )
        assert config.symbols == ("BTCUSDT", "ETHUSDT")

    def test_default_end_date_is_current(self):
        """Default end_year/end_month should be current date."""
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        config = create_binance_vision_config(
            symbols=["BTCUSDT"],
            intervals=["1h"],
            output_dir="/tmp/vision",
        )
        assert config.end_year == now.year
        assert config.end_month == now.month

    def test_config_frozen(self):
        """BinanceVisionConfig should be frozen (immutable)."""
        config = create_binance_vision_config(
            symbols=["BTCUSDT"],
            intervals=["1h"],
            output_dir="/tmp/vision",
        )
        with pytest.raises(Exception):
            config.symbols = ("ETHUSDT",)  # type: ignore[misc]

    def test_invalid_month_raises(self):
        """Month < 1 or > 12 should raise BackfillError."""
        with pytest.raises(BackfillError):
            create_binance_vision_config(
                symbols=["BTCUSDT"], intervals=["1h"],
                output_dir="/tmp/vision",
                start_year=2023, start_month=13,
            )


# ---------------------------------------------------------------------------
# Binance Vision — internal helpers
# ---------------------------------------------------------------------------


class TestBinanceVisionHelpers:
    """Test internal helper functions for Binance Vision download."""

    def test_parse_klines_csv_with_header(self):
        """CSV with header row should parse correctly."""
        csv_text = (
            "open_time,open,high,low,close,volume,close_time,quote_volume,count,"
            "taker_buy_volume,taker_buy_quote_volume,ignore\n"
            "1700000000000,50000.0,51000.0,49000.0,50500.0,100.0,1700003600000,5000000.0,"
            "1000,55.0,2750000.0,0\n"
        )
        table = _parse_klines_csv(csv_text, "1h")
        assert len(table) == 1
        assert table.column("open_time")[0].as_py() == 1700000000000
        assert table.column("close")[0].as_py() == 50500.0
        assert table.column("interval")[0].as_py() == "1h"

    def test_parse_klines_csv_no_header(self):
        """CSV without header should parse correctly."""
        csv_text = (
            "1700000000000,50000.0,51000.0,49000.0,50500.0,100.0,1700003600000,5000000.0,"
            "1000,55.0,2750000.0,0\n"
            "1700003600000,50500.0,51500.0,49500.0,51000.0,200.0,1700007200000,10000000.0,"
            "2000,110.0,5500000.0,0\n"
        )
        table = _parse_klines_csv(csv_text, "5m")
        assert len(table) == 2
        assert table.column("open")[1].as_py() == 50500.0
        assert table.column("volume")[1].as_py() == 200.0
        assert table.column("interval")[1].as_py() == "5m"

    def test_parse_klines_csv_skip_short_row(self):
        """Row with fewer than 11 columns should be skipped."""
        csv_text = "1700000000000,50000.0\n"
        table = _parse_klines_csv(csv_text, "1h")
        assert len(table) == 0

    def test_file_sha256(self):
        """_file_sha256 should compute correct digest."""
        import tempfile
        content = b"test data for sha256"
        expected = hashlib.sha256(content).hexdigest()
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(content)
            tmp = f.name
        try:
            actual = _file_sha256(tmp)
            assert actual == expected
        finally:
            os.unlink(tmp)

    def test_fetch_checksum_parses_correctly(self):
        """_fetch_checksum should extract hash from CHECKSUM content."""
        checksum_content = (
            b"d9b5b65b75f0b94571fbcf2c8b0426b1f885c12be5b9e80b3ae0c3ad81b394df  "
            b"BTCUSDT-1h-2024-01.zip\n"
        )
        with patch("alphaforge.data.backfill._fetch_url", return_value=checksum_content):
            result = _fetch_checksum("http://example.com/test.CHECKSUM")
            assert result == "d9b5b65b75f0b94571fbcf2c8b0426b1f885c12be5b9e80b3ae0c3ad81b394df"

    def test_fetch_checksum_404_returns_none(self):
        """_fetch_checksum should return None on 404."""
        with patch("alphaforge.data.backfill._fetch_url", return_value=None):
            result = _fetch_checksum("http://example.com/missing.CHECKSUM")
            assert result is None


# ---------------------------------------------------------------------------
# Binance Vision — download function (mocked HTTP)
# ---------------------------------------------------------------------------


class FakeHTTPResponse:
    """Minimal mock for urllib.request.urlopen response."""

    def __init__(self, data: bytes):
        self._data = data
        self._pos = 0

    def read(self, n: int = -1) -> bytes:
        if n < 0:
            n = len(self._data) - self._pos
        chunk = self._data[self._pos:self._pos + n]
        self._pos += n
        return chunk

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class TestDownloadFromBinanceVision:
    """Test download_from_binance_vision with mocked HTTP."""

    def _make_sample_csv(self) -> str:
        return (
            "open_time,open,high,low,close,volume,close_time,quote_volume,count,"
            "taker_buy_volume,taker_buy_quote_volume,ignore\n"
            "1700000000000,50000.0,51000.0,49000.0,50500.0,100.0,1700003600000,"
            "5000000.0,1000,55.0,2750000.0,0\n"
        )

    def _make_zip_bytes(self, csv_text: str, filename: str) -> bytes:
        buf = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
        try:
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.writestr(filename, csv_text)
            buf.close()
            with open(buf.name, "rb") as f:
                return f.read()
        finally:
            os.unlink(buf.name)

    def test_download_single_file(self):
        """Should download one ZIP, extract CSV, write Parquet."""
        csv_text = self._make_sample_csv()
        zip_bytes = self._make_zip_bytes(csv_text, "BTCUSDT-1h-2023-01.csv")
        zip_checksum = hashlib.sha256(zip_bytes).hexdigest()

        config = create_binance_vision_config(
            symbols=["BTCUSDT"],
            intervals=["1h"],
            output_dir=tempfile.mkdtemp(),
            start_year=2023,
            start_month=1,
            end_year=2023,
            end_month=1,
        )

        def fake_urlopen(url, timeout=300):
            if url.endswith(".CHECKSUM"):
                return FakeHTTPResponse(
                    f"{zip_checksum}  BTCUSDT-1h-2023-01.zip\n".encode()
                )
            return FakeHTTPResponse(zip_bytes)

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            stats = download_from_binance_vision(config)

        assert stats["total_files"] == 1
        assert stats["total_records"] == 1
        assert stats["errors"] == []
        assert stats["skipped"] == []

        # Verify Parquet was written
        out_path = Path(config.output_dir) / "BTCUSDT" / "1h" / "2023" / "01.parquet"
        assert out_path.exists()
        table = pq.read_table(str(out_path))
        assert len(table) == 1
        assert table.column("open_time")[0].as_py() == 1700000000000

    def test_download_skips_existing(self):
        """Files that already exist should be skipped."""
        import tempfile
        output_dir = tempfile.mkdtemp()

        # Create an existing file (write an empty table to make valid Parquet)
        out_path = Path(output_dir) / "BTCUSDT" / "1h" / "2023" / "01.parquet"
        out_path.parent.mkdir(parents=True)
        empty_table = pa.table({"open_time": pa.array([], type=pa.int64())})
        pq.write_table(empty_table, str(out_path))

        config = create_binance_vision_config(
            symbols=["BTCUSDT"],
            intervals=["1h"],
            output_dir=output_dir,
            start_year=2023,
            start_month=1,
            end_year=2023,
            end_month=1,
        )

        stats = download_from_binance_vision(config)

        assert stats["total_files"] == 0
        assert stats["total_records"] == 0
        assert len(stats["skipped"]) == 1
        assert "01.parquet" in stats["skipped"][0]

    def test_download_checksum_mismatch(self):
        """Checksum mismatch should produce an error."""
        csv_text = self._make_sample_csv()
        zip_bytes = self._make_zip_bytes(csv_text, "BTCUSDT-1h-2023-01.csv")

        config = create_binance_vision_config(
            symbols=["BTCUSDT"],
            intervals=["1h"],
            output_dir=tempfile.mkdtemp(),
            start_year=2023,
            start_month=1,
            end_year=2023,
            end_month=1,
        )

        def fake_urlopen(url, timeout=300):
            if url.endswith(".CHECKSUM"):
                # Return a checksum that won't match
                return FakeHTTPResponse(
                    b"0000000000000000000000000000000000000000000000000000000000000000  "
                    b"BTCUSDT-1h-2023-01.zip\n"
                )
            return FakeHTTPResponse(zip_bytes)

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            stats = download_from_binance_vision(config)

        # Should have an error from the hash mismatch
        assert len(stats["errors"]) == 1
        assert "SHA-256 mismatch" in stats["errors"][0]
        assert stats["total_files"] == 0

    def test_download_http_404(self):
        """HTTP 404 should be recorded as an error."""
        import urllib.error

        config = create_binance_vision_config(
            symbols=["BTCUSDT"],
            intervals=["1h"],
            output_dir=tempfile.mkdtemp(),
            start_year=2023,
            start_month=1,
            end_year=2023,
            end_month=1,
        )

        def fake_urlopen(url, timeout=300):
            raise urllib.error.HTTPError(
                url, 404, "Not Found", {}, None
            )

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            stats = download_from_binance_vision(config)

        assert len(stats["errors"]) == 1
        assert "HTTP 404" in stats["errors"][0]
        assert stats["total_files"] == 0

    def test_download_multiple_months(self):
        """Multiple months should all be downloaded."""
        csv_text = self._make_sample_csv()
        zip_bytes_01 = self._make_zip_bytes(
            csv_text, "BTCUSDT-1h-2023-01.csv"
        )
        zip_bytes_02 = self._make_zip_bytes(
            csv_text, "BTCUSDT-1h-2023-02.csv"
        )
        cs_01 = hashlib.sha256(zip_bytes_01).hexdigest()
        cs_02 = hashlib.sha256(zip_bytes_02).hexdigest()

        config = create_binance_vision_config(
            symbols=["BTCUSDT"],
            intervals=["1h"],
            output_dir=tempfile.mkdtemp(),
            start_year=2023,
            start_month=1,
            end_year=2023,
            end_month=2,
        )

        def fake_urlopen(url, timeout=300):
            if url.endswith(".CHECKSUM"):
                if "2023-01" in url:
                    return FakeHTTPResponse(f"{cs_01}  x.zip\n".encode())
                return FakeHTTPResponse(f"{cs_02}  x.zip\n".encode())
            if "2023-01" in url:
                return FakeHTTPResponse(zip_bytes_01)
            return FakeHTTPResponse(zip_bytes_02)

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            stats = download_from_binance_vision(config)

        assert stats["total_files"] == 2
        assert stats["total_records"] == 2  # 1 record each month
        assert stats["errors"] == []

        # Both month files should exist
        out_01 = Path(config.output_dir) / "BTCUSDT" / "1h" / "2023" / "01.parquet"
        out_02 = Path(config.output_dir) / "BTCUSDT" / "1h" / "2023" / "02.parquet"
        assert out_01.exists()
        assert out_02.exists()


# ---------------------------------------------------------------------------
# Binance Vision — Pipeline integration
# ---------------------------------------------------------------------------


class TestBackfillPipelineVision:
    """Test the download_vision method on BackfillPipeline."""

    def test_download_vision_delegates(self):
        """download_vision should delegate to download_from_binance_vision."""
        from unittest.mock import patch as _patch

        config = create_binance_vision_config(
            symbols=["BTCUSDT"],
            intervals=["1h"],
            output_dir="/tmp/vision_test",
            start_year=2023,
            start_month=1,
            end_year=2023,
            end_month=1,
        )

        mock_client = Mock(spec=BinanceClient)
        from lib.market_data.binance.klines_service import KlinesService
        from lib.market_data.binance.funding_service import FundingService
        from lib.market_data.storage import StorageWriter
        from lib.market_data.catalog import DataCatalog
        from lib.market_data.binance.rate_limiter import BinanceRateLimiter
        from lib.market_data.binance.checkpoint import BackfillCheckpoint

        with tempfile.TemporaryDirectory() as tmp_dir:
            writer = StorageWriter(base_dir=tmp_dir)
            catalog = DataCatalog(catalog_path=f"{tmp_dir}/catalog.json")
            limiter = BinanceRateLimiter()
            with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as cp_file:
                checkpoint = BackfillCheckpoint(file_path=cp_file.name)

            try:
                pipeline = BackfillPipeline(
                    klines_service=KlinesService(mock_client),
                    funding_service=FundingService(mock_client),
                    storage_writer=writer,
                    catalog=catalog,
                    rate_limiter=limiter,
                    checkpoint=checkpoint,
                )

                with _patch(
                    "alphaforge.data.backfill.download_from_binance_vision",
                    return_value={"total_files": 0, "total_records": 0},
                ) as mock_fn:
                    result = pipeline.download_vision(config)
                    mock_fn.assert_called_once_with(config)
                    assert result["total_files"] == 0
            finally:
                if os.path.exists(cp_file.name):
                    os.unlink(cp_file.name)
