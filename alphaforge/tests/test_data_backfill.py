"""Test suite for AlphaForge data backfill pipeline.

Covers:
  - BackfillConfig validation (construction errors)
  - create_backfill_config factory
  - Dry-run pipeline
  - Full pipeline with mocked Binance dependencies
  - Integrity validation
  - Error handling
  - Domain boundary (no imports from simulation/v7/runtime/interface)
"""

from __future__ import annotations

import os
import tempfile
from unittest.mock import Mock

import pytest

from alphaforge.data.backfill import (
    BackfillConfig,
    BackfillError,
    BackfillPipeline,
    BackfillResult,
    create_backfill_config,
    create_pipeline,
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
