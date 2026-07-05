#!/usr/bin/env python3
"""Backtest the 21-day momentum alpha factor."""
from __future__ import annotations
import json, logging, os, sys, time
from datetime import datetime, timezone
import numpy as np
import pandas as pd

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_af_src = os.path.join(PROJECT_ROOT, "alphaforge", "src")
for p in [PROJECT_ROOT, _af_src]:
    if p not in sys.path:
        sys.path.insert(0, p)

from alphaforge.alphas import AlphaMomentum
from alphaforge.factors.evaluation import compute_forward_returns, evaluate_factor

logger = logging.getLogger(__name__)
TRAIN_START = "2020-01-01"; TRAIN_END = "2022-12-31"
TEST_START = "2023-01-01"; TEST_END = "2024-12-31"
FULL_START = TRAIN_START; FULL_END = TEST_END
N_SYMBOLS = 20; ANNUAL_VOL = 0.30; TRADING_DAYS_PER_YEAR = 365
FORWARD_HORIZONS = [1, 5, 21]; ALPHA_WINDOW = 21

SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
    "ADAUSDT", "AVAXUSDT", "DOGEUSDT", "DOTUSDT", "LINKUSDT",
    "MATICUSDT", "NEARUSDT", "ATOMUSDT", "FILUSDT", "APTUSDT",
    "SUIUSDT", "OPUSDT", "ARBUSDT", "INJUSDT", "RUNEUSDT",
]

def gen_data(n_bars, n_symbols=20, symbols=None, seed=42):
    if symbols is None:
        symbols = SYMBOLS[:n_symbols]
    rng = np.random.RandomState(seed)
    date_idx = pd.date_range(start=FULL_START, end=FULL_END + "T23:59:59", freq="D")[:n_bars]
    common = rng.randn(n_bars) * (ANNUAL_VOL / np.sqrt(TRADING_DAYS_PER_YEAR))
    all_data = {c: {} for c in ["close", "open", "high", "low", "volume"]}
    for sym in symbols:
        sv = ANNUAL_VOL * rng.uniform(0.7, 1.3)
        sd = rng.normal(0.0, 0.0001)
        ret = sd + 0.6*common + 0.8*rng.randn(n_bars)*(sv/np.sqrt(TRADING_DAYS_PER_YEAR))
        ret = np.clip(ret, -0.15, 0.15)
        c = np.maximum(rng.uniform(10,500)*np.exp(np.cumsum(ret)), 0.01)
        o = c*(1+rng.uniform(-0.005,0.005,n_bars))
        h = np.maximum(o,c)*(1+rng.uniform(0,0.02,n_bars))
        l = np.minimum(o,c)*(1-rng.uniform(0,0.02,n_bars))
        l = np.minimum(l, np.minimum(o,c))
        h = np.maximum(h, np.maximum(o,c))
        v = rng.lognormal(12,1.5,n_bars)
        all_data["close"][sym]=c; all_data["open"][sym]=o
        all_data["high"][sym]=h; all_data["low"][sym]=l; all_data["volume"][sym]=v
    return {k: pd.DataFrame(v, index=date_idx) for k,v in all_data.items()}

def _to_native(obj):
    if isinstance(obj,dict): return {k:_to_native(v) for k,v in obj.items()}
    if isinstance(obj,list): return [_to_native(v) for v in obj]
    if isinstance(obj,np.integer): return int(obj)
    if isinstance(obj,np.floating): return float(obj)
    if isinstance(obj,np.bool_): return bool(obj)
    if isinstance(obj,np.ndarray): return obj.tolist()
    if isinstance(obj,pd.Timestamp): return str(obj)
    return obj

def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%H:%M:%S")
    log = logging.getLogger("backtest")
    log.info("="*60)
    log.info("Alpha Momentum Backtest")
    log.info("="*60)
    t0 = time.time()
    n_bars = 365*5
    panels = gen_data(n_bars)
    alpha = AlphaMomentum(window=ALPHA_WINDOW)
    log.info("Alpha: %s (window=%d)", type(alpha).__name__, alpha.window)
    close = panels["close"]
    forward = compute_forward_returns(close, horizons=FORWARD_HORIZONS)
    full_scores = alpha.compute(panels)
    full_r = evaluate_factor("m21", full_scores, forward, direction=alpha.direction)
    train_mask = (close.index>=pd.Timestamp(TRAIN_START))&(close.index<=pd.Timestamp(TRAIN_END))
    train_scores = full_scores.loc[train_mask]
    train_fwd = {h:fwd.loc[train_mask] for h,fwd in forward.items()}
    train_r = evaluate_factor("m21train", train_scores, train_fwd, direction=alpha.direction)
    test_mask = (close.index>=pd.Timestamp(TEST_START))&(close.index<=pd.Timestamp(TEST_END))
    test_scores = full_scores.loc[test_mask]
    test_fwd = {h:fwd.loc[test_mask] for h,fwd in forward.items()}
    test_r = evaluate_factor("m21test", test_scores, test_fwd, direction=alpha.direction)
    elapsed = time.time()-t0
    print()
    print("="*70)
    print("  ALPHA MOMENTUM BACKTEST REPORT")
    print("="*70)
    print(f"  Alpha: {type(alpha).__name__} (window={alpha.window})")
    print(f"  Data: synthetic daily ({n_bars} bars)")
    print(f"  Symbols: {len(panels["close"].columns)}")
    print(f"  Full: {FULL_START} to {FULL_END}")
    print(f"  Train: {TRAIN_START} to {TRAIN_END}")
    print(f"  Test: {TEST_START} to {TEST_END}")
    print(f"  Combinations: 1")
    print(f"  Time: {elapsed:.2f}s")
    print()
    for label, results in [("FULL",full_r),("TRAIN",train_r),("TEST",test_r)]:
        print(f"  --- {label} ---")
        for r in results:
            if r.get("n_timestamps",0)==0: continue
            print(f"    h={r["horizon"]:>2}d  IC={r["mean_rank_ic"]:+.6f}  IC_IR={r["ic_ir"]:+.4f}  Spread={r["top_bottom_gross_return"]:+.6f}  n={r["n_timestamps"]:>5d}  [{r["pass_fail"]}]")
        print()
    def _best(rr):
        for h in [21,5,1]:
            for r in rr:
                if r.get("horizon")==h and r.get("n_timestamps",0)>0: return r
        return None
    tb = _best(test_r); mk = tb["mean_rank_ic"] if tb else float("nan")
    print("  --- COMPLETION SUMMARY ---")
    print(f"  train_start: {TRAIN_START}")
    print(f"  train_end: {TRAIN_END}")
    print(f"  test_start: {TEST_START}")
    print(f"  test_end: {TEST_END}")
    print(f"  n_combinations: 1")
    print(f"  metric (mean_rank_ic): {mk}")
    print(f"  Status: {'SUCCESS' if pd.notna(mk) else 'FAILURE'}")
    print("="*70)
    report = dict(report_id="ALPHA_MOMENTUM_BACKTEST_V01", generated_at=datetime.now(timezone.utc).isoformat(), alpha=dict(name="AlphaMomentum", class_="alphaforge.alphas.alpha_momentum.AlphaMomentum", window=alpha.window, direction=alpha.direction), parameters=dict(data_source="synthetic_daily", n_bars=n_bars, n_symbols=len(panels["close"].columns), forward_horizons=FORWARD_HORIZONS), periods=dict(full=dict(start=FULL_START,end=FULL_END), train=dict(start=TRAIN_START,end=TRAIN_END), test=dict(start=TEST_START,end=TEST_END)), n_combinations=1, results=dict(full=_to_native(full_r), train=_to_native(train_r), test=_to_native(test_r)), status="SUCCESS" if pd.notna(mk) else "FAILURE")
    output_dir = os.path.join(PROJECT_ROOT, "reports", "candidates")
    os.makedirs(output_dir, exist_ok=True)
    with open(os.path.join(output_dir, "alpha_momentum_backtest.json"), "w") as f:
        json.dump(report, f, indent=2)
    log.info("Report saved")
    return 0
if __name__ == "__main__": sys.exit(main())
