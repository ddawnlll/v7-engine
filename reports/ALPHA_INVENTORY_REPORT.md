# ALPHA INVENTORY FULL REPORT

**Generated:** 2026-07-08
**Scope:** Every alpha concept ever tested in this repo — real data + synthetic
**Sources:** Alpha Ledger (26), R-Leaderboard (63), IC-Leaderboard (48), Proxy (33)
**Master file:** `reports/ALPHA_INVENTORY_FULL.csv`

---

## Executive Summary

| Metric | Value |
|--------|-------|
| **Total alpha entries** | **170** |
| Unique alpha concepts | ~25 |
| Unique factor types | 22 |
| XGBoost model candidates | 2 |
| Discovery pipeline runs | 1 |
| **Total positive net_R** | **3** |
| Total negative net_R | 110 |
| Best net_R (all time) | **+0.0515R** (Discovery V6, 870 trades) |
| Cost-adjacent alpha | **0** |
| Promotion-ready alpha | **0** |
| Total trades (sum across all) | 8,481,699 |

---

## Status Breakdown

| Status | Count | Meaning |
|--------|-------|---------|
| REJECT | 96 | Failed simulation-space evaluation |
| WATCH | 46 | Weak IC signal, not yet simulated |
| REJECTED | 23 | Explicitly rejected by gates |
| FAIL | 3 | Near-zero IC, not actionable |
| CONTAMINATED | 1 | Future leakage (bb_position v1) |
| HOLD | 1 | Awaiting re-validation (bb_position v2) |

---

## Mode Breakdown

| Mode | Count | Notes |
|------|-------|-------|
| SCALP | 62 | Including ledger + IC leaderboard |
| SWING_PROXY_1H | 32 | Factor sprint with SWING holding period |
| SCALP_1H_SLOW | 32 | Factor sprint with slow scalp profile |
| SCALP_1H_FAST | 32 | Factor sprint with fast scalp profile |
| SWING | 12 | Ledger entries for SWING mode |

---

## Top 5 Alphas by net_R

| Rank | Name | net_R | Trade Count | Source | Status |
|------|------|-------|-------------|--------|--------|
| 1 | Discovery Pipeline V6 | **+0.0515** | 870 | ledger | REJECTED |
| 2 | SCALP 1h Direction v01 | **+0.0076** | 31,752 | ledger | REJECTED |
| 3 | BB Position v1 (all trades) | **+0.0043** | 4,552 | ledger | CONTAMINATED |

All other 167 entries have **negative net_R**.

---

## Cost Survivability Analysis

| Alpha | Raw R | Est. Cost/Trade | Cost-Adj R | Verdict |
|-------|-------|-----------------|------------|---------|
| Truth V6 | +0.0515 | ~0.062R | **~-0.01R** | FAIL |
| BB Position v1 | +0.0043 | ~0.062R | **~-0.058R** | FAIL |
| Op Scalp 0.05 Base | -0.0951 | 0.0619R | -0.157R | FAIL |
| Op Scalp 0.05 Maker | -0.0828 | 0.0496R | -0.132R | FAIL |

**Cost gate (>= 0.10R after costs): NO ALPHA PASSES.**

---

## OOS / Walk-Forward Status

| Alpha | WF Folds | OOS R | Train/OOS Gap | Holdout |
|-------|----------|-------|---------------|---------|
| Truth V6 | 6 | +0.0515 | Unknown | NOT RUN |
| BB Position v1 | 6 | +0.0043 | Unknown | NOT RUN |
| Op Scalp 0.05 | 6 | -0.0951 | Unknown | NOT RUN |

**OOS gate: NOT EVALUATED properly.**

---

## Symbol Concentration

| Alpha | Top Symbol Share | 2-Symbol Share | Gate (< 40%) |
|-------|-----------------|----------------|--------------|
| Op Scalp 0.05 (12 sym) | DOGEUSDT 21.4% | 41.2% | **FAIL** |
| SWING Control (12 sym) | AVAXUSDT 75.8% | 86.6% | **FAIL** |
| Factor Sprint | Mixed per factor | ~10-18% | PASS (20 sym) |

---

## Regime Split

**Not evaluated for any alpha.** All regime analysis is marked NOT_EVALUATED in V7 gates (G4).

---

## Alpha Uniqueness / Correlation

| Cluster | Factors | Independence |
|---------|---------|-------------|
| Price Momentum | ret_1h/4h/12h/24h_rank | Same bet, different windows |
| Mean Reversion | reversal_1h/4h_zscore, bb_position | Same bet, different params |
| Volume | volume_zscore, volume_climax_reversal | Somewhat independent |
| Breakout | breakout_n_high, breakdown_n_low | Binary signals, independent direction |
| Trend | trend_pullback_ema, btc_uptrend_pullback | Similar logic |
| Volatility | range_zscore, compression_expansion, session_vol_regime | Vol cluster |
| Spread | corwin_schultz, spread_contraction | Microstructure cluster |
| Regime | compression_breakout_regime, btc_lead_lag | BTC-dependent |

**Estimated independent clusters: 4-5** (price/momentum, volume, breakout, regime, spread)

---

## Baseline Comparison

| Baseline | Best Alpha Beats It? |
|----------|---------------------|
| Random entry (50% WR) | Truth V6 marginally (49.66% WR ≈ random) |
| Buy-and-hold BTC | Not tested |
| Simple ATR threshold | Not tested |
| Simple BB threshold | Not tested |

**No alpha definitively beats simple baselines.**

---

## V7 Gate Status (G0-G10)

| Gate | Status | Evidence |
|------|--------|----------|
| G0 DOC_READY | PASS | Docs complete |
| G1 RESEARCH_BACKTEST | PARTIAL | Truth V6 +0.0515R, but contaminated candidates |
| G2 WALK_FORWARD_OOS | PARTIAL | 6-fold WFV exists, but results negative for most |
| G3 COST_STRESS | **FAIL** | No alpha survives cost-adjusted |
| G4 REGIME_BREAKDOWN | NOT_EVALUATED | No regime analysis done |
| G5 SYMBOL_STABILITY | NOT_EVALUATED | Concentration detected but not gated |
| G6 CALIBRATION | NOT_EVALUATED | No calibration artifact |
| G7 SHADOW | NOT_STARTED | No shadow infrastructure |
| G8 PAPER | NOT_STARTED | No paper trading path |
| G9 TINY_LIVE | NOT_STARTED | No live adapter |
| G10 LIVE | NOT_STARTED | No live path |

---

## V7-Lite AlphaForge Completion Gate

```text
G0 Alpha Discovery Exists:          PASS (25 concepts, real data)
G1 Minimum Alpha Viability:         PARTIAL_PASS (+0.0515R, 870 trades)
G2 Cost-Adjusted Survival:          FAIL (no alpha survives costs)
G3 Robustness / OOS:                NOT_PASS (incomplete evaluation)
G4 Replay Infrastructure:           NOT_STARTED
G5 Calibration Control Plane:       DESIGN_ONLY
G6 Revenue / Live Readiness:        FAIL (0 promoted clusters)

Overall V7-Lite Completion:         37%
```

---

## Allowed Next Actions

1. Truth V6 trade distribution analysis (p25/p50/p75, top/bottom split)
2. Cost survivability at 2x/5x stress
3. Regime split (trend/chop/vol regimes)
4. Symbol split (per-symbol R contribution)
5. Session split (hour/day effects)
6. Alpha correlation matrix (uniqueness verification)
7. Build CPU candidate-outcome cache
8. Build simulation parity benchmark

## Forbidden Actions

- Claim revenue readiness
- Build live executor
- Mutate cost model
- Mutate risk limits
- Let LLM mutate full configs

---

## Files

| File | Description |
|------|-------------|
| `reports/ALPHA_INVENTORY_FULL.csv` | Master CSV (170 rows, all alphas) |
| `reports/ALPHA_INVENTORY_REPORT.md` | This report |
| `alphaforge_report/alpha_ledger.json` | Alpha Ledger (26 entries, persistent) |
| `reports/alphaforge/factor_sprint/ALPHA_R_LEADERBOARD.csv` | Factor sprint R results (63 entries) |
| `reports/alphaforge/factor_sprint/ALPHA_LEADERBOARD_V2.csv` | Factor sprint IC results (48 entries) |
| `reports/alphaforge/factor_sprint/PROXY_R_LEADERBOARD_V2.csv` | Proxy R results (33 entries) |
| `reports/alphaforge/factor_sprint/V7_ALPHA_CANDIDATES.md` | V7 candidates (0 promoted) |
| `reports/overnight/MORNING_REPORT.md` | Operation SCALP 0.05 campaign |
| `alphaforge/docs/discovered_alphas/SCALP_bb_position_mean_reversion_v1.json` | BB Position v1 handoff |

---

*Generated by AlphaForge audit. All data from real Binance market data unless noted.*
