"""Tests for DataLakePaths — path resolution for medallion storage."""

from __future__ import annotations

import pathlib
from typing import Any

from lib.data_lake.storage import DataLakePaths


def test_path_resolution() -> None:
    """klines_path returns correct path components."""
    p = DataLakePaths.klines_path("BTCUSDT", "1h", 2024, 3)

    assert isinstance(p, pathlib.Path)
    # Every component in the expected sequence must be present.
    parts = p.parts
    assert "raw" in parts
    assert "binance" in parts
    assert "um" in parts
    assert "klines" in parts
    assert "BTCUSDT" in parts
    assert "1h" in parts
    assert "2024" in parts
    assert "03.parquet" == p.name


def test_bronze_path() -> None:
    """bronze_klines_path mirrors raw structure under bronze/."""
    p = DataLakePaths.bronze_klines_path("ETHUSDT", "15m", 2024, 11)

    parts = p.parts
    assert "bronze" in parts
    assert "binance" in parts
    assert "um" in parts
    assert "klines" in parts
    assert "ETHUSDT" in parts
    assert "15m" in parts
    assert "2024" in parts
    assert "11.parquet" == p.name
    assert "raw" not in parts


def test_funding_rate_path() -> None:
    """funding_rate_path resolves under raw/binance/um/fundingRate/."""
    p = DataLakePaths.funding_rate_path("BTCUSDT", 2025, 6)

    assert "fundingRate" in p.parts
    assert "06.parquet" == p.name


def test_mark_price_path() -> None:
    """mark_price_path resolves under raw/binance/um/markPrice/."""
    p = DataLakePaths.mark_price_path("ETHUSDT", "1h", 2025, 1)

    assert "markPrice" in p.parts
    assert "ETHUSDT" in p.parts
    assert "1h" in p.parts
    assert "01.parquet" == p.name


def test_manifest_path() -> None:
    """manifest_path returns correct path with .json extension."""
    p = DataLakePaths.manifest_path("download_manifest")

    assert "manifests" in p.parts
    assert p.suffix == ".json"
    assert p.stem == "download_manifest"
    assert p.name == "download_manifest.json"


def test_configurable_base() -> None:
    """BASE_DIR override works correctly."""
    original = DataLakePaths.BASE_DIR
    try:
        DataLakePaths.BASE_DIR = pathlib.Path("/custom/data_lake")
        p = DataLakePaths.klines_path("BTCUSDT", "1h", 2024, 1)
        assert str(p).startswith("/custom/data_lake")
    finally:
        DataLakePaths.BASE_DIR = original


def test_roundtrip() -> None:
    """Symbol case preserved, no double slashes."""
    p = DataLakePaths.klines_path("btcUSDT", "1h", 2024, 1)
    assert "btcUSDT" in p.parts
    # No empty-string segment -> no double slash.
    assert "" not in p.parts
    assert "//" not in str(p)


def test_all_data_types() -> None:
    """Exercise every path method to ensure no crashes."""
    args: dict[str, Any] = dict(symbol="ADAUSDT", interval="4h", year=2025, month=7)

    DataLakePaths.klines_path(**args)
    DataLakePaths.funding_rate_path(symbol="ADAUSDT", year=2025, month=7)
    DataLakePaths.mark_price_path(**args)
    DataLakePaths.bronze_klines_path(**args)
    DataLakePaths.manifest_path("test")
    # If we get here without exception the test passes.
    assert True
