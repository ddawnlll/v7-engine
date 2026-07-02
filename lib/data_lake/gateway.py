"""DataGateway — unified read interface for the data lake.

Pipeline never guesses local paths.  Pure read — never writes.

Reads parquet files from the medallion-architecture data lake
(``bronze`` / ``raw`` / ``silver`` layers under
``data_lake/{layer}/binance/um/{data_type}/…``).

Domain-boundary compliant: imports only lib/ primitives, stdlib, and
pandas.
"""

from __future__ import annotations

import logging
import pathlib
from datetime import datetime
from typing import Optional

import pandas as pd

from lib.data_lake.catalog import DataCatalog
from lib.data_lake.spec import DatasetSpec
from lib.data_lake.storage import DataLakePaths

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Column constants — match Binance raw klines export order
# ---------------------------------------------------------------------------

KLINES_COLUMNS: list[str] = [
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "quote_volume",
    "trade_count",
    "taker_buy_base_volume",
    "taker_buy_quote_volume",
]

FUNDING_RATE_COLUMNS: list[str] = [
    "timestamp",
    "funding_rate",
    "mark_price",
]

# ---------------------------------------------------------------------------
# DataGateway
# ---------------------------------------------------------------------------


class DataGateway:
    """Unified read interface for the data lake.

    Concatenates monthly parquet files, caches directory listings, and
    provides fallback logic (bronze -> raw).  Pure read — never writes
    to the lake.

    Parameters
    ----------
    data_dir:
        Path to the data lake root directory.  Defaults to ``"data_lake"``
        (resolved relative to the current working directory).
    catalog:
        Optional :class:`DataCatalog` instance.  If omitted, an in-memory
        catalog is created lazily for :meth:`coverage_summary`.
    """

    def __init__(
        self,
        data_dir: str = "data_lake",
        catalog: Optional[DataCatalog] = None,
    ) -> None:
        self._data_dir: pathlib.Path = pathlib.Path(data_dir).resolve()
        self._catalog: DataCatalog = (
            catalog
            if catalog is not None
            else DataCatalog(
                catalog_path=str(self._data_dir / ".gateway_catalog.json")
            )
        )
        # Cache: data_type -> list[str] of symbol names
        self._symbol_cache: dict[str, list[str]] = {}

    # ------------------------------------------------------------------
    # Path resolution
    # ------------------------------------------------------------------

    def resolve_path(
        self,
        symbol: str,
        interval: str,
        data_type: str = "klines",
        layer: str = "bronze",
    ) -> pathlib.Path:
        """Resolve the *layer* directory root for a symbol / interval / data_type.

        Follows :class:`DataLakePaths` conventions (medallion layout under
        ``data_lake/{layer}/binance/um/{data_type}/…``).

        Returns a **directory** path (not an individual monthly parquet
        file).
        """
        symbol = symbol.upper()

        if layer == "bronze":
            root = DataLakePaths.BRONZE_BINANCE_UM
        elif layer == "raw":
            root = DataLakePaths.RAW_BINANCE_UM
        elif layer == "silver":
            root = DataLakePaths.SILVER_BINANCE_UM
        else:
            raise ValueError(f"Unknown layer: {layer!r}")

        if data_type == "klines":
            return self._data_dir / root / "klines" / symbol / interval
        elif data_type == "funding_rate":
            return self._data_dir / root / "fundingRate" / symbol
        elif data_type == "mark_price":
            return self._data_dir / root / "markPrice" / symbol / interval
        else:
            raise ValueError(f"Unknown data_type: {data_type!r}")

    # ------------------------------------------------------------------
    # Read methods
    # ------------------------------------------------------------------

    def read_klines(
        self,
        symbol: str,
        interval: str,
        start: datetime,
        end: datetime,
        source: str = "bronze",
    ) -> pd.DataFrame:
        """Read klines for *symbol* over the half-open interval [*start*, *end*).

        First tries the *source* layer (default ``"bronze"``).  If no data
        is found in bronze, falls back to ``"raw"``.  Raises
        :class:`FileNotFoundError` when no data exists in either layer.

        Returns columns in :data:`KLINES_COLUMNS` order, sorted by
        timestamp, with duplicates removed.
        """
        if source not in ("bronze", "raw"):
            raise ValueError(f"Unknown source layer: {source!r}")

        df = self._read_monthly_parquets(
            symbol=symbol,
            interval=interval,
            start=start,
            end=end,
            data_type="klines",
            source=source,
            columns=KLINES_COLUMNS,
        )

        # Fallback to raw when the preferred layer is empty
        if df.empty and source == "bronze":
            df = self._read_monthly_parquets(
                symbol=symbol,
                interval=interval,
                start=start,
                end=end,
                data_type="klines",
                source="raw",
                columns=KLINES_COLUMNS,
            )

        if df.empty:
            raise FileNotFoundError(
                f"No klines data for {symbol} {interval} "
                f"[{start.isoformat()}, {end.isoformat()}) "
                f"in bronze or raw"
            )

        return df

    def read_funding_rate(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
    ) -> pd.DataFrame:
        """Read funding rates for *symbol* over [*start*, *end*).

        Reads from the ``raw`` layer.  Returns columns in
        :data:`FUNDING_RATE_COLUMNS` order, sorted by timestamp, with
        duplicates removed.

        Raises :class:`FileNotFoundError` when no data exists.
        """
        df = self._read_monthly_parquets(
            symbol=symbol,
            interval="",
            start=start,
            end=end,
            data_type="funding_rate",
            source="raw",
            columns=FUNDING_RATE_COLUMNS,
        )

        if df.empty:
            raise FileNotFoundError(
                f"No funding rate data for {symbol} "
                f"[{start.isoformat()}, {end.isoformat()})"
            )

        return df

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def list_available_symbols(self, data_type: str = "klines") -> list[str]:
        """List symbols that have data in the lake for *data_type*.

        Scans the layer directory structure.  Results are cached
        in-memory for the lifetime of this instance.
        """
        if data_type in self._symbol_cache:
            return self._symbol_cache[data_type]

        if data_type == "klines":
            base = self._data_dir / "bronze" / "binance" / "um" / "klines"
        elif data_type == "funding_rate":
            base = self._data_dir / "raw" / "binance" / "um" / "fundingRate"
        else:
            return []

        if not base.exists():
            return []

        symbols = sorted(
            entry.name for entry in base.iterdir() if entry.is_dir()
        )
        self._symbol_cache[data_type] = symbols
        return symbols

    # ------------------------------------------------------------------
    # Coverage
    # ------------------------------------------------------------------

    def coverage_summary(self, spec: DatasetSpec) -> dict:
        """Produce a coverage summary dict for the given *spec*.

        Delegates to :meth:`DataCatalog.to_summary`.  Returns a dict with
        keys ``coverage_pct``, ``gap_count``, ``symbols``, ``intervals``,
        etc.
        """
        return self._catalog.to_summary(spec)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _monthly_parquet_path(
        self,
        symbol: str,
        interval: str,
        year: int,
        month: int,
        data_type: str = "klines",
        layer: str = "bronze",
    ) -> pathlib.Path:
        """Build the path to a single monthly parquet file.

        Follows the same naming convention as :class:`DataLakePaths`::

            <data_dir>/{layer}/binance/um/{data_type_dir}/{symbol}[/{interval}]/{year}/{month:02d}.parquet
        """
        symbol = symbol.upper()

        if data_type == "klines":
            return (
                self._data_dir
                / layer / "binance" / "um" / "klines"
                / symbol / interval
                / str(year) / f"{month:02d}.parquet"
            )
        elif data_type == "funding_rate":
            return (
                self._data_dir
                / layer / "binance" / "um" / "fundingRate"
                / symbol
                / str(year) / f"{month:02d}.parquet"
            )
        elif data_type == "mark_price":
            return (
                self._data_dir
                / layer / "binance" / "um" / "markPrice"
                / symbol / interval
                / str(year) / f"{month:02d}.parquet"
            )
        else:
            raise ValueError(f"Unknown data_type: {data_type!r}")

    def _read_monthly_parquets(
        self,
        symbol: str,
        interval: str,
        start: datetime,
        end: datetime,
        data_type: str,
        source: str,
        columns: list[str],
    ) -> pd.DataFrame:
        """Read and concatenate monthly parquet files covering [*start*, *end*).

        Collects every month whose directory overlaps the query range,
        reads any existing parquet file, concatenates them, and filters
        to the exact [start, end) window.

        Returns an empty DataFrame (with *columns*) when no files are
        found.
        """
        start_ms = int(start.timestamp() * 1000)
        end_ms = int(end.timestamp() * 1000)

        frames: list[pd.DataFrame] = []
        year, month = start.year, start.month
        end_year, end_month = end.year, end.month

        # Visit every month from start to end inclusive (extra months
        # are harmless because we filter by timestamp later).
        while (year, month) <= (end_year, end_month):
            p = self._monthly_parquet_path(
                symbol=symbol,
                interval=interval,
                year=year,
                month=month,
                data_type=data_type,
                layer=source,
            )

            if p.exists():
                try:
                    df = pd.read_parquet(p)
                    frames.append(df)
                except Exception as exc:
                    logger.warning("Failed to read %s: %s", p, exc)

            month += 1
            if month > 12:
                month = 1
                year += 1

        if not frames:
            return pd.DataFrame(columns=columns)

        result = pd.concat(frames, ignore_index=True)

        # Filter to exact [start, end) window
        if "timestamp" in result.columns:
            result = result[
                (result["timestamp"] >= start_ms) & (result["timestamp"] < end_ms)
            ]

        # Sort by timestamp and remove duplicates
        if "timestamp" in result.columns and not result.empty:
            result = (
                result.sort_values("timestamp")
                .drop_duplicates(subset=["timestamp"], keep="last")
                .reset_index(drop=True)
            )

        # Ensure only requested columns are returned
        present = [c for c in columns if c in result.columns]
        return result[present]

    def invalidate_cache(self) -> None:
        """Clear the in-memory symbol cache."""
        self._symbol_cache.clear()
