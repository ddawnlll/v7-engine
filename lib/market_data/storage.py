"""
Parquet-based storage writer with SHA-256 checksums.

Writes market data (klines raw/normalized, funding rates) to
versioned Parquet files with checksum sidecar files.
"""

import hashlib
import json
import logging
import os
from typing import Optional

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from lib.market_data.contracts import KlineRecord
from lib.market_data.binance.funding_service import FundingRecord

logger = logging.getLogger(__name__)


class StorageWriter:
    """Write market data to Parquet files with SHA-256 checksums.

    File naming convention:
      data/raw/{symbol}/{symbol}_{interval}_{start_ms}_{end_ms}.parquet
      data/normalized/{symbol}/{symbol}_{interval}_{start_ms}_{end_ms}.parquet
      data/normalized/{symbol}/funding_{symbol}_{start_ms}_{end_ms}.parquet

    A ``.sha256`` sidecar file is written alongside each Parquet.
    """

    def __init__(self, base_dir: str = "data") -> None:
        """Initialize storage writer.

        Args:
            base_dir: Root data directory. Writes go to
                      ``{base_dir}/raw/`` and ``{base_dir}/normalized/``.
        """
        self._base_dir = base_dir.rstrip("/")

    # ------------------------------------------------------------------
    # Public write methods
    # ------------------------------------------------------------------

    def write_raw_klines(
        self,
        records: list[KlineRecord],
        symbol: str,
        interval: str,
        start_time: int,
        end_time: int,
    ) -> str:
        """Write raw klines to Parquet (with original Binance fields).

        Returns:
            Path to the written Parquet file.
        """
        rows = [
            {
                "symbol": r.symbol,
                "timestamp": r.timestamp,
                "open": r.open,
                "high": r.high,
                "low": r.low,
                "close": r.close,
                "volume": r.volume,
                "quote_volume": r.quote_volume,
                "trade_count": r.trade_count,
                "taker_buy_volume": r.taker_buy_volume,
                "taker_buy_quote_volume": r.taker_buy_quote_volume,
                "interval": r.interval,
                "source": r.source,
                "is_closed": r.is_closed,
            }
            for r in records
        ]
        file_path = self._path("raw", symbol, interval, start_time, end_time)
        return self._write_parquet(rows, file_path)

    def write_normalized_klines(
        self,
        records: list[KlineRecord],
        symbol: str,
        interval: str,
        start_time: int,
        end_time: int,
    ) -> str:
        """Write normalized klines to Parquet (derived fields added).

        Currently writes the same fields as raw; normalisation transforms
        (e.g. ATR, log-returns) will be added by the feature pipeline.
        """
        rows = [
            {
                "symbol": r.symbol,
                "timestamp": r.timestamp,
                "open": r.open,
                "high": r.high,
                "low": r.low,
                "close": r.close,
                "volume": r.volume,
                "quote_volume": r.quote_volume,
                "trade_count": r.trade_count,
                "taker_buy_volume": r.taker_buy_volume,
                "taker_buy_quote_volume": r.taker_buy_quote_volume,
                "interval": r.interval,
                "source": r.source,
                "is_closed": r.is_closed,
            }
            for r in records
        ]
        file_path = self._path("normalized", symbol, interval, start_time, end_time)
        return self._write_parquet(rows, file_path)

    def write_funding(
        self,
        records: list[FundingRecord],
        symbol: str,
        start_time: int,
        end_time: int,
    ) -> str:
        """Write funding rate records to Parquet.

        Returns:
            Path to the written Parquet file.
        """
        rows = [
            {
                "symbol": r.symbol,
                "timestamp": r.timestamp,
                "funding_rate": r.funding_rate,
                "source": r.source,
            }
            for r in records
        ]
        file_path = self._funding_path("normalized", symbol, start_time, end_time)
        return self._write_parquet(rows, file_path)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _path(self, subdir: str, symbol: str, interval: str,
              start_time: int, end_time: int) -> str:
        return os.path.join(
            self._base_dir,
            subdir,
            symbol.upper(),
            f"{symbol.upper()}_{interval}_{start_time}_{end_time}.parquet",
        )

    def _funding_path(self, subdir: str, symbol: str,
                      start_time: int, end_time: int) -> str:
        return os.path.join(
            self._base_dir,
            subdir,
            symbol.upper(),
            f"funding_{symbol.upper()}_{start_time}_{end_time}.parquet",
        )

    def _write_parquet(self, rows: list[dict], file_path: str) -> str:
        """Write rows to Parquet with checksum sidecar."""
        if not rows:
            logger.warning("No rows to write for %s", file_path)
            return file_path

        df = pd.DataFrame(rows)
        table = pa.Table.from_pandas(df)

        dir_path = os.path.dirname(file_path)
        os.makedirs(dir_path, exist_ok=True)

        pq.write_table(table, file_path)
        logger.info("Wrote %d rows to %s", len(rows), file_path)

        self._write_checksum(file_path)
        return file_path

    def _write_checksum(self, file_path: str) -> None:
        """Write SHA-256 checksum sidecar file."""
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                sha256.update(chunk)

        checksum_path = file_path + ".sha256"
        with open(checksum_path, "w") as f:
            f.write(sha256.hexdigest())

    def verify_checksum(self, file_path: str) -> bool:
        """Verify a Parquet file against its .sha256 sidecar.

        Returns:
            True if checksums match, False otherwise.
        """
        checksum_path = file_path + ".sha256"
        if not os.path.exists(checksum_path):
            logger.warning("No checksum file found for %s", file_path)
            return False

        with open(checksum_path, "r") as f:
            expected = f.read().strip()

        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                sha256.update(chunk)

        actual = sha256.hexdigest()
        return actual == expected
