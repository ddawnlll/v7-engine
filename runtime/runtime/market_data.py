"""Market data fetch and persistence runtime for v4."""

from __future__ import annotations

import time
from typing import Any, Callable

import pandas as pd

from runtime.db.repos.candle_repo import CandleRepository
from runtime.db.session import session_scope


def _candle_row_to_payload(symbol: str, interval: str, row: dict[str, Any], stale: bool) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "interval": interval,
        "open_time_utc": pd.Timestamp(row["open_time"]).isoformat(),
        "close_time_utc": pd.Timestamp(row.get("close_time") or row["open_time"]).isoformat(),
        "open": float(row["open"]),
        "high": float(row["high"]),
        "low": float(row["low"]),
        "close": float(row["close"]),
        "volume": float(row.get("volume", 0.0)),
        "source": "binance",
        "stale": stale,
    }


def _records_to_frame(records: list[dict[str, Any]]) -> pd.DataFrame:
    frame = pd.DataFrame(records)
    if frame.empty:
        raise ValueError("No candle records available.")
    frame["open_time"] = pd.to_datetime(frame["open_time_utc"])
    frame["close_time"] = pd.to_datetime(frame["close_time_utc"])
    for column in ("open", "high", "low", "close", "volume"):
        frame[column] = frame[column].astype(float)
    if "trades" not in frame.columns:
        frame["trades"] = 0
    if "quote_volume" not in frame.columns:
        frame["quote_volume"] = 0.0
    return frame[["open_time", "open", "high", "low", "close", "volume", "trades", "quote_volume", "close_time"]]


class MarketDataRuntime:
    def __init__(
        self,
        candle_repo: CandleRepository | None = None,
        candle_fetcher: Callable[[str, str, int], pd.DataFrame] | None = None,
        snapshot_builder: Callable[[pd.DataFrame], dict[str, Any]] | None = None,
    ) -> None:
        if candle_fetcher is None:
            from runtime.services.binance_client import fetch_klines

            candle_fetcher = fetch_klines
        if snapshot_builder is None:
            from runtime.services.indicator_snapshot import build_indicator_snapshot

            snapshot_builder = build_indicator_snapshot
        self.candle_repo = candle_repo or CandleRepository()
        self.candle_fetcher = candle_fetcher
        self.snapshot_builder = snapshot_builder

    def get_market_snapshot(self, symbol: str, interval: str, limit: int = 250) -> dict[str, Any]:
        started = time.perf_counter()
        try:
            fetch_started = time.perf_counter()
            frame = self.candle_fetcher(symbol, interval, limit)
            fetch_ms = round((time.perf_counter() - fetch_started) * 1000.0, 4)
            persist_started = time.perf_counter()
            persist_meta = self._persist_frame(symbol, interval, frame, stale=False)
            persist_ms = round((time.perf_counter() - persist_started) * 1000.0, 4)
            snapshot_started = time.perf_counter()
            snapshot = dict(self.snapshot_builder(frame))
            snapshot_ms = round((time.perf_counter() - snapshot_started) * 1000.0, 4)
            snapshot["stale_market_data"] = False
            return {
                "symbol": symbol,
                "interval": interval,
                "stale": False,
                "snapshot": snapshot,
                "candles": self._frame_to_output_records(frame),
                "metrics": {
                    "source": "live",
                    "fetch_ms": fetch_ms,
                    "cache_load_ms": None,
                    "persist_ms": persist_ms,
                    "snapshot_build_ms": snapshot_ms,
                    "total_ms": round((time.perf_counter() - started) * 1000.0, 4),
                    **persist_meta,
                },
            }
        except Exception as exc:
            cache_started = time.perf_counter()
            cached = self._load_cached(symbol, interval, limit)
            cache_ms = round((time.perf_counter() - cache_started) * 1000.0, 4)
            if not cached:
                raise RuntimeError(f"Failed to fetch candles for {symbol} {interval}: {exc}") from exc
            frame = _records_to_frame(cached)
            snapshot_started = time.perf_counter()
            snapshot = dict(self.snapshot_builder(frame))
            snapshot_ms = round((time.perf_counter() - snapshot_started) * 1000.0, 4)
            snapshot["stale_market_data"] = True
            snapshot["market_data_error"] = str(exc)
            return {
                "symbol": symbol,
                "interval": interval,
                "stale": True,
                "snapshot": snapshot,
                "candles": cached,
                "metrics": {
                    "source": "cache",
                    "fetch_ms": None,
                    "cache_load_ms": cache_ms,
                    "persist_ms": 0.0,
                    "snapshot_build_ms": snapshot_ms,
                    "total_ms": round((time.perf_counter() - started) * 1000.0, 4),
                    "write_skipped": True,
                    "rows_written": 0,
                },
            }

    def _persist_frame(self, symbol: str, interval: str, frame: pd.DataFrame, stale: bool) -> dict[str, Any]:
        records = frame.to_dict(orient="records")
        payloads = [_candle_row_to_payload(symbol, interval, row, stale=stale) for row in records]
        with session_scope() as session:
            return self.candle_repo.replace_symbol_interval(session, symbol, interval, payloads)

    def _load_cached(self, symbol: str, interval: str, limit: int) -> list[dict[str, Any]]:
        with session_scope() as session:
            rows = self.candle_repo.list_candles(session, symbol, interval, limit)
        return rows[-limit:] if rows else []

    @staticmethod
    def _frame_to_output_records(frame: pd.DataFrame) -> list[dict[str, Any]]:
        records = []
        for row in frame.to_dict(orient="records"):
            records.append({
                "open_time_utc": pd.Timestamp(row["open_time"]).isoformat(),
                "close_time_utc": pd.Timestamp(row.get("close_time") or row["open_time"]).isoformat(),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row.get("volume", 0.0)),
                "stale": False,
            })
        return records
