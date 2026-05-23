"""Hypothesis 3: Funding + Spot Divergence.

When funding rate is high (> 0.1% per 8h) but spot price isn't rising,
longs are paying to hold but price momentum is failing → predicts short-term
downward move.
"""

import logging
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from ..config import (
    FUNDING_DIVERGENCE_FUNDING_THRESHOLDS, FUNDING_DIVERGENCE_SPOT_THRESHOLDS,
    FUNDING_DIVERGENCE_HOLD_DURATIONS_H, FUNDING_DIVERGENCE_MAX_HOLD_H,
    STOP_LOSS_PCT, TAKE_PROFIT_PCT,
    START_DATE, END_DATE,
)
from ..engine import WalkForwardEngine, run_baselines
from ..utils import save_csv, save_json, save_text
from ..data import download_klines, download_funding_rate

logger = logging.getLogger(__name__)


# ── Data availability check ──────────────────────────────────────────────────

def check_funding_data_available(symbols: List[str]) -> bool:
    """Check if historical funding rate data is accessible via Binance API.

    Returns True if at least 10 symbols have non-empty funding history.
    """
    logger.info("Checking funding rate data availability...")
    count_ok = 0
    for sym in symbols[:20]:  # Check first 20 symbols
        try:
            df = download_funding_rate(sym, start=START_DATE, end=END_DATE)
            if df is not None and len(df) > 10:
                count_ok += 1
                logger.info(f"  {sym}: {len(df)} funding records OK")
        except Exception as e:
            logger.warning(f"  {sym}: funding data FAILED - {e}")

        if count_ok >= 10:
            break

    available = count_ok >= 10
    logger.info(f"Funding data {'AVAILABLE' if available else 'NOT AVAILABLE'} "
                f"({count_ok}/10 symbols have data)")
    return available


# ── Parameter grid ───────────────────────────────────────────────────────────

def build_param_grid() -> List[dict]:
    """Build parameter grid for Hypothesis 3."""
    grid = []
    for fund_thresh in FUNDING_DIVERGENCE_FUNDING_THRESHOLDS:
        for spot_thresh in FUNDING_DIVERGENCE_SPOT_THRESHOLDS:
            for hold_dur in FUNDING_DIVERGENCE_HOLD_DURATIONS_H:
                grid.append({
                    "funding_threshold": fund_thresh,
                    "spot_threshold": spot_thresh,
                    "hold_duration_h": hold_dur,
                })
    return grid


# ── Signal generation ────────────────────────────────────────────────────────

def funding_divergence_signal(
    df: pd.DataFrame,
    symbol: str,
    params: dict,
    funding_data: Optional[pd.DataFrame] = None,
) -> List[dict]:
    """Generate funding + spot divergence signals.

    Improvements over the original:
      - Only fires at funding interval boundaries (every 8h) to avoid spamming.
      - Requires funding persistence: the threshold must be exceeded for 2+
        consecutive funding periods before a signal triggers.
      - Uses proper 4h spot return aligned to the funding timestamp.

    funding_data: DataFrame with timestamp, funding_rate for the symbol.
    """
    if funding_data is None or funding_data.empty:
        return []

    fund_thresh = params["funding_threshold"]
    spot_thresh = params["spot_threshold"]
    freq_h = _infer_freq(df)

    # Build a set of funding interval timestamps (every 8h boundaries)
    # from the funding_data, so we only fire signals at those points.
    fund_times = set(funding_data["timestamp"].dt.floor("h").values)

    # Align funding data to kline timestamps
    fund_aligned = funding_data.set_index("timestamp").reindex(
        df["timestamp"], method="ffill"
    ).reset_index()

    df = df.copy()
    df["funding_rate"] = fund_aligned["funding_rate"].values

    # Track consecutive funding periods above threshold
    # Funding changes every 8h ≈ 8 bars on 1h chart
    fund_interval_bars = max(1, int(8 / freq_h)) if freq_h > 0 else 1
    df["fund_above_thresh"] = df["funding_rate"].abs() > fund_thresh
    df["fund_persistence"] = (
        df["fund_above_thresh"]
        .astype(int)
        .rolling(fund_interval_bars * 2)  # 2 consecutive funding periods
        .sum()
    )

    # Compute 4h spot return
    lookback = max(1, int(4 / freq_h) if freq_h > 0 else 4)
    df["spot_4h_return"] = df["close"].pct_change(lookback)

    signals = []

    for i in range(lookback, len(df)):
        # Only fire at funding interval boundaries
        ts = df["timestamp"].iloc[i]
        if ts not in fund_times:
            # Also check nearby bars if exact match fails (timezone rounding)
            nearby = pd.Timestamp(ts).floor("h")
            if nearby not in fund_times:
                continue

        fund_rate = df["funding_rate"].iloc[i]
        spot_ret = df["spot_4h_return"].iloc[i]
        persistence = df["fund_persistence"].iloc[i]

        # Require persistence: funding has been above threshold for
        # at least 2 consecutive funding periods
        if persistence < fund_interval_bars * 2:
            continue

        # Divergence: high funding but spot not following
        if fund_rate > fund_thresh and spot_ret < spot_thresh:
            signals.append({
                "entry_idx": i,
                "direction": -1,
                "reason": "high_funding_flat_spot",
            })
        elif fund_rate < -fund_thresh and spot_ret > -spot_thresh:
            signals.append({
                "entry_idx": i,
                "direction": 1,
                "reason": "low_funding_flat_spot",
            })

    return signals


def _infer_freq(df: pd.DataFrame) -> float:
    if len(df) < 2:
        return 1.0
    delta = (df["timestamp"].iloc[1] - df["timestamp"].iloc[0]).total_seconds() / 3600
    return max(delta, 1.0)


# ── Data preparation ─────────────────────────────────────────────────────────

def prepare_data(
    symbols: List[str],
    interval: str = "1h",
) -> Dict[str, pd.DataFrame]:
    """Download spot klines and funding rates for all symbols.

    Returns dict of symbol -> DataFrame (including klines + aligned funding).
    """
    logger.info(f"Downloading funding + spot data for {len(symbols)} symbols...")

    data = {}
    for sym in symbols:
        try:
            # Get klines
            df = download_klines(sym, interval=interval)
            if df.empty:
                continue

            # Get funding rate (8h frequency)
            fund_df = download_funding_rate(sym, start=START_DATE, end=END_DATE)
            if fund_df.empty:
                logger.warning(f"  {sym}: no funding data, skipping")
                continue

            # Align funding to kline timestamps (forward fill)
            fund_ts = fund_df.set_index("timestamp")["funding_rate"]
            df = df.set_index("timestamp")
            df["funding_rate"] = fund_ts.reindex(df.index, method="ffill")
            df = df.reset_index()

            data[sym] = df

        except Exception as e:
            logger.warning(f"Failed to prepare {sym}: {e}")

    return data


# ── Run hypothesis ───────────────────────────────────────────────────────────

def run_hypothesis(
    symbols: List[str],
    interval: str = "1h",
) -> Dict:
    """Run full Hypothesis 3 validation.

    Returns dict with status: 'BLOCKED' or results.
    """
    logger.info("=" * 60)
    logger.info("HYPOTHESIS 3: Funding + Spot Divergence")
    logger.info("=" * 60)

    # ── Data availability check FIRST ──
    funding_ok = check_funding_data_available(symbols)
    if not funding_ok:
        decision = (
            "BLOCKED: Historical funding rate data not available via Binance free API. "
            "Cannot test Hypothesis 3 without funding rate history. "
            "Check if Binance futures API provides /fapi/v1/fundingRate with historical data. "
            "If only current rate is available, this hypothesis is UNTESTABLE."
        )
        logger.warning(decision)
        save_text(decision, "rejection_decision_funding_divergence.txt")
        return {
            "status": "BLOCKED",
            "reason": "Funding rate history not available",
            "decision": decision,
        }

    # ── Prepare data ──
    data = prepare_data(symbols, interval)
    if not data:
        decision = "BLOCKED: No symbols with complete funding + spot data"
        save_text(decision, "rejection_decision_funding_divergence.txt")
        return {"status": "BLOCKED", "reason": "No data"}

    param_grid = build_param_grid()

    engine = WalkForwardEngine(
        hypothesis_name="funding_divergence",
        signal_fn=lambda df, sym, params: funding_divergence_signal(
            df, sym, params,
            funding_data=data.get(sym, pd.DataFrame()),
        ),
        param_grid=param_grid,
        max_hold_hours=FUNDING_DIVERGENCE_MAX_HOLD_H,
        stop_pct=STOP_LOSS_PCT,
        tp_pct=TAKE_PROFIT_PCT,
    )

    results = engine.run(data)

    # ── Save deliverables ──
    trades_df = pd.DataFrame(engine.all_trades)
    save_csv(trades_df, "results_funding_divergence.csv")

    save_json(results, "stats_funding_divergence.json")

    baselines = run_baselines(data, "funding_divergence")
    save_json(baselines, "baseline_comparison_funding_divergence.json")

    save_json(engine.fold_results, "fold_results_funding_divergence.json")

    decision = _make_decision(results, baselines)
    save_text(decision, "rejection_decision_funding_divergence.txt")
    logger.info(f"Decision: {decision[:100]}...")

    return results


def _make_decision(results: dict, baselines: dict) -> str:
    """Formulate rejection decision."""
    directional_acc = results.get("win_rate", 0.0)
    median_r = results.get("median_r_multiple", 0.0)

    if directional_acc < 0.45:
        return (
            f"REJECTED: Directional accuracy {directional_acc:.1%} < 45% "
            f"(worse than coin flip)"
        )

    # Check if only works on BTC (too narrow)
    trades_df = pd.DataFrame()  # We'd need to track this
    # Placeholder check:
    total = results.get("total_signals", 0)
    regime_bd = results.get("regime_breakdown", {})
    regimes_with_trades = [r for r, v in regime_bd.items() if v["count"] > 0]

    return (
        f"ACCEPTED: Directional accuracy {directional_acc:.1%}, "
        f"median R-multiple {median_r:.3f}, "
        f"{len(regimes_with_trades)} regimes, {total} signals"
    )
