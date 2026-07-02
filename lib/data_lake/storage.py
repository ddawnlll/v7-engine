"""Data Lake — centralized path resolution for medallion architecture.

Provides :class:`DataLakePaths` with static methods that compute
storage paths for raw, bronze, and silver layers.  No I/O — pure path
math on :class:`pathlib.Path`.

Domain-boundary compliant: imports only stdlib.
"""

from __future__ import annotations

import pathlib
from typing import Final


class DataLakePaths:
    """Read-only path resolver for data lake storage.

    All methods are static — no state.  Paths are relative to
    ``BASE_DIR`` (default: ``<project_root> / "data_lake"``).
    """

    BASE_DIR: pathlib.Path = pathlib.Path(__file__).resolve().parent.parent.parent / "data_lake"

    # --- Layer roots (relative to BASE_DIR) ---

    RAW_BINANCE_UM: Final[pathlib.PurePosixPath] = pathlib.PurePosixPath(
        "raw/binance/um"
    )
    BRONZE_BINANCE_UM: Final[pathlib.PurePosixPath] = pathlib.PurePosixPath(
        "bronze/binance/um"
    )
    SILVER_BINANCE_UM: Final[pathlib.PurePosixPath] = pathlib.PurePosixPath(
        "silver/binance/um"
    )
    MANIFESTS: Final[pathlib.PurePosixPath] = pathlib.PurePosixPath("manifests")

    # ------------------------------------------------------------------
    # Raw layer
    # ------------------------------------------------------------------

    @staticmethod
    def klines_path(
        symbol: str,
        interval: str,
        year: int,
        month: int,
    ) -> pathlib.Path:
        """``data_lake/raw/binance/um/klines/{symbol}/{interval}/{year}/{month:02d}.parquet``"""
        return (
            DataLakePaths.BASE_DIR
            / DataLakePaths.RAW_BINANCE_UM
            / "klines"
            / symbol
            / interval
            / str(year)
            / f"{month:02d}.parquet"
        )

    @staticmethod
    def funding_rate_path(
        symbol: str,
        year: int,
        month: int,
    ) -> pathlib.Path:
        """``data_lake/raw/binance/um/fundingRate/{symbol}/{year}/{month:02d}.parquet``"""
        return (
            DataLakePaths.BASE_DIR
            / DataLakePaths.RAW_BINANCE_UM
            / "fundingRate"
            / symbol
            / str(year)
            / f"{month:02d}.parquet"
        )

    @staticmethod
    def mark_price_path(
        symbol: str,
        interval: str,
        year: int,
        month: int,
    ) -> pathlib.Path:
        """``data_lake/raw/binance/um/markPrice/{symbol}/{interval}/{year}/{month:02d}.parquet``"""
        return (
            DataLakePaths.BASE_DIR
            / DataLakePaths.RAW_BINANCE_UM
            / "markPrice"
            / symbol
            / interval
            / str(year)
            / f"{month:02d}.parquet"
        )

    # ------------------------------------------------------------------
    # Bronze layer
    # ------------------------------------------------------------------

    @staticmethod
    def bronze_klines_path(
        symbol: str,
        interval: str,
        year: int,
        month: int,
    ) -> pathlib.Path:
        """``data_lake/bronze/binance/um/klines/{symbol}/{interval}/{year}/{month:02d}.parquet``"""
        return (
            DataLakePaths.BASE_DIR
            / DataLakePaths.BRONZE_BINANCE_UM
            / "klines"
            / symbol
            / interval
            / str(year)
            / f"{month:02d}.parquet"
        )

    # ------------------------------------------------------------------
    # Manifests
    # ------------------------------------------------------------------

    @staticmethod
    def manifest_path(name: str) -> pathlib.Path:
        """``data_lake/manifests/{name}.json``"""
        return (
            DataLakePaths.BASE_DIR
            / DataLakePaths.MANIFESTS
            / f"{name}.json"
        )
