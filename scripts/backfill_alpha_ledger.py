"""Backfill Alpha Ledger with all alphas discovered so far.

Run once:
    PYTHONPATH=alphaforge/src:. python scripts/backfill_alpha_ledger.py

Seeds the ledger with every alpha that has been tested across all runs.
Idempotent — skips already-registered alpha_ids.
"""

from alphaforge.reports.alpha_ledger import AlphaLedger, DATA_REAL, DATA_SYNTHETIC

LEDGER = AlphaLedger()

# ---------------------------------------------------------------------------
# Existing alphas from alphaforge/docs/ai_summary.md + leaderboard data
# ---------------------------------------------------------------------------

BACKFILL = [
    # === BB Position Mean-Reversion v1 ===
    {
        "alpha_id": "scalp_bb_position_mean_reversion_v1",
        "run_id": "run-scalp-bb-v1-20260705",
        "mode": "SCALP",
        "name": "BB Position Mean-Reversion v1",
        "thesis": "bb_position = normalized location of close within Bollinger Bands. Near upper band -> mean-reversion sell. 97.3% feature dominance.",
        "source": "xgb",
        "status": "CONTAMINATED",
        "data_source": DATA_REAL,
        "symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"],
        "net_R_per_trade": 0.0043,
        "trade_count": 4552,
        "win_rate": None,
        "profit_factor": None,
        "max_drawdown_R": 0.1518,
        "sharpe": None,
        "oos_ic": None,
        "oos_rank_ic": None,
        "cost_stress_survived": True,
        "holdout_tested": False,
        "holdout_net_R": None,
        "v7_gates": {
            "G0": "PASS", "G1": "PASS", "G2": "PASS", "G3": "PASS",
            "G4": "NOT_EVALUATED", "G5": "NOT_EVALUATED",
            "G6": "PENDING", "G7-G10": "NOT_EVALUATED",
        },
        "tags": ["leakage", "single-feature-dominance", "contaminated"],
        "notes": "CONTAMINATED: _rolling_mean used np.convolve(mode='same') leaking future data. bb_position 97.3% dominance. Must re-validate on corrected features.",
        "lineage": {"git_commit": "5d2edde", "data_refs": ["binance-real-4symbol-118Kbar-1h-2023-2026"]},
    },
    # === BB Position on CORRECTED features (preliminary) ===
    {
        "alpha_id": "scalp_bb_position_mean_reversion_v2",
        "run_id": "run-scalp-bb-v2-pending",
        "mode": "SCALP",
        "name": "BB Position Mean-Reversion v2 (corrected)",
        "thesis": "Same as v1 but on corrected trailing-window features. Awaiting re-validation.",
        "source": "xgb",
        "status": "HOLD",
        "data_source": DATA_REAL,
        "symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"],
        "net_R_per_trade": None,
        "trade_count": None,
        "tags": ["awaiting-revalidation"],
        "notes": "Pipeline fixed (mode='full'[:n]). Re-validation not yet run.",
    },
    # === Alpha Truth Upgrade V6 ===
    {
        "alpha_id": "discovery_pipeline_v6",
        "run_id": "run-alpha-truth-v6-20260707",
        "mode": "SCALP",
        "name": "Discovery Pipeline V6 (real data, 4-sym)",
        "thesis": "V1-V6 fixes applied: per-symbol ranges, mode-aware labels, residual momentum, unified eval, debias quarantine, simulation scoreboard.",
        "source": "discovery",
        "status": "REJECTED",
        "data_source": DATA_REAL,
        "symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"],
        "net_R_per_trade": 0.0515,
        "trade_count": 870,
        "win_rate": 0.4966,
        "profit_factor": 1.11,
        "max_drawdown_R": -20.96,
        "sharpe": 0.79,
        "cost_stress_survived": None,
        "holdout_tested": False,
        "tags": ["discovery-pipeline", "best-honest"],
        "notes": "Best honest result: +0.0515R. Below SCALP promotion threshold (0.05R borderline). DD=-20.96R. REJECT.",
    },
    # === AlphaForge SCALP 1h Direction v01 ===
    {
        "alpha_id": "scalp_1h_direction_v01",
        "run_id": "run-scalp-direction-v01-20260702",
        "mode": "SCALP",
        "name": "SCALP 1h Direction (XGBoost 2-class)",
        "thesis": "Binary LONG vs SHORT classifier on 1h data. NO_TRADE class removed (random 50%).",
        "source": "xgb",
        "status": "REJECTED",
        "data_source": DATA_REAL,
        "symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"],
        "net_R_per_trade": 0.007648,
        "trade_count": 31752,
        "win_rate": None,
        "profit_factor": 242647.86,
        "max_drawdown_R": None,
        "sharpe": None,
        "oos_ic": None,
        "oos_rank_ic": None,
        "cost_stress_survived": None,
        "holdout_tested": False,
        "tags": ["2-class", "no-actionability"],
        "notes": "OOS acc=0.5149, marginally beats random. Flat calibration. Not V7_READY.",
    },
    # === SCALP Operation 0.05 Base (12 sym) ===
    {
        "alpha_id": "scalp_op005_base_12sym",
        "run_id": "run-op-scalp-005-20260707",
        "mode": "SCALP",
        "name": "SCALP Baseline (Operation 0.05, taker, 12 sym)",
        "thesis": "Baseline SCALP evaluation on 12 bootstrap symbols with taker execution.",
        "source": "operation_scalp",
        "status": "REJECTED",
        "data_source": DATA_REAL,
        "symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT",
                      "DOTUSDT", "AVAXUSDT", "LINKUSDT", "ATOMUSDT", "MATICUSDT", "AVAXUSDT"],
        "net_R_per_trade": -0.0951,
        "trade_count": 4726,
        "win_rate": 0.4448,
        "profit_factor": 0.81,
        "max_drawdown_R": -462.83,
        "sharpe": -1.53,
        "cost_stress_survived": False,
        "holdout_tested": False,
        "tags": ["baseline", "negative-expectancy", "operation-005"],
        "notes": "True base R on 12 real symbols. Negative expectancy. 0.1328R short of 0.05 target.",
    },
    # === SCALP Operation 0.05 Maker-pessimistic ===
    {
        "alpha_id": "scalp_op005_maker_pess_12sym",
        "run_id": "run-op-scalp-005-20260707",
        "mode": "SCALP",
        "name": "SCALP Maker-Pessimistic (Operation 0.05, 12 sym)",
        "thesis": "Same as base but with pessimistic maker fill assumption (+0.0124R/trade improvement).",
        "source": "operation_scalp",
        "status": "REJECTED",
        "data_source": DATA_REAL,
        "symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT",
                      "DOTUSDT", "AVAXUSDT", "LINKUSDT", "ATOMUSDT", "MATICUSDT", "AVAXUSDT"],
        "net_R_per_trade": -0.0828,
        "trade_count": 4726,
        "win_rate": 0.4467,
        "profit_factor": None,
        "max_drawdown_R": None,
        "cost_stress_survived": False,
        "holdout_tested": False,
        "tags": ["maker", "best-honest", "operation-005"],
        "notes": "Best honest stack: -0.0828R. Still 0.1328R short of 0.05 target.",
    },
    # === SWING Control (12 sym) ===
    {
        "alpha_id": "swing_control_12sym",
        "run_id": "run-op-scalp-005-20260707",
        "mode": "SWING",
        "name": "SWING Control (Operation 0.05, taker, 12 sym)",
        "thesis": "SWING baseline as control mode for architecture validation.",
        "source": "operation_scalp",
        "status": "REJECTED",
        "data_source": DATA_REAL,
        "symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT",
                      "DOTUSDT", "AVAXUSDT", "LINKUSDT", "ATOMUSDT", "MATICUSDT", "AVAXUSDT"],
        "net_R_per_trade": -0.1138,
        "trade_count": 2270,
        "win_rate": 0.4137,
        "profit_factor": 0.80,
        "max_drawdown_R": -328.31,
        "sharpe": -1.66,
        "cost_stress_survived": False,
        "holdout_tested": False,
        "tags": ["control", "negative-expectancy"],
        "notes": "SWING control baseline. Negative expectancy. Cost decomposition: fee=0.0468R, slippage=0.0118R.",
    },
    # === Factor Sprint alphas (22 unique factor types) ===
    {
        "alpha_id": "fs_trend_pullback_ema",
        "run_id": "fs-001-20260704", "mode": "SWING", "name": "Trend Pullback EMA",
        "thesis": "Long if price > EMA(50) and RSI < 40 (pullback in uptrend).",
        "source": "factor_sprint", "status": "REJECTED", "data_source": DATA_REAL,
        "symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT",
                      "DOTUSDT", "AVAXUSDT", "LINKUSDT", "ATOMUSDT", "MATICUSDT",
                      "NEARUSDT", "FILUSDT", "APTUSDT", "ARBUSDT", "OPUSDT", "SUIUSDT",
                      "DOGEUSDT", "BCHUSDT", "LTCUSDT"],
        "net_R_per_trade": -0.1033, "trade_count": 40944,
        "notes": "SWING_PROXY_1H. Negative total R (-4231). REJECT.",
    },
    {
        "alpha_id": "fs_compression_breakout_regime",
        "run_id": "fs-001-20260704", "mode": "SWING", "name": "Compression Breakout Regime",
        "thesis": "BB width compression followed by breakout regime detection.",
        "source": "factor_sprint", "status": "REJECTED", "data_source": DATA_REAL,
        "symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"],
        "net_R_per_trade": -0.1061, "trade_count": 45669,
        "notes": "Negative total R (-4847). REJECT.",
    },
    {
        "alpha_id": "fs_spread_contraction_signal",
        "run_id": "fs-001-20260704", "mode": "SWING", "name": "Spread Contraction Signal",
        "thesis": "Spread narrowing as precursor to directional move.",
        "source": "factor_sprint", "status": "REJECTED", "data_source": DATA_REAL,
        "symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"],
        "net_R_per_trade": -0.1101, "trade_count": 44562,
        "notes": "Negative total R (-4908). REJECT.",
    },
    {
        "alpha_id": "fs_corwin_schultz_spread_proxy",
        "run_id": "fs-001-20260704", "mode": "SWING", "name": "Corwin-Schultz Spread Proxy",
        "thesis": "High-low range based spread estimation.",
        "source": "factor_sprint", "status": "REJECTED", "data_source": DATA_REAL,
        "symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"],
        "net_R_per_trade": -0.1164, "trade_count": 49672,
        "notes": "Negative total R (-5781). REJECT.",
    },
    {
        "alpha_id": "fs_volume_climax_reversal_long",
        "run_id": "fs-001-20260704", "mode": "SWING", "name": "Volume Climax Reversal Long",
        "thesis": "Abnormally high volume exhaustion -> reversal long.",
        "source": "factor_sprint", "status": "REJECTED", "data_source": DATA_REAL,
        "symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"],
        "net_R_per_trade": -0.1143, "trade_count": 57167,
        "notes": "Negative total R (-6535). REJECT.",
    },
    {
        "alpha_id": "fs_volume_climax_reversal_short",
        "run_id": "fs-001-20260704", "mode": "SWING", "name": "Volume Climax Reversal Short",
        "thesis": "Abnormally high volume exhaustion -> reversal short.",
        "source": "factor_sprint", "status": "REJECTED", "data_source": DATA_REAL,
        "symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"],
        "net_R_per_trade": -0.1227, "trade_count": 57227,
        "notes": "Negative total R (-7023). REJECT.",
    },
    {
        "alpha_id": "fs_session_volatility_regime",
        "run_id": "fs-001-20260704", "mode": "SWING", "name": "Session Volatility Regime",
        "thesis": "Volatility regime classification as alpha source.",
        "source": "factor_sprint", "status": "REJECTED", "data_source": DATA_REAL,
        "symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"],
        "net_R_per_trade": -0.2439, "trade_count": 44342,
        "notes": "Negative total R (-10816). REJECT.",
    },
    {
        "alpha_id": "fs_btc_uptrend_pullback_long",
        "run_id": "fs-001-20260704", "mode": "SWING", "name": "BTC Uptrend Pullback Long",
        "thesis": "BTC regime uptrend -> pullback entry long on alts.",
        "source": "factor_sprint", "status": "REJECTED", "data_source": DATA_REAL,
        "symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"],
        "net_R_per_trade": -0.4150, "trade_count": 21628,
        "notes": "Negative total R (-8976). REJECT.",
    },
    {
        "alpha_id": "fs_btc_lead_lag_alt_short",
        "run_id": "fs-001-20260704", "mode": "SWING", "name": "BTC Lead-Lag Alt Short",
        "thesis": "BTC leads altcoins -> short altcoin on BTC weakness.",
        "source": "factor_sprint", "status": "REJECTED", "data_source": DATA_REAL,
        "symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"],
        "net_R_per_trade": -0.3611, "trade_count": 35738,
        "notes": "Negative total R (-12904). REJECT.",
    },
    {
        "alpha_id": "fs_btc_lead_lag_alt_long",
        "run_id": "fs-001-20260704", "mode": "SWING", "name": "BTC Lead-Lag Alt Long",
        "thesis": "BTC leads altcoins -> long altcoin on BTC strength.",
        "source": "factor_sprint", "status": "REJECTED", "data_source": DATA_REAL,
        "symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"],
        "net_R_per_trade": -0.3628, "trade_count": 35744,
        "notes": "Negative total R (-12968). REJECT.",
    },
    {
        "alpha_id": "fs_btc_downtrend_breakdown_short",
        "run_id": "fs-001-20260704", "mode": "SWING", "name": "BTC Downtrend Breakdown Short",
        "thesis": "BTC regime downtrend -> breakdown short on alts.",
        "source": "factor_sprint", "status": "REJECTED", "data_source": DATA_REAL,
        "symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"],
        "net_R_per_trade": -0.4200, "trade_count": 41974,
        "notes": "Negative total R (-17628). REJECT.",
    },
    # IC-based factor signals (from ALPHA_LEADERBOARD_V2)
    {
        "alpha_id": "fs_breakdown_n_low_24h",
        "run_id": "fs-001-20260704", "mode": "SCALP", "name": "Breakdown N Low 24h",
        "thesis": "close < lowest(low, 20) within last 3 bars. Short direction.",
        "source": "factor_sprint", "status": "WATCH", "data_source": DATA_REAL,
        "symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"],
        "oos_rank_ic": -0.045, "sharpe": -0.154, "trade_count": 29893,
        "notes": "Best IC signal: mean_rank_ic=-0.045, IC_IR=0.15. WATCH but sim-space negative.",
    },
    {
        "alpha_id": "fs_volume_zscore_24h",
        "run_id": "fs-001-20260704", "mode": "SCALP", "name": "Volume Z-Score 24h",
        "thesis": "Z-score of volume relative to 20-bar rolling window.",
        "source": "factor_sprint", "status": "REJECTED", "data_source": DATA_REAL,
        "symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"],
        "oos_rank_ic": 0.035, "sharpe": 0.141, "trade_count": 29893,
        "notes": "IC_IR=0.14, orientation flipped (inverted). Sim-space negative.",
    },
    {
        "alpha_id": "fs_ret_24h_rank_24h",
        "run_id": "fs-001-20260704", "mode": "SCALP", "name": "Ret 24h Rank 24h",
        "thesis": "Log return over 24 bars, cross-sectionally ranked.",
        "source": "factor_sprint", "status": "REJECTED", "data_source": DATA_REAL,
        "symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"],
        "oos_rank_ic": 0.029, "sharpe": 0.101, "trade_count": 29880,
        "notes": "IC_IR=0.10, flipped. Sim-space negative.",
    },
    {
        "alpha_id": "fs_ret_4h_rank_1h",
        "run_id": "fs-001-20260704", "mode": "SCALP", "name": "Ret 4h Rank 1h",
        "thesis": "Log return over 4 bars, cross-sectionally ranked.",
        "source": "factor_sprint", "status": "REJECTED", "data_source": DATA_REAL,
        "symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"],
        "oos_rank_ic": 0.029, "sharpe": 0.102, "trade_count": 29922,
        "notes": "IC_IR=0.10, flipped. Sim-space negative.",
    },
    {
        "alpha_id": "fs_reversal_4h_zscore_1h",
        "run_id": "fs-001-20260704", "mode": "SCALP", "name": "Reversal 4h Z-Score 1h",
        "thesis": "Negative of z-scored 4h return (mean-reversion signal).",
        "source": "factor_sprint", "status": "REJECTED", "data_source": DATA_REAL,
        "symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"],
        "oos_rank_ic": 0.029, "sharpe": 0.102, "trade_count": 29922,
        "notes": "IC_IR=0.10. Sim-space negative.",
    },
    {
        "alpha_id": "fs_volume_zscore_12h",
        "run_id": "fs-001-20260704", "mode": "SCALP", "name": "Volume Z-Score 12h",
        "thesis": "Z-score of volume relative to 20-bar rolling window.",
        "source": "factor_sprint", "status": "REJECTED", "data_source": DATA_REAL,
        "symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"],
        "oos_rank_ic": 0.029, "sharpe": 0.116, "trade_count": 29905,
        "notes": "IC_IR=0.12, flipped. Sim-space negative.",
    },
    {
        "alpha_id": "fs_trend_pullback_ema_24h",
        "run_id": "fs-001-20260704", "mode": "SCALP", "name": "Trend Pullback EMA 24h",
        "thesis": "Long if price > EMA(50) and RSI < 40 (pullback in uptrend).",
        "source": "factor_sprint", "status": "REJECTED", "data_source": DATA_REAL,
        "symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"],
        "oos_rank_ic": 0.029, "sharpe": 0.106, "trade_count": 29881,
        "notes": "IC_IR=0.11, flipped. Sim-space negative.",
    },
    {
        "alpha_id": "fs_breakdown_n_low_12h",
        "run_id": "fs-001-20260704", "mode": "SCALP", "name": "Breakdown N Low 12h",
        "thesis": "close < lowest(low, 20) within last 3 bars. Short.",
        "source": "factor_sprint", "status": "REJECTED", "data_source": DATA_REAL,
        "symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"],
        "oos_rank_ic": -0.041, "sharpe": -0.138, "trade_count": 29905,
        "notes": "IC_IR=0.14. Sim-space negative.",
    },
]


# ---------------------------------------------------------------------------
# Execute backfill
# ---------------------------------------------------------------------------

def main() -> None:
    added = 0
    skipped = 0
    for alpha in BACKFILL:
        alpha_id = alpha["alpha_id"]
        if LEDGER.get_alpha(alpha_id) is not None:
            skipped += 1
            continue
        LEDGER.add_alpha(**alpha)
        added += 1

    path = LEDGER.write()
    print(f"Alpha Ledger backfill complete:")
    print(f"  Added: {added}")
    print(f"  Skipped (already exists): {skipped}")
    print(f"  Total in ledger: {len(LEDGER.alphas)}")
    print(f"  Written to: {path}")

    # Print summary
    s = LEDGER.summary
    print(f"\n  Summary:")
    print(f"    Total: {s['total_alphas']}")
    for status, count in s["by_status"].items():
        print(f"    {status}: {count}")
    print(f"    Best net_R: {s['best_net_R']}")


if __name__ == "__main__":
    main()
