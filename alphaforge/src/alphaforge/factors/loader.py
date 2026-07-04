"""Data loader for factor sprint — reads 1h OHLCV from the data lake.

Uses DataGateway.read_klines for parquet access. Resamples to 4h when needed.
All functions are pure: same inputs → same outputs, no side effects.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import hashlib

import numpy as np
import pandas as pd

try:
    import cudf
    import cupy as cp
    HAS_CUDF = True
except ImportError:
    cudf = None  # type: ignore[assignment]
    cp = None  # type: ignore[assignment]
    HAS_CUDF = False

_CACHE_DIR = Path(__file__).resolve().parents[4] / "cache" / "factor_sprint"

# Ensure project root is on sys.path for lib.data_lake imports
# factors/loader.py is at alphaforge/src/alphaforge/factors/loader.py
# Project root is 3 parents up
_PROJECT_ROOT = str(Path(__file__).resolve().parents[3])
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from lib.data_lake.gateway import DataGateway  # noqa: E402


# Default universe — 20 Binance perp symbols
DEFAULT_SYMBOLS: list[str] = [
    "ADAUSDT", "APTUSDT", "ARBUSDT", "ATOMUSDT", "AVAXUSDT",
    "BNBUSDT", "BTCUSDT", "DOGEUSDT", "DOTUSDT", "ETHUSDT",
    "FILUSDT", "INJUSDT", "LINKUSDT", "MATICUSDT", "NEARUSDT",
    "OPUSDT", "RUNEUSDT", "SOLUSDT", "SUIUSDT", "XRPUSDT",
]

DEFAULT_START = datetime(2023, 1, 1)
DEFAULT_END = datetime(2026, 7, 1)


def load_1h_ohlcv(
    symbols: list[str] | None = None,
    start: datetime = DEFAULT_START,
    end: datetime = DEFAULT_END,
) -> dict[str, pd.DataFrame]:
    """Load 1h OHLCV for all symbols from the data lake.

    Reads parquet files directly (bypasses DataGateway which drops
    the timestamp column for non-standard schemas).

    Returns:
        Dict mapping symbol → DataFrame with columns:
        [open, high, low, close, volume] indexed by timestamp.
        Empty DataFrame for symbols with no data.
    """
    if symbols is None:
        symbols = DEFAULT_SYMBOLS

    import glob

    result: dict[str, pd.DataFrame] = {}
    start_ms = int(start.timestamp() * 1000)
    end_ms = int(end.timestamp() * 1000)

    for sym in symbols:
        try:
            # Find all monthly parquet files for this symbol
            pattern = f"data_lake/raw/binance/um/klines/{sym}/1h/*/*.parquet"
            files = sorted(glob.glob(pattern))

            if not files:
                result[sym] = pd.DataFrame()
                continue

            frames = []
            for f in files:
                try:
                    df = pd.read_parquet(f)
                    frames.append(df)
                except Exception:
                    continue

            if not frames:
                result[sym] = pd.DataFrame()
                continue

            df = pd.concat(frames, ignore_index=True)
            df.columns = [c.lower() for c in df.columns]

            # Find timestamp column — raw parquet may use 'open_time'
            ts_col = None
            for candidate in ["timestamp", "open_time"]:
                if candidate in df.columns:
                    ts_col = candidate
                    break

            if ts_col is None:
                print(f"[loader] WARNING: {sym} has no timestamp column")
                result[sym] = pd.DataFrame()
                continue

            # Convert to datetime index
            df.index = pd.to_datetime(df[ts_col], unit="ms", utc=True)
            df = df.drop(columns=[ts_col], errors="ignore")

            # Filter to [start, end)
            df = df[(df.index >= pd.Timestamp(start, tz="UTC")) &
                    (df.index < pd.Timestamp(end, tz="UTC"))]

            # Sort, dedup
            df = df.sort_index()
            df = df[~df.index.duplicated(keep="last")]

            # Keep only OHLCV columns
            keep = [c for c in ["open", "high", "low", "close", "volume"] if c in df.columns]
            df = df[keep]
            result[sym] = df

        except Exception as e:
            print(f"[loader] WARNING: {sym} load failed: {e}")
            result[sym] = pd.DataFrame()

    return result


# ── FUNDING RATE LOADER ────────────────────────────────────────────

def load_funding_rates(
    symbols: list[str] | None = None,
    start: datetime = DEFAULT_START,
    end: datetime = DEFAULT_END,
) -> dict[str, pd.DataFrame]:
    """Load historical funding rates from data_lake and resample to 1h.

    Funding rates are published every 8h on Binance. We forward-fill
    to 1h to align with the OHLCV panels.

    Returns:
        Dict mapping symbol → DataFrame with columns [funding_rate]
        indexed by 1h timestamps.
    """
    if symbols is None:
        symbols = DEFAULT_SYMBOLS

    import glob

    base_dir = Path(__file__).resolve().parents[4] / "data_lake" / "raw" / "binance" / "um" / "fundingRate"
    result: dict[str, pd.DataFrame] = {}

    for sym in symbols:
        try:
            pattern = str(base_dir / sym / "*" / "*.parquet")
            files = sorted(glob.glob(pattern))
            if not files:
                result[sym] = pd.DataFrame()
                continue

            frames = []
            for f in files:
                try:
                    df = pd.read_parquet(f)
                    frames.append(df)
                except Exception:
                    continue

            if not frames:
                result[sym] = pd.DataFrame()
                continue

            df = pd.concat(frames)
            df = df[~df.index.duplicated(keep="last")]
            df = df.sort_index()

            # Filter to date range
            df = df[(df.index >= pd.Timestamp(start, tz="UTC")) &
                    (df.index < pd.Timestamp(end, tz="UTC"))]

            # Keep only funding_rate column
            if "funding_rate" in df.columns:
                df = df[["funding_rate"]].copy()
                df["funding_rate"] = pd.to_numeric(df["funding_rate"], errors="coerce")
            else:
                result[sym] = pd.DataFrame()
                continue

            # Resample to 1h by forward-filling (funding is every 8h)
            df = df.resample("1h").ffill()

            result[sym] = df

        except Exception as e:
            print(f"[loader] WARNING: {sym} funding rate load failed: {e}")
            result[sym] = pd.DataFrame()

    return result


def build_funding_panel(
    funding_data: dict[str, pd.DataFrame],
    aligned_index: pd.DatetimeIndex,
) -> pd.DataFrame:
    """Build a funding rate panel aligned to the OHLCV panel index.

    Returns DataFrame[timestamps × symbols] of funding rates.
    """
    panel_data = {}
    for sym, df in funding_data.items():
        if not df.empty and "funding_rate" in df.columns:
            panel_data[sym] = df["funding_rate"].reindex(aligned_index)

    if not panel_data:
        return pd.DataFrame(index=aligned_index)

    return pd.DataFrame(panel_data, index=aligned_index)


def resample_to_4h(data_1h: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """Resample 1h data to 4h OHLCV using standard bar aggregation.

    Rules:
    - open: first open in the 4h window
    - high: max high
    - low: min low
    - close: last close
    - volume: sum of volume
    """
    result: dict[str, pd.DataFrame] = {}
    for sym, df in data_1h.items():
        if df.empty:
            result[sym] = df
            continue
        agg = {
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
        }
        if "volume" in df.columns:
            agg["volume"] = "sum"
        resampled = df.resample("4h").agg(agg).dropna(subset=["close"])
        result[sym] = resampled
    return result


def build_aligned_panel(
    data: dict[str, pd.DataFrame],
    columns: list[str] | None = None,
) -> dict[str, pd.DataFrame]:
    """Align all symbols to a common timestamp index.

    Returns dict mapping column_name → DataFrame (timestamps × symbols).
    Missing values are NaN.
    """
    if columns is None:
        columns = ["close", "high", "low", "open", "volume"]

    # Find common timestamps (intersection of all non-empty symbols)
    valid = {s: df for s, df in data.items() if not df.empty}
    if not valid:
        return {}

    # Use union of all timestamps, then align
    all_idx = pd.DatetimeIndex([])
    for df in valid.values():
        all_idx = all_idx.union(df.index)
    all_idx = all_idx.sort_values()

    panels: dict[str, pd.DataFrame] = {}
    for col in columns:
        panel_data = {}
        for sym, df in valid.items():
            if col in df.columns:
                panel_data[sym] = df[col].reindex(all_idx)
        if panel_data:
            panels[col] = pd.DataFrame(panel_data, index=all_idx)

    return panels


def load_or_build_aligned_panel(
    data: dict[str, pd.DataFrame],
    start: datetime = DEFAULT_START,
    end: datetime = DEFAULT_END,
    columns: list[str] | None = None,
) -> dict[str, pd.DataFrame]:
    """Load aligned panel from cache or build fresh."""
    if columns is None:
        columns = ["close", "high", "low", "open", "volume"]

    valid_syms = sorted(s for s, df in data.items() if not df.empty)
    cache_key = hashlib.sha256(
        f"{'|'.join(valid_syms)}:{start}:{end}".encode()
    ).hexdigest()[:16]

    _CACHE_DIR.mkdir(parents=True, exist_ok=True)

    panels = {}
    all_cached = True
    for col in columns:
        cache_file = _CACHE_DIR / f"panel_{cache_key}_{col}.parquet"
        if cache_file.exists():
            panels[col] = pd.read_parquet(cache_file)
        else:
            all_cached = False
            break

    if all_cached and panels:
        return panels

    panels = build_aligned_panel(data, columns)
    return panels


# ----------------------------------------------------------------------
# GPU‑enabled helpers (ROCm / cuDF / CuPy)
# ----------------------------------------------------------------------

def load_1h_ohlcv_gpu(
    symbols: list[str] | None = None,
    start: datetime = DEFAULT_START,
    end: datetime = DEFAULT_END,
) -> dict[str, cudf.DataFrame]:
    """GPU‑accelerated loader using cuDF.

    If cuDF is unavailable, falls back to the CPU implementation.
    """
    if not HAS_CUDF:
        # Fallback to CPU loader and convert DataFrames to cuDF if needed
        print("[loader] INFO: cuDF not available, falling back to CPU loader")
        cpu_data = load_1h_ohlcv(symbols, start, end)
        # Convert pandas DataFrames to cuDF DataFrames when possible
        try:
            import cudf
            return {sym: cudf.from_pandas(df) for sym, df in cpu_data.items()}
        except Exception:
            return cpu_data

    if symbols is None:
        symbols = DEFAULT_SYMBOLS

    result: dict[str, cudf.DataFrame] = {}
    start_ms = int(start.timestamp() * 1000)
    end_ms = int(end.timestamp() * 1000)

    for sym in symbols:
        try:
            pattern = f"data_lake/raw/binance/um/klines/{sym}/1h/*/*.parquet"
            df = cudf.read_parquet(
                pattern,
                columns=["timestamp", "open", "high", "low", "close", "volume"],
                filters=[("timestamp", ">=", start_ms), ("timestamp", "<", end_ms)],
                engine="pyarrow",
                use_threads=True,
            )
            if df.empty:
                result[sym] = cudf.DataFrame()
                continue
            df.columns = [c.lower() for c in df.columns]
            df["timestamp"] = cp.array(df["timestamp"])
            df["timestamp"] = cudf.utils.dtypes.convert_timestamp_to_datetime(
                df["timestamp"], unit="ms"
            )
            df = df.set_index("timestamp")
            df = df[["open", "high", "low", "close", "volume"]]
            df = df[~df.index.duplicated(keep="last")].sort_index()
            result[sym] = df
        except Exception as exc:
            print(f"[loader] WARNING: {sym} GPU load failed: {exc}")
            result[sym] = cudf.DataFrame()

    return result


def build_aligned_panel_gpu(
    data: dict[str, cudf.DataFrame],
    columns: list[str] | None = None,
) -> dict[str, cudf.DataFrame]:
    """Align cuDF panels across symbols on a common timestamp index."""
    if columns is None:
        columns = ["close", "high", "low", "open", "volume"]

    valid = {s: df for s, df in data.items() if not df.empty}
    if not valid:
        return {}

    all_idx = cudf.concat([df.index for df in valid.values()])
    all_idx = all_idx.unique().sort_values()

    panels: dict[str, cudf.DataFrame] = {}
    for col in columns:
        panel_data = {}
        for sym, df in valid.items():
            if col in df.columns:
                panel_data[sym] = df[[col]].reindex(all_idx)
        if panel_data:
            panels[col] = cudf.DataFrame(panel_data, index=all_idx)
    return panels


def load_or_build_aligned_panel_gpu(
    data: dict[str, cudf.DataFrame],
    start: datetime = DEFAULT_START,
    end: datetime = DEFAULT_END,
    columns: list[str] | None = None,
) -> dict[str, cudf.DataFrame]:
    """Same caching logic as the CPU version but operates on cuDF.

    If cuDF is unavailable, falls back to the CPU version and
    returns pandas DataFrames.
    """
    if not HAS_CUDF:
        print("[loader] INFO: cuDF not available, falling back to CPU aligned panel")
        # Use CPU loader and convert if possible
        from .loader import load_or_build_aligned_panel
        return load_or_build_aligned_panel(data, start, end, columns)

    if columns is None:
        columns = ["close", "high", "low", "open", "volume"]

    valid_syms = sorted(s for s, df in data.items() if not df.empty)
    cache_key = hashlib.sha256(
        f"{','.join(valid_syms)}:{start}:{end}".encode()
    ).hexdigest()[:16]

    _CACHE_DIR.mkdir(parents=True, exist_ok=True)

    panels = {}
    all_cached = True
    for col in columns:
        cache_file = _CACHE_DIR / f"panel_{cache_key}_{col}.parquet"
        if cache_file.exists():
            panels[col] = cudf.read_parquet(cache_file)
        else:
            all_cached = False
            break

    if all_cached and panels:
        return panels

    panels = build_aligned_panel_gpu(data, columns)

    for col, df in panels.items():
        cache_file = _CACHE_DIR / f"panel_{cache_key}_{col}.parquet"
        df.to_parquet(cache_file)

    return panels


