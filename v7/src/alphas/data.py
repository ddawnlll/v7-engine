"""Alphas data adapter — re-exports the reusable data layer.

Hypothesis files import from ``.data`` (relative to alphas package).
This module forwards to ``data`` (the reusable package at src/data/)
using absolute imports.
"""

import logging
from typing import List, Union

import pandas as pd

from data import (
    download_klines as _download_klines_dict,
    download_funding_rate as _download_funding_rate_dict,
    download_open_interest as _download_open_interest_dict,
    get_top_symbols as _get_top_symbols,
    cache_get,
    cache_set,
    cached,
    fetch_klines_single,
    fetch_funding_rate_single,
    fetch_open_interest_single,
)

from .config import START_DATE, END_DATE, PERPETUAL_SYMBOLS, TOP_N_SYMBOLS

logger = logging.getLogger(__name__)


def download_klines(
    symbols: Union[str, List[str]],
    interval: str = "1h",
    start: str = START_DATE,
    end: str = END_DATE,
    force: bool = False,
) -> Union[pd.DataFrame, dict]:
    """Backward-compatible wrapper.

    - If ``symbols`` is a single string → returns a single DataFrame.
    - If ``symbols`` is a list → returns {symbol: DataFrame}.
    """
    if isinstance(symbols, str):
        return fetch_klines_single(symbols, interval=interval, start=start, end=end, force=force)
    return _download_klines_dict(symbols, interval=interval, start=start, end=end, force=force)


def download_funding_rate(
    symbols: Union[str, List[str]],
    start: str = START_DATE,
    end: str = END_DATE,
    force: bool = False,
) -> Union[pd.DataFrame, dict]:
    """Backward-compatible wrapper."""
    if isinstance(symbols, str):
        return fetch_funding_rate_single(symbols, start=start, end=end, force=force)
    return _download_funding_rate_dict(symbols, start=start, end=end, force=force)


def get_top_symbols_by_volume(n: int = 60, min_volume_usdt: float = 0) -> list:
    return _get_top_symbols(n=n, min_volume_usdt=min_volume_usdt)


def download_open_interest(
    symbols: Union[str, List[str]],
    interval: str = "1h",
    start: str = START_DATE,
    end: str = END_DATE,
    force: bool = False,
) -> Union[pd.DataFrame, dict]:
    """Backward-compatible wrapper.

    - If ``symbols`` is a single string → returns a single DataFrame.
    - If ``symbols`` is a list → returns {symbol: DataFrame}.
    """
    if isinstance(symbols, str):
        return fetch_open_interest_single(symbols, interval=interval, start=start, end=end, force=force)
    return _download_open_interest_dict(symbols, interval=interval, start=start, end=end, force=force)


def check_data_availability(symbols: list = None) -> dict:
    """Verify data completeness for the given symbols (parallel download).

    Uses the parallel klines fetcher to download all symbols simultaneously,
    then checks each for gaps and completeness.

    Returns dict with symbol -> {ok: bool, gap_hours: float, pct_complete: float}.
    """
    if symbols is None:
        symbols = PERPETUAL_SYMBOLS[:TOP_N_SYMBOLS]

    logger.info(f"Downloading klines for {len(symbols)} symbols in parallel...")
    all_data = download_klines(list(symbols))  # parallel fetch

    results = {}
    for sym in symbols:
        df = all_data.get(sym)
        if df is None or df.empty:
            results[sym] = {"ok": False, "gap_hours": 999, "pct_complete": 0.0}
            continue
        try:
            df = df.sort_values("timestamp")
            df["delta_h"] = df["timestamp"].diff().dt.total_seconds() / 3600
            max_gap = df["delta_h"].max()
            total_h = (df["timestamp"].max() - df["timestamp"].min()).total_seconds() / 3600
            expected = int(total_h) + 1
            pct = len(df) / expected if expected > 0 else 0
            ok = max_gap <= 24 and pct >= 0.90
            results[sym] = {"ok": ok, "gap_hours": float(max_gap), "pct_complete": round(pct, 4)}
        except Exception as e:
            logger.warning(f"Data check failed for {sym}: {e}")
            results[sym] = {"ok": False, "gap_hours": 999, "pct_complete": 0.0}
    return results


def filter_symbols_with_data(symbols: List[str], min_year: int = 2021) -> List[str]:
    """Keep only symbols whose klines data starts at or before *min_year*.

    Uses cached Parquet files if available; otherwise fetches the first
    candle timestamp.
    """
    from data.binance import fetch_klines_single
    import os

    kept = []
    cutoff = datetime(min_year, 1, 1, tzinfo=timezone.utc)
    for sym in symbols:
        try:
            df = fetch_klines_single(sym, interval="1mo", start=f"{min_year}-01-01", end=f"{min_year}-12-31")
            if df is not None and not df.empty:
                kept.append(sym)
        except Exception:
            continue
    logger.info(f"Symbol filter: {len(kept)}/{len(symbols)} have data since {min_year}")
    return kept


__all__ = [
    "download_klines",
    "download_funding_rate",
    "download_open_interest",
    "get_top_symbols_by_volume",
    "filter_symbols_with_data",
    "cache_get", "cache_set", "cached",
    "check_data_availability",
]
