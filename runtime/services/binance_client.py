"""Binance public market data client for v4."""

from __future__ import annotations

from typing import Sequence

import pandas as pd
from datetime import datetime, timezone
import requests
from requests.adapters import HTTPAdapter

BINANCE_API_BASES = [
    "https://api.binance.com/api/v3",
    "https://api1.binance.com/api/v3",
    "https://api2.binance.com/api/v3",
    "https://api3.binance.com/api/v3",
]
INTERVALS = ["1m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d", "3d", "7d", "14d", "1M"]
POPULAR_PAIRS = [
    "BTCUSDT",
    "ETHUSDT",
    "BNBUSDT",
    "SOLUSDT",
    "XRPUSDT",
    "ADAUSDT",
    "DOGEUSDT",
    "AVAXUSDT",
    "LINKUSDT",
    "DOTUSDT",
    "MATICUSDT",
    "LTCUSDT",
    "UNIUSDT",
    "ATOMUSDT",
    "NEARUSDT",
]
TOP_100_USDT_PAIRS = [
    "BTCUSDT", "ETHUSDT", "XRPUSDT", "BNBUSDT", "SOLUSDT", "DOGEUSDT", "ADAUSDT", "TRXUSDT", "LINKUSDT", "AVAXUSDT",
    "XLMUSDT", "SUIUSDT", "TONUSDT", "HBARUSDT", "SHIBUSDT", "DOTUSDT", "BCHUSDT", "LTCUSDT", "PEPEUSDT", "APTUSDT",
    "UNIUSDT", "NEARUSDT", "AAVEUSDT", "ICPUSDT", "ETCUSDT", "MATICUSDT", "FILUSDT", "TAOUSDT", "RENDERUSDT", "ATOMUSDT",
    "OPUSDT", "ARBUSDT", "INJUSDT", "SEIUSDT", "FETUSDT", "TIAUSDT", "WIFUSDT", "ONDOUSDT", "JUPUSDT", "RUNEUSDT",
    "ALGOUSDT", "VETUSDT", "IMXUSDT", "ENAUSDT", "THETAUSDT", "BONKUSDT", "FTMUSDT", "GRTUSDT", "JASMYUSDT",
    "SANDUSDT", "MKRUSDT", "LDOUSDT", "FLOWUSDT", "EOSUSDT", "QNTUSDT", "PYTHUSDT", "STXUSDT", "EGLDUSDT", "BTTUSDT",
    "MANAUSDT", "XTZUSDT", "AXSUSDT", "WLDUSDT", "KAVAUSDT", "AIOZUSDT", "DYDXUSDT", "APEUSDT", "ZECUSDT", "ROSEUSDT",
    "CHZUSDT", "MINAUSDT", "COMPUSDT", "CFXUSDT", "CRVUSDT", "1INCHUSDT", "SNXUSDT", "LRCUSDT", "ENSUSDT", "BLURUSDT",
    "GMTUSDT", "CELOUSDT", "ZILUSDT", "MASKUSDT", "HOTUSDT", "IOTAUSDT", "ANKRUSDT", "DASHUSDT", "KSMUSDT", "CAKEUSDT",
    "RAYUSDT", "GMXUSDT", "YFIUSDT", "SUSHIUSDT", "WOOUSDT", "QTUMUSDT", "BATUSDT", "IOSTUSDT", "RSRUSDT", "IDUSDT",
]
UNSUPPORTED_SCAN_SYMBOLS = {"KASUSDT", "AIOZUSDT"}
DEFAULT_SCAN_SYMBOLS = [symbol for symbol in TOP_100_USDT_PAIRS if symbol not in UNSUPPORTED_SCAN_SYMBOLS][:100]
STABLE_BASE_ASSETS = {"USDT", "USDC", "FDUSD", "TUSD", "USDP", "DAI", "BUSD", "EUR", "TRY"}
EXCLUDED_SUFFIXES = ("UPUSDT", "DOWNUSDT", "BULLUSDT", "BEARUSDT")

SESSION = requests.Session()
SESSION.mount("https://", HTTPAdapter(pool_connections=32, pool_maxsize=32))


class BinanceBadSymbolError(RuntimeError):
    """Raised when Binance rejects a symbol request as invalid or unsupported."""


def sanitize_scan_symbols(symbols: Sequence[str], *, limit: int | None = None) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for symbol in symbols:
        normalized = str(symbol or "").strip().upper()
        if not normalized or normalized in UNSUPPORTED_SCAN_SYMBOLS or normalized in seen:
            continue
        seen.add(normalized)
        cleaned.append(normalized)
        if limit is not None and len(cleaned) >= limit:
            break
    return cleaned


def _request_json(path: str, *, params: dict | None = None, timeout: int = 10):
    last_error: Exception | None = None
    for base_url in BINANCE_API_BASES:
        try:
            response = SESSION.get(
                f"{base_url}{path}",
                params=params,
                timeout=timeout,
            )
            response.raise_for_status()
            return response.json()
        except requests.HTTPError as exc:
            status_code = exc.response.status_code if exc.response is not None else None
            if status_code is not None and 400 <= status_code < 500:
                raise BinanceBadSymbolError(
                    f"Binance rejected request for {params or {}} with status {status_code}"
                ) from exc
            last_error = exc
            continue
        except Exception as exc:
            last_error = exc
            continue
    if last_error is not None:
        raise last_error
    raise RuntimeError(f"no Binance API base configured for path {path}")


def _normalize_interval(interval: str) -> str:
    raw = str(interval or "1h").strip()
    if not raw:
        return "1h"
    if raw == "1M":
        return "1M"
    lowered = raw.lower()
    if lowered == "1w":
        return "1w"
    if lowered in {"1m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d", "3d", "7d", "14d"}:
        return lowered
    if lowered in {"1mo", "1month", "1mth"}:
        return "1M"
    if raw == "1M":
        return "1M"
    return raw


def _resample_multi_day(frame: pd.DataFrame, days: int, limit: int) -> pd.DataFrame:
    if frame.empty:
        return frame
    ordered = frame.sort_values("open_time").reset_index(drop=True)
    bucket_index = ordered.index // max(days, 1)
    grouped = ordered.groupby(bucket_index, sort=True)
    aggregated = grouped.agg(
        open_time=("open_time", "first"),
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
        trades=("trades", "sum"),
        quote_volume=("quote_volume", "sum"),
        taker_buy_base=("taker_buy_base", "sum"),
        taker_buy_quote=("taker_buy_quote", "sum"),
        close_time=("close_time", "last"),
    )
    return aggregated.tail(limit).reset_index(drop=True)


def _klines_rows_to_frame(raw: list) -> pd.DataFrame:
    frame = pd.DataFrame(
        raw,
        columns=[
            "open_time",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "close_time",
            "quote_volume",
            "trades",
            "taker_buy_base",
            "taker_buy_quote",
            "ignore",
        ],
    )
    if frame.empty:
        return frame
    frame["open_time"] = pd.to_datetime(frame["open_time"], unit="ms", utc=True)
    frame["close_time"] = pd.to_datetime(frame["close_time"], unit="ms", utc=True)
    for column in ("open", "high", "low", "close", "volume", "quote_volume"):
        frame[column] = frame[column].astype(float)
    frame["trades"] = frame["trades"].astype(int)
    frame["taker_buy_base"] = frame["taker_buy_base"].astype(float)
    frame["taker_buy_quote"] = frame["taker_buy_quote"].astype(float)
    return frame[["open_time", "open", "high", "low", "close", "volume", "trades", "quote_volume", "taker_buy_base", "taker_buy_quote", "close_time"]]


def _fetch_native_klines(symbol: str, interval: str, limit: int) -> pd.DataFrame:
    raw = _request_json(
        "/klines",
        params={"symbol": symbol.upper(), "interval": interval, "limit": limit},
        timeout=10,
    )
    return _klines_rows_to_frame(raw)


def _timestamp_ms(value: datetime) -> int:
    resolved = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    return int(resolved.timestamp() * 1000)


def fetch_klines_range(symbol: str, interval: str, start_time: datetime, end_time: datetime, limit: int = 1000) -> pd.DataFrame:
    normalized_interval = _normalize_interval(interval)
    rows: list = []
    cursor_ms = _timestamp_ms(start_time)
    end_ms = _timestamp_ms(end_time)
    page_limit = max(1, min(int(limit), 1000))
    while cursor_ms <= end_ms:
        page = _request_json(
            "/klines",
            params={
                "symbol": symbol.upper(),
                "interval": normalized_interval,
                "limit": page_limit,
                "startTime": cursor_ms,
                "endTime": end_ms,
            },
            timeout=15,
        )
        if not page:
            break
        rows.extend(page)
        last_open_ms = int(page[-1][0])
        next_cursor_ms = last_open_ms + 1
        if next_cursor_ms <= cursor_ms or len(page) < page_limit:
            break
        cursor_ms = next_cursor_ms
    frame = _klines_rows_to_frame(rows)
    if frame.empty:
        return frame
    return frame.drop_duplicates(subset=["open_time"]).sort_values("open_time").reset_index(drop=True)


def fetch_klines(symbol: str, interval: str = "1h", limit: int = 200) -> pd.DataFrame:
    normalized_interval = _normalize_interval(interval)
    requested_limit = max(1, int(limit))
    if normalized_interval == "7d":
        daily_frame = _fetch_native_klines(symbol, "1d", max(requested_limit * 7, 7))
        return _resample_multi_day(daily_frame, 7, requested_limit)
    if normalized_interval == "14d":
        daily_frame = _fetch_native_klines(symbol, "1d", max(requested_limit * 14, 14))
        return _resample_multi_day(daily_frame, 14, requested_limit)
    return _fetch_native_klines(symbol, normalized_interval, requested_limit)


def fetch_all_tickers(symbols: Sequence[str] | None = None) -> list[dict[str, float | int | str]]:
    wanted = set(symbols or POPULAR_PAIRS)
    rows = _request_json("/ticker/24hr", timeout=15)
    items: list[dict[str, float | int | str]] = []
    for row in rows:
        symbol = str(row["symbol"])
        if symbol not in wanted:
            continue
        items.append({
            "symbol": symbol,
            "price": float(row["lastPrice"]),
            "change_pct": float(row["priceChangePercent"]),
            "high_24h": float(row["highPrice"]),
            "low_24h": float(row["lowPrice"]),
            "volume_24h": float(row["volume"]),
            "quote_volume_24h": float(row["quoteVolume"]),
            "trades_24h": int(row["count"]),
        })
    return items


def fetch_exchange_info() -> dict[str, object]:
    return _request_json("/exchangeInfo", timeout=20)


def fetch_top_usdt_pairs(limit: int = 100) -> list[str]:
    """Return active spot USDT pairs ranked by recent quote volume.

    Binance exposes tradable symbols via ``/api/v3/exchangeInfo`` and rolling
    24-hour statistics via ``/api/v3/ticker/24hr``. We combine those feeds so
    the default watchlist and scan universe follow the live exchange instead of
    a stale hardcoded subset.
    """

    limit = max(1, min(int(limit), 200))
    try:
        exchange_info = fetch_exchange_info()
        tradable_symbols = {
            str(item["symbol"]): str(item.get("baseAsset", ""))
            for item in exchange_info.get("symbols", [])
            if str(item.get("status")) == "TRADING"
            and bool(item.get("isSpotTradingAllowed", True))
            and str(item.get("quoteAsset")) == "USDT"
        }
        response = SESSION.get(f"{BINANCE_API_BASES[0]}/ticker/24hr", timeout=20)
        response.raise_for_status()
        tickers = response.json()
        ranked: list[tuple[float, str]] = []
        for row in tickers:
            symbol = str(row.get("symbol", ""))
            if symbol not in tradable_symbols:
                continue
            if symbol.endswith(EXCLUDED_SUFFIXES):
                continue
            base_asset = tradable_symbols[symbol]
            if base_asset in STABLE_BASE_ASSETS:
                continue
            try:
                quote_volume = float(row.get("quoteVolume", 0.0) or 0.0)
            except (TypeError, ValueError):
                quote_volume = 0.0
            ranked.append((quote_volume, symbol))
        ranked.sort(key=lambda item: item[0], reverse=True)
        pairs = sanitize_scan_symbols([symbol for _volume, symbol in ranked], limit=limit)
        if pairs:
            return pairs
    except Exception:
        pass
    return list(DEFAULT_SCAN_SYMBOLS[:limit])


def fetch_ticker(symbol: str) -> dict[str, float | str]:
    row = _request_json(
        "/ticker/24hr",
        params={"symbol": symbol.upper()},
        timeout=10,
    )
    return {
        "symbol": str(row["symbol"]),
        "price": float(row["lastPrice"]),
        "change_pct": float(row["priceChangePercent"]),
        "high_24h": float(row["highPrice"]),
        "low_24h": float(row["lowPrice"]),
        "volume_24h": float(row["volume"]),
        "quote_volume_24h": float(row["quoteVolume"]),
        "trades_24h": int(row["count"]),
    }


def fetch_orderbook(symbol: str, limit: int = 20) -> dict[str, object]:
    row = _request_json(
        "/depth",
        params={"symbol": symbol.upper(), "limit": max(5, min(int(limit), 1000))},
        timeout=10,
    )
    return {
        "lastUpdateId": row.get("lastUpdateId"),
        "symbol": symbol.upper(),
        "bids": [[float(price), float(size)] for price, size in row.get("bids", [])],
        "asks": [[float(price), float(size)] for price, size in row.get("asks", [])],
    }
