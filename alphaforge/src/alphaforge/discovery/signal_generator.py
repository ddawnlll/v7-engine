"""Trade signal generator — converts model predictions into trade signals.

Takes a trained model's OOS predictions (from walk-forward validation) and
the aligned OHLCV data, then produces structured TradeSignal objects ready
for the simulation engine.

The signal generator answers: "Given what the model predicted, what trades
should we attempt, and at what prices/levels?"

It does NOT run the simulation engine — that is Phase 3's responsibility.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

from alphaforge.discovery import TradeSignal
from lib.config_training import TrainingConfig

logger = logging.getLogger("alphaforge.discovery.signal_generator")

# ATR computation period (matches train._generate_labels_numba)
_ATR_PERIOD = 14


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_trade_signals(
    fold_results: list[dict],
    fold_preds: list[np.ndarray],
    fold_y_class: list[np.ndarray],
    ohlcv: dict,
    mode_cfg: TrainingConfig,
    timestamps: np.ndarray,
    symbols: np.ndarray,
    close_arr: np.ndarray | None = None,
    confidence_threshold: float = 0.55,
    min_edge_r: float | None = None,
) -> list[TradeSignal]:
    """Generate trade signals from walk-forward OOS predictions.

    For each fold's validation window, extracts the model's OOS predictions.
    Where the prediction is LONG_NOW or SHORT_NOW with confidence above
    *confidence_threshold*, builds a TradeSignal with entry-price context.

    Parameters
    ----------
    fold_results:
        Per-fold result dicts from walk_forward_validate().  Each must contain
        ``val_start``, ``val_end``, and ``effective_val_start``.
    fold_preds:
        Per-fold max-softmax arrays (from walk_forward_validate with
        ``return_raw_preds=True``).
    fold_y_class:
        Per-fold argmax prediction arrays (same source).
    ohlcv:
        OHLCV data dict with keys ``close``, ``high``, ``low``, ``open``,
        ``volume`` (concatenated per-symbol, same length as training frame).
    mode_cfg:
        TrainingConfig from ``load_training_config(mode)`` — provides
        ``stop_multiplier``, ``target_multiplier``, ``max_holding_bars``,
        ``min_action_edge_r``.
    timestamps:
        Aligned timestamps array from the training frame (same length as
        feature matrix rows).
    symbols:
        Aligned symbols array from the training frame (same length).
    close_arr:
        Pre-extracted close prices aligned with the training frame
        (falls back to ``ohlcv['close']`` if not provided).
    confidence_threshold:
        Minimum softmax probability for a directional trade.
    min_edge_r:
        Minimum edge in R for a signal to be actionable.  Defaults to
        ``mode_cfg.min_action_edge_r``.
    Returns
    -------
    list[TradeSignal]
        One entry per qualifying OOS prediction, ordered by fold then bar.
    """
    if min_edge_r is None:
        min_edge_r = mode_cfg.min_action_edge_r

    stop_mult = mode_cfg.stop_multiplier
    target_mult = mode_cfg.target_multiplier
    max_hold = mode_cfg.max_holding_bars

    use_close = close_arr if close_arr is not None else ohlcv["close"]
    high_arr = ohlcv["high"].astype(np.float64)
    low_arr = ohlcv["low"].astype(np.float64)

    # Pre-compute per-symbol ATR lookup: symbol -> (timestamps, atr_values)
    # This avoids the interleaved-symbol scanning issue
    _atr_lookup = _build_atr_lookup(ohlcv, symbols, _ATR_PERIOD)

    signals: list[TradeSignal] = []

    for fold_idx, fold_res in enumerate(fold_results):
        val_start = fold_res.get("val_start", 0)
        val_end = fold_res.get("val_end", 0)
        eff_start = fold_res.get("effective_val_start", val_start)

        if eff_start >= val_end:
            continue

        preds = fold_preds[fold_idx] if fold_idx < len(fold_preds) else np.array([])
        y_class = fold_y_class[fold_idx] if fold_idx < len(fold_y_class) else np.array([])

        n_val = val_end - eff_start
        if len(preds) != n_val or len(y_class) != n_val:
            logger.warning(
                "Fold %d: preds len %d != val window %d",
                fold_idx + 1, len(preds), n_val,
            )
            continue

        # Walk the validation window
        for local_idx in range(n_val):
            global_idx = eff_start + local_idx

            if global_idx >= len(use_close) or global_idx >= len(timestamps):
                continue

            # Skip NO_TRADE predictions (class 2)
            action_class = int(y_class[local_idx])
            if action_class == 2:
                continue

            # Check confidence threshold
            prob = float(preds[local_idx])
            if prob < confidence_threshold:
                continue

            # Determine side
            side = "LONG" if action_class == 0 else "SHORT"

            # Get entry OHLCV data
            entry_price = float(use_close[global_idx])
            if not np.isfinite(entry_price) or entry_price <= 0:
                continue

            sym = str(symbols[global_idx]) if global_idx < len(symbols) else ""
            ts = int(timestamps[global_idx]) if global_idx < len(timestamps) else 0

            # Look up ATR from pre-computed per-symbol lookup
            atr = None
            if sym in _atr_lookup:
                _atr_ts_list, _atr_val_list = _atr_lookup[sym]
                # Find the ATR value at or just before this timestamp
                _ts_idx = np.searchsorted(_atr_ts_list, ts, side="right") - 1
                if _ts_idx >= 0:
                    atr = float(_atr_val_list[_ts_idx])
            if atr is None or not np.isfinite(atr) or atr <= 0:
                continue
            if atr > entry_price * 0.5:
                continue  # degenerate ATR

            # Compute stop/target levels
            stop_dist = atr * stop_mult
            target_dist = atr * target_mult

            if side == "LONG":
                stop_price = entry_price - stop_dist
                target_price = entry_price + target_dist
                initial_risk = stop_dist
            else:
                stop_price = entry_price + stop_dist
                target_price = entry_price - target_dist
                initial_risk = stop_dist

            if initial_risk <= 0:
                continue

            # Build signal
            signal = TradeSignal(
                bar_index=global_idx,
                timestamp=ts,
                symbol=sym,
                side=side,
                entry_price=entry_price,
                atr=atr,
                stop_price=stop_price,
                target_price=target_price,
                confidence=prob,
                model_score=prob,
                initial_risk=initial_risk,
            )
            signals.append(signal)

    logger.info(
        "Generated %d trade signals from %d folds (threshold=%.2f)",
        len(signals), len(fold_results), confidence_threshold,
    )
    return signals


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_atr_lookup(
    ohlcv: dict,
    symbols: np.ndarray,
    period: int = 14,
) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Build per-symbol ATR lookup table.

    Returns {symbol: (timestamps_array, atr_array)}.
    ATR is computed per symbol on its own contiguous bars, so the computation
    is correct even when the training frame interleaves symbols.
    """
    close_arr = ohlcv["close"].astype(np.float64)
    high_arr = ohlcv["high"].astype(np.float64)
    low_arr = ohlcv["low"].astype(np.float64)
    ts_arr = np.array(ohlcv.get("timestamp", np.arange(len(close_arr))), dtype=np.int64)
    sym_arr = np.array([str(s) for s in ohlcv.get("symbol", [])], dtype=object)

    lookup: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    unique_syms = np.unique(sym_arr)

    for sym in unique_syms:
        mask = sym_arr == sym
        idx = np.where(mask)[0]
        n = len(idx)
        if n < period + 2:
            continue
        c = close_arr[idx]
        h = high_arr[idx]
        l = low_arr[idx]
        t = ts_arr[idx]

        # Compute true range for each candle (TR[i] uses close[i-1])
        tr = np.zeros(n, dtype=np.float64)
        tr[0] = h[0] - l[0]  # first bar: no prior close
        for i in range(1, n):
            tr[i] = max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))

        # ATR = simple moving average of TR
        atr = np.full(n, np.nan, dtype=np.float64)
        for i in range(period - 1, n):
            atr[i] = np.mean(tr[i - period + 1:i + 1])

        lookup[sym] = (t, atr)

    return lookup


def _compute_atr_at_index(
    close: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    symbols: np.ndarray,
    target_symbol: str,
    global_idx: int,
    period: int = 14,
) -> float | None:
    """Compute ATR at *global_idx* for *target_symbol*.

    Scans backward in the concatenated array to find *period* bars belonging
    to the same symbol, then computes ATR as the mean of |high - low| (a
    simplified true-range approximation).

    NOTE: This function assumes the array is contiguous per symbol (not
    interleaved).  For interleaved arrays, use _build_atr_lookup instead.
    """
    symbol_bars = []
    idx = global_idx
    while idx >= 0 and str(symbols[idx]) == target_symbol and len(symbol_bars) < period + 1:
        symbol_bars.append(idx)
        idx -= 1

    if len(symbol_bars) < period + 1:
        return None

    symbol_bars.reverse()
    tr_values = []
    for i in range(1, len(symbol_bars)):
        bi = symbol_bars[i]
        tr = max(
            high[bi] - low[bi],
            abs(high[bi] - close[bi - 1]),
            abs(low[bi] - close[bi - 1]),
        )
        tr_values.append(tr)

    if not tr_values:
        return None

    return float(np.mean(tr_values[-period:]))


def filter_overlapping_signals(signals: list[TradeSignal]) -> list[TradeSignal]:
    """Remove overlapping signals on the same symbol.

    If multiple signals fire for the same symbol in a row (model predicts
    LONG on consecutive bars), only the first is kept.  This prevents
    stacking multiple positions on the same symbol.
    """
    if not signals:
        return []

    # Sort by symbol then timestamp
    sorted_sigs = sorted(signals, key=lambda s: (s.symbol, s.timestamp))
    filtered: list[TradeSignal] = [sorted_sigs[0]]

    for sig in sorted_sigs[1:]:
        prev = filtered[-1]
        if sig.symbol == prev.symbol:
            # Skip if same symbol and within max_hold of the previous signal
            if sig.bar_index - prev.bar_index < 10:  # heuristic min gap
                continue
        filtered.append(sig)

    return filtered
