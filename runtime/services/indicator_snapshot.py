"""Indicator snapshot builder without pandas_ta or v1 imports."""

from __future__ import annotations

from datetime import UTC
from typing import Any

import numpy as np
import pandas as pd


def _ema(series: pd.Series, length: int) -> pd.Series:
    return series.ewm(span=length, adjust=False).mean()


def _sma(series: pd.Series, length: int) -> pd.Series:
    return series.rolling(length, min_periods=1).mean()


def _rsi(close: pd.Series, length: int = 14) -> pd.Series:
    delta = close.diff()
    gains = delta.clip(lower=0.0)
    losses = -delta.clip(upper=0.0)
    avg_gain = gains.ewm(alpha=1 / length, adjust=False, min_periods=length).mean()
    avg_loss = losses.ewm(alpha=1 / length, adjust=False, min_periods=length).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50.0)


def _stochastic(high: pd.Series, low: pd.Series, close: pd.Series, length: int = 14, smooth: int = 3) -> tuple[pd.Series, pd.Series]:
    lowest = low.rolling(length, min_periods=1).min()
    highest = high.rolling(length, min_periods=1).max()
    denom = (highest - lowest).replace(0, np.nan)
    k = ((close - lowest) / denom * 100).fillna(50.0)
    d = k.rolling(smooth, min_periods=1).mean()
    return k, d


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, length: int = 14) -> pd.Series:
    previous_close = close.shift(1)
    tr = pd.concat(
        [
            (high - low),
            (high - previous_close).abs(),
            (low - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1 / length, adjust=False, min_periods=length).mean().bfill()


def _adx(high: pd.Series, low: pd.Series, close: pd.Series, length: int = 14) -> tuple[pd.Series, pd.Series, pd.Series]:
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0.0), index=high.index)
    minus_dm = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0.0), index=high.index)
    atr = _atr(high, low, close, length).replace(0, np.nan)
    plus_di = (100 * plus_dm.ewm(alpha=1 / length, adjust=False).mean() / atr).fillna(0.0)
    minus_di = (100 * minus_dm.ewm(alpha=1 / length, adjust=False).mean() / atr).fillna(0.0)
    dx = ((plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan) * 100).fillna(0.0)
    adx = dx.ewm(alpha=1 / length, adjust=False, min_periods=length).mean().fillna(0.0)
    return adx, plus_di, minus_di


def _ultimate_oscillator(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    previous_close = close.shift(1).fillna(close)
    buying_pressure = close - pd.concat([low, previous_close], axis=1).min(axis=1)
    true_range = pd.concat([high, previous_close], axis=1).max(axis=1) - pd.concat([low, previous_close], axis=1).min(axis=1)
    avg7 = buying_pressure.rolling(7, min_periods=1).sum() / true_range.rolling(7, min_periods=1).sum().replace(0, np.nan)
    avg14 = buying_pressure.rolling(14, min_periods=1).sum() / true_range.rolling(14, min_periods=1).sum().replace(0, np.nan)
    avg28 = buying_pressure.rolling(28, min_periods=1).sum() / true_range.rolling(28, min_periods=1).sum().replace(0, np.nan)
    return (100 * (4 * avg7 + 2 * avg14 + avg28) / 7).fillna(50.0)


def _session_label(timestamp: pd.Timestamp | None) -> tuple[str | None, float | None]:
    if timestamp is None:
        return None, None
    hour = timestamp.tz_convert(UTC).hour if timestamp.tzinfo else timestamp.hour
    if 7 <= hour < 12:
        return "LONDON", 0.9
    if 12 <= hour < 16:
        return "LONDON_NEW_YORK_OVERLAP", 1.0
    if 16 <= hour < 21:
        return "NEW_YORK", 0.95
    if 0 <= hour < 7:
        return "ASIA", 0.65
    return "OFF_HOURS", 0.5


def _swing_levels(frame: pd.DataFrame, lookback: int = 50, order: int = 5) -> dict[str, Any]:
    if len(frame) < max(lookback // 2, order * 2 + 1):
        return {
            "recent_high": None,
            "recent_low": None,
            "swing_highs": [],
            "swing_lows": [],
            "near_resistance": False,
            "near_support": False,
            "breakout_up": False,
            "breakout_down": False,
            "retest_support": False,
            "retest_resist": False,
            "dist_to_resist": None,
            "dist_to_support": None,
            "bullish_sweep": False,
            "bearish_sweep": False,
        }

    window = frame.tail(lookback).copy()
    price = float(window["close"].iloc[-1])
    previous_close = float(window["close"].iloc[-2]) if len(window) > 1 else price
    highs = window["high"].to_numpy()
    lows = window["low"].to_numpy()

    swing_highs: list[float] = []
    swing_lows: list[float] = []
    for index in range(order, len(window) - order):
        if highs[index] == np.max(highs[index - order:index + order + 1]):
            swing_highs.append(float(highs[index]))
        if lows[index] == np.min(lows[index - order:index + order + 1]):
            swing_lows.append(float(lows[index]))

    def cluster(levels: list[float]) -> list[float]:
        if not levels:
            return []
        sorted_levels = sorted(set(levels))
        groups: list[list[float]] = [[sorted_levels[0]]]
        for value in sorted_levels[1:]:
            if (value - groups[-1][-1]) / groups[-1][-1] < 0.003:
                groups[-1].append(value)
            else:
                groups.append([value])
        return [sum(group) / len(group) for group in groups]

    clustered_highs = cluster(swing_highs)
    clustered_lows = cluster(swing_lows)
    resistance = sorted([value for value in clustered_highs if value > price])
    support = sorted([value for value in clustered_lows if value < price], reverse=True)
    recent_high = resistance[0] if resistance else None
    recent_low = support[0] if support else None
    proximity = 0.005
    near_resistance = recent_high is not None and (recent_high - price) / price < proximity
    near_support = recent_low is not None and (price - recent_low) / price < proximity
    breakout_up = any(previous_close < level <= price for level in clustered_highs)
    breakout_down = any(previous_close > level >= price for level in clustered_lows)
    latest_low = float(window["low"].iloc[-1])
    latest_high = float(window["high"].iloc[-1])
    bullish_sweep = recent_low is not None and latest_low < recent_low and price > recent_low
    bearish_sweep = recent_high is not None and latest_high > recent_high and price < recent_high
    return {
        "recent_high": recent_high,
        "recent_low": recent_low,
        "swing_highs": resistance[:3],
        "swing_lows": support[:3],
        "near_resistance": near_resistance,
        "near_support": near_support,
        "breakout_up": breakout_up,
        "breakout_down": breakout_down,
        "retest_support": breakout_up and near_support,
        "retest_resist": breakout_down and near_resistance,
        "dist_to_resist": round((recent_high - price) / price * 100, 3) if recent_high else None,
        "dist_to_support": round((price - recent_low) / price * 100, 3) if recent_low else None,
        "bullish_sweep": bullish_sweep,
        "bearish_sweep": bearish_sweep,
    }


def _safe_number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if np.isnan(number) or np.isinf(number):
        return None
    return round(number, 6)


def _safe_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def enrich_snapshot_with_orderbook(snapshot: dict[str, Any], orderbook: dict[str, Any] | None) -> dict[str, Any]:
    if not orderbook:
        return snapshot

    bids = orderbook.get("bids") or []
    asks = orderbook.get("asks") or []
    if not bids or not asks:
        return snapshot

    try:
        best_bid = float(bids[0][0])
        best_ask = float(asks[0][0])
    except (TypeError, ValueError, IndexError):
        return snapshot

    mid = (best_bid + best_ask) / 2 if (best_bid + best_ask) > 0 else 0.0
    bid_depth = sum(float(level[1]) for level in bids[:10] if len(level) >= 2)
    ask_depth = sum(float(level[1]) for level in asks[:10] if len(level) >= 2)
    total_depth = bid_depth + ask_depth
    imbalance = ((bid_depth - ask_depth) / total_depth) if total_depth > 0 else 0.0
    spread_bps = ((best_ask - best_bid) / mid * 10000) if mid > 0 else 0.0
    microprice = ((best_ask * bid_depth) + (best_bid * ask_depth)) / total_depth if total_depth > 0 else mid
    microprice_deviation_bps = ((microprice - mid) / mid * 10000) if mid > 0 else 0.0

    snapshot.update({
        "best_bid": _safe_number(best_bid),
        "best_ask": _safe_number(best_ask),
        "orderbook_spread_bps": _safe_number(spread_bps),
        "orderbook_bid_depth": _safe_number(bid_depth),
        "orderbook_ask_depth": _safe_number(ask_depth),
        "orderbook_imbalance": _safe_number(imbalance),
        "orderbook_microprice_deviation_bps": _safe_number(microprice_deviation_bps),
        "microstructure_source": "orderbook",
    })
    return snapshot


def build_indicator_snapshot(frame: pd.DataFrame) -> dict[str, Any]:
    if frame.empty:
        raise ValueError("Cannot build indicator snapshot from an empty frame.")

    working = frame.copy()
    if "open_time" in working.columns:
        working["open_time"] = pd.to_datetime(working["open_time"], utc=True)
        working = working.sort_values("open_time").reset_index(drop=True)
    else:
        working["open_time"] = pd.date_range(end=pd.Timestamp.now(tz=UTC), periods=len(working), freq="min")

    if "close_time" not in working.columns:
        working["close_time"] = working["open_time"]

    close = working["close"].astype(float)
    high = working["high"].astype(float)
    low = working["low"].astype(float)
    volume = working["volume"].astype(float)
    trades = working["trades"].astype(float) if "trades" in working.columns else pd.Series(0.0, index=working.index)
    quote_volume = working["quote_volume"].astype(float) if "quote_volume" in working.columns else pd.Series(0.0, index=working.index)
    taker_buy_base = working["taker_buy_base"].astype(float) if "taker_buy_base" in working.columns else volume * 0.5
    taker_buy_quote = working["taker_buy_quote"].astype(float) if "taker_buy_quote" in working.columns else quote_volume * 0.5

    working["ema_9"] = _ema(close, 9)
    working["ema_21"] = _ema(close, 21)
    working["ema_50"] = _ema(close, 50)
    working["ema_200"] = _ema(close, 200)
    working["sma_20"] = _sma(close, 20)
    working["rsi"] = _rsi(close, 14)
    working["rsi_slope"] = working["rsi"].diff(3)

    working["macd"] = _ema(close, 12) - _ema(close, 26)
    working["macd_signal"] = _ema(working["macd"], 9)
    working["macd_hist"] = working["macd"] - working["macd_signal"]
    working["macd_hist_delta"] = working["macd_hist"].diff()

    working["stoch_k"], working["stoch_d"] = _stochastic(high, low, close)
    rsi_min = working["rsi"].rolling(14, min_periods=1).min()
    rsi_max = working["rsi"].rolling(14, min_periods=1).max()
    stochrsi = ((working["rsi"] - rsi_min) / (rsi_max - rsi_min).replace(0, np.nan) * 100).fillna(50.0)
    working["stochrsi_k"] = stochrsi.rolling(3, min_periods=1).mean()
    working["stochrsi_d"] = working["stochrsi_k"].rolling(3, min_periods=1).mean()

    working["bb_mid"] = _sma(close, 20)
    working["bb_std"] = close.rolling(20, min_periods=1).std().fillna(0.0)
    working["bb_upper"] = working["bb_mid"] + 2 * working["bb_std"]
    working["bb_lower"] = working["bb_mid"] - 2 * working["bb_std"]
    working["bb_width"] = ((working["bb_upper"] - working["bb_lower"]) / working["bb_mid"].replace(0, np.nan) * 100).fillna(0.0)
    working["atr"] = _atr(high, low, close)
    working["atr_5bar_avg"] = working["atr"].rolling(5, min_periods=1).mean().bfill()
    working["atr_expanding"] = (working["atr"] > working["atr_5bar_avg"]).fillna(False)

    adx, dmp, dmn = _adx(high, low, close)
    working["adx"] = adx
    working["dmp"] = dmp
    working["dmn"] = dmn

    typical_price = (high + low + close) / 3.0
    mad = typical_price.rolling(20, min_periods=1).apply(lambda values: np.mean(np.abs(values - np.mean(values))), raw=True)
    working["cci"] = ((typical_price - typical_price.rolling(20, min_periods=1).mean()) / (0.015 * mad.replace(0, np.nan))).fillna(0.0)
    median_price = (high + low) / 2.0
    working["ao"] = _sma(median_price, 5) - _sma(median_price, 34)
    working["mom"] = close.diff(10).fillna(0.0)
    highest14 = high.rolling(14, min_periods=1).max()
    lowest14 = low.rolling(14, min_periods=1).min()
    working["willr"] = (-100 * (highest14 - close) / (highest14 - lowest14).replace(0, np.nan)).fillna(-50.0)
    working["uo"] = _ultimate_oscillator(high, low, close)
    ema13 = _ema(close, 13)
    working["bbp"] = (high - ema13) + (low - ema13)

    cumulative_volume = volume.cumsum().replace(0, np.nan)
    working["vwap"] = ((typical_price * volume).cumsum() / cumulative_volume).fillna(close)
    direction = np.sign(close.diff().fillna(0.0))
    working["obv"] = (direction * volume).cumsum()
    working["obv_slope"] = working["obv"].diff(5).fillna(0.0)
    working["vol_sma_20"] = _sma(volume, 20).replace(0, np.nan)
    working["vol_ratio"] = (volume / working["vol_sma_20"]).replace([np.inf, -np.inf], np.nan).fillna(1.0)
    working["vol_slope"] = working["vol_ratio"].rolling(5, min_periods=2).apply(
        lambda values: np.polyfit(range(len(values)), values, 1)[0] if len(values) >= 2 else 0.0,
        raw=True,
    ).fillna(0.0)
    working["price_vs_ema50"] = ((close - working["ema_50"]) / working["ema_50"].replace(0, np.nan) * 100).fillna(0.0)
    working["price_vs_vwap"] = ((close - working["vwap"]) / working["vwap"].replace(0, np.nan) * 100).fillna(0.0)
    working["log_return"] = np.log(close / close.shift(1)).replace([np.inf, -np.inf], np.nan).fillna(0.0)
    working["mean_return_10"] = working["log_return"].rolling(10, min_periods=3).mean().fillna(0.0)
    working["mean_return_20"] = working["log_return"].rolling(20, min_periods=5).mean().fillna(0.0)
    working["realized_vol_10"] = working["log_return"].rolling(10, min_periods=5).std().fillna(0.0)
    working["realized_vol_20"] = working["log_return"].rolling(20, min_periods=8).std().fillna(0.0)
    working["realized_vol_50"] = working["log_return"].rolling(50, min_periods=20).std().fillna(0.0)
    working["return_skew_20"] = working["log_return"].rolling(20, min_periods=8).skew().fillna(0.0)
    working["return_kurtosis_20"] = working["log_return"].rolling(20, min_periods=8).kurt().replace([np.inf, -np.inf], np.nan).fillna(0.0)
    working["return_zscore"] = (
        working["log_return"] / working["realized_vol_20"].replace(0, np.nan)
    ).replace([np.inf, -np.inf], np.nan).fillna(0.0)
    working["vol_cluster_ratio"] = (
        working["realized_vol_10"] / working["realized_vol_50"].replace(0, np.nan)
    ).replace([np.inf, -np.inf], np.nan).fillna(1.0)
    working["return_trend_ratio"] = (
        working["mean_return_20"] / working["realized_vol_20"].replace(0, np.nan)
    ).replace([np.inf, -np.inf], np.nan).fillna(0.0)
    working["trades"] = trades
    working["quote_volume"] = quote_volume
    working["taker_buy_base"] = taker_buy_base
    working["taker_buy_quote"] = taker_buy_quote
    working["buy_volume_share"] = (taker_buy_base / volume.replace(0, np.nan)).clip(0.0, 1.0).fillna(0.5)
    working["sell_volume_share"] = (1.0 - working["buy_volume_share"]).clip(0.0, 1.0)
    working["flow_imbalance"] = ((taker_buy_base - (volume - taker_buy_base)) / volume.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan).fillna(0.0)
    working["trade_intensity"] = (trades / trades.rolling(20, min_periods=3).mean().replace(0, np.nan)).replace([np.inf, -np.inf], np.nan).fillna(1.0)
    working["avg_trade_notional"] = (quote_volume / trades.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan).fillna(0.0)

    latest = working.iloc[-1]
    row = working.iloc[-2] if len(working) > 1 else latest
    previous = working.iloc[-3] if len(working) > 2 else row
    session_label, liquidity_score = _session_label(pd.Timestamp(latest["open_time"]))
    structure = _swing_levels(working)
    vol_cluster_ratio = float(row.get("vol_cluster_ratio") or 1.0)
    if vol_cluster_ratio >= 1.35:
        volatility_regime = "EXPANDING"
    elif vol_cluster_ratio <= 0.75:
        volatility_regime = "CONTRACTING"
    else:
        volatility_regime = "STABLE"

    snapshot = {
        "price": _safe_number(latest["close"]),
        "open": _safe_number(row["open"]),
        "high": _safe_number(row["high"]),
        "low": _safe_number(row["low"]),
        "ema_9": _safe_number(row.get("ema_9")),
        "ema_21": _safe_number(row.get("ema_21")),
        "ema_50": _safe_number(row.get("ema_50")),
        "ema_200": _safe_number(row.get("ema_200")),
        "rsi": _safe_number(row.get("rsi")),
        "rsi_slope": _safe_number(row.get("rsi_slope")),
        "macd": _safe_number(row.get("macd")),
        "macd_signal": _safe_number(row.get("macd_signal")),
        "macd_hist": _safe_number(row.get("macd_hist")),
        "macd_hist_delta": _safe_number(row.get("macd_hist_delta")),
        "stoch_k": _safe_number(row.get("stoch_k")),
        "stoch_d": _safe_number(row.get("stoch_d")),
        "stochrsi_k": _safe_number(row.get("stochrsi_k")),
        "stochrsi_d": _safe_number(row.get("stochrsi_d")),
        "bb_upper": _safe_number(row.get("bb_upper")),
        "bb_mid": _safe_number(row.get("bb_mid")),
        "bb_lower": _safe_number(row.get("bb_lower")),
        "bb_width": _safe_number(row.get("bb_width")),
        "atr": _safe_number(row.get("atr")),
        "atr_5bar_avg": _safe_number(row.get("atr_5bar_avg")),
        "atr_expanding": bool(row.get("atr_expanding")) if row.get("atr_expanding") is not None else None,
        "adx": _safe_number(row.get("adx")),
        "dmp": _safe_number(row.get("dmp")),
        "dmn": _safe_number(row.get("dmn")),
        "cci": _safe_number(row.get("cci")),
        "ao": _safe_number(row.get("ao")),
        "mom": _safe_number(row.get("mom")),
        "willr": _safe_number(row.get("willr")),
        "uo": _safe_number(row.get("uo")),
        "bbp": _safe_number(row.get("bbp")),
        "vwap": _safe_number(row.get("vwap")),
        "obv": _safe_number(row.get("obv")),
        "obv_slope": _safe_number(row.get("obv_slope")),
        "vol_ratio": _safe_number(row.get("vol_ratio")),
        "vol_slope": _safe_number(row.get("vol_slope")),
        "price_vs_ema50": _safe_number(row.get("price_vs_ema50")),
        "price_vs_vwap": _safe_number(row.get("price_vs_vwap")),
        "log_return": _safe_number(row.get("log_return")),
        "mean_return_10": _safe_number(row.get("mean_return_10")),
        "mean_return_20": _safe_number(row.get("mean_return_20")),
        "return_mean": _safe_number(row.get("mean_return_20")),
        "realized_vol_10": _safe_number(row.get("realized_vol_10")),
        "realized_vol_20": _safe_number(row.get("realized_vol_20")),
        "realized_vol_50": _safe_number(row.get("realized_vol_50")),
        "return_vol": _safe_number(row.get("realized_vol_20")),
        "return_skew_20": _safe_number(row.get("return_skew_20")),
        "return_skew": _safe_number(row.get("return_skew_20")),
        "return_kurtosis_20": _safe_number(row.get("return_kurtosis_20")),
        "return_kurt": _safe_number(row.get("return_kurtosis_20")),
        "return_zscore": _safe_number(row.get("return_zscore")),
        "return_trend_ratio": _safe_number(row.get("return_trend_ratio")),
        "vol_cluster_ratio": _safe_number(vol_cluster_ratio),
        "volatility_regime": _safe_text(volatility_regime),
        "buy_volume_share": _safe_number(row.get("buy_volume_share")),
        "sell_volume_share": _safe_number(row.get("sell_volume_share")),
        "flow_imbalance": _safe_number(row.get("flow_imbalance")),
        "trade_intensity": _safe_number(row.get("trade_intensity")),
        "avg_trade_notional": _safe_number(row.get("avg_trade_notional")),
        "microstructure_source": "candles",
        "_prev_macd": _safe_number(previous.get("macd")),
        "_prev_macd_sig": _safe_number(previous.get("macd_signal")),
        "_prev_stoch_k": _safe_number(previous.get("stoch_k")),
        "_price_5bar_change": _safe_number(((row["close"] - working.iloc[-6]["close"]) / working.iloc[-6]["close"] * 100) if len(working) >= 7 else 0.0),
        "_vol_5bar_avg": _safe_number(working["vol_ratio"].iloc[-6:-1].mean()) if len(working) >= 6 else 1.0,
        "strategy_version": "v4-native-market",
        "session_label": session_label,
        "session_liquidity_score": liquidity_score,
    }
    snapshot.update(structure)
    return snapshot
