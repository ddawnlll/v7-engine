"""Hypothesis 1: Altcoin Delay.

When BTC moves > threshold in 4h, altcoins follow with 1-4h delay.
"""

import logging
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from ..config import (
    ALTCOIN_DELAY_BTC_THRESHOLDS, ALTCOIN_DELAY_WINDOWS_H, ALTCOIN_DELAY_UNIVERSE_SIZES,
    ALTCOIN_DELAY_MAX_HOLD_H, STOP_LOSS_PCT, TAKE_PROFIT_PCT,
    KNOWN_DELISTED,
)
from ..engine import WalkForwardEngine, run_baselines
from ..utils import save_csv, save_json, save_text, compute_r_multiple
from ..data import download_klines

logger = logging.getLogger(__name__)


def build_param_grid() -> List[dict]:
    """Build parameter grid for Hypothesis 1 optimization."""
    grid = []
    for thresh in ALTCOIN_DELAY_BTC_THRESHOLDS:
        for delay in ALTCOIN_DELAY_WINDOWS_H:
            for universe_size in ALTCOIN_DELAY_UNIVERSE_SIZES:
                grid.append({
                    "btc_threshold": thresh,
                    "delay_window_h": delay,
                    "altcoin_universe_size": universe_size,
                })
    return grid


def altcoin_delay_signal(
    df: pd.DataFrame,
    symbol: str,
    params: dict,
    btc_data: Optional[pd.DataFrame] = None,
) -> List[dict]:
    """Generate altcoin delay signals with proper temporal alignment.

    Correct logic:
      1. At bar i, check if BTC just moved > threshold (BTC_4h_return > thresh).
      2. If yes, mark bar i as a "BTC move" event.
      3. Look forward `delay_bars` to bar `future_idx = i + delay_bars`.
      4. At `future_idx`, check if the altcoin has caught up to BTC's move.
         If altcoin return FROM bar i TO future_idx is smaller than BTC's move,
         the delay is still in effect → signal at future_idx.
    """
    if btc_data is None or btc_data.empty:
        return []

    threshold = params["btc_threshold"]
    delay_h = params["delay_window_h"]
    freq_h = _infer_freq(df)
    delay_bars = max(1, int(delay_h / freq_h)) if freq_h > 0 else 1
    lookback = max(1, int(4 / freq_h)) if freq_h > 0 else 4

    signals = []

    # Align BTC data to this symbol's timestamps (forward-fill)
    btc_aligned = btc_data.set_index("timestamp").reindex(
        df["timestamp"], method="ffill"
    ).reset_index()

    # BTC 4h return at each bar
    btc_close = btc_aligned["close"].values
    df = df.copy()
    df["btc_close"] = btc_close

    # Altcoin close
    alt_close = df["close"].values

    for i in range(lookback, len(df) - delay_bars):
        # BTC return over the last 4 bars (4h)
        btc_ret = (btc_close[i] - btc_close[i - lookback]) / btc_close[i - lookback]

        if abs(btc_ret) <= threshold:
            continue  # BTC didn't move enough

        # ── BTC moved at bar i. Now look forward by delay_bars. ──
        future_idx = i + delay_bars

        # Altcoin return from bar i to future_idx
        alt_ret_from_btc_move = (alt_close[future_idx] - alt_close[i]) / alt_close[i]

        # Also compute altcoin's own 4h return ending at future_idx
        # (to avoid catching a coin that already pumped on its own)
        alt_own_ret = (alt_close[future_idx] - alt_close[future_idx - lookback]) / alt_close[future_idx - lookback]

        if btc_ret > 0:
            # BTC went up → we expect altcoin to go up (with delay)
            # Only signal if altcoin hasn't already caught up
            if alt_ret_from_btc_move < btc_ret * 0.5:
                # Also check altcoin isn't already moving on its own
                if alt_own_ret < btc_ret:
                    signals.append({"entry_idx": future_idx, "direction": 1})
        else:
            # BTC went down → expect altcoin to go down
            if alt_ret_from_btc_move > btc_ret * 0.5:
                if alt_own_ret > btc_ret:
                    signals.append({"entry_idx": future_idx, "direction": -1})

    return signals


def _infer_freq(df: pd.DataFrame) -> float:
    if len(df) < 2:
        return 1.0
    delta = (df["timestamp"].iloc[1] - df["timestamp"].iloc[0]).total_seconds() / 3600
    return max(delta, 1.0)


def prepare_data(
    symbols: List[str],
    interval: str = "1h",
    btc_symbol: str = "BTCUSDT",
) -> Dict[str, pd.DataFrame]:
    """Download and prepare data for Hypothesis 1.

    Downloads BTC and altcoin klines. Returns dict of symbol -> DataFrame.
    """
    logger.info(f"Downloading data for {len(symbols)} symbols ({interval})...")

    # Download BTC data first
    btc_df = download_klines(btc_symbol, interval=interval)
    data = {btc_symbol: btc_df}

    # Download altcoin data
    for sym in symbols:
        if sym == btc_symbol:
            continue
        try:
            df = download_klines(sym, interval=interval)
            if not df.empty:
                data[sym] = df
        except Exception as e:
            logger.warning(f"Failed to download {sym}: {e}")

    return data, btc_df


def run_hypothesis(
    symbols: List[str],
    interval: str = "1h",
) -> Dict:
    """Run full Hypothesis 1 validation."""
    logger.info("=" * 60)
    logger.info("HYPOTHESIS 1: Altcoin Delay")
    logger.info("=" * 60)

    # Prepare data
    data, btc_df = prepare_data(symbols, interval)

    # Check for known delisted symbols in our universe (survivorship bias check)
    present_delisted = [s for s in symbols if s in KNOWN_DELISTED]
    if present_delisted:
        logger.info(f"  Including delisted symbols: {present_delisted}")

    param_grid = build_param_grid()

    engine = WalkForwardEngine(
        hypothesis_name="altcoin_delay",
        signal_fn=lambda df, sym, params: altcoin_delay_signal(df, sym, params, btc_df),
        param_grid=param_grid,
        max_hold_hours=ALTCOIN_DELAY_MAX_HOLD_H,
        stop_pct=STOP_LOSS_PCT,
        tp_pct=TAKE_PROFIT_PCT,
    )

    results = engine.run(data)

    # ── Save deliverables ──
    trades_df = pd.DataFrame(engine.all_trades)
    save_csv(trades_df, "results_altcoin_delay.csv")

    save_json(results, "stats_altcoin_delay.json")

    baselines = run_baselines(data, "altcoin_delay")
    save_json(baselines, "baseline_comparison_altcoin_delay.json")

    save_json(engine.fold_results, "fold_results_altcoin_delay.json")

    # Rejection decision
    decision = _make_decision(results, baselines)
    save_text(decision, "rejection_decision_altcoin_delay.txt")
    logger.info(f"Decision: {decision[:100]}...")

    return results


def _make_decision(results: dict, baselines: dict) -> str:
    """Formulate rejection decision based on results."""
    median_r = results.get("median_r_multiple", 0.0)
    total = results.get("total_signals", 0)
    n_folds = len(results.get("fold_results", []))

    if median_r < 1.0:
        return (
            f"REJECTED: Median R-multiple {median_r:.3f} < 1.0 "
            f"({total} signals across {n_folds} folds)"
        )

    regime_bd = results.get("regime_breakdown", {})
    regimes_with_trades = [r for r, v in regime_bd.items() if v["count"] > 0]
    if len(regimes_with_trades) < 2:
        return (
            f"REJECTED: Only works in {len(regimes_with_trades)} regime(s) "
            f"({regimes_with_trades}) — need 2+ regimes"
        )

    # Compare vs baselines (placeholder)
    hyp_r = baselines.get("hypothesis_r", median_r)
    rand_r = baselines.get("random_baseline_r", 0.0)
    if hyp_r <= rand_r:
        return f"REJECTED: Hypothesis R {hyp_r:.3f} <= Random baseline R {rand_r:.3f}"

    return (
        f"ACCEPTED: Median R-multiple {median_r:.3f} across {total} signals, "
        f"{len(regimes_with_trades)} regimes, {n_folds} folds"
    )
