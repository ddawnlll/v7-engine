# Reject Forever List

**Generated:** 2026-07-08

---

## Criteria for Permanent Rejection

An alpha is permanently rejected only if BOTH conditions hold:
1. Strongly negative evidence (R < -0.3, or consistent large losses)
2. No plausible rescue path (no segment, no inversion, no regime that helps)

---

## Rejected Forever Entries (5)

### 1. SWING Control (Operation 0.05, taker, 12 sym)
- **Alpha ID:** `swing_control_12sym`
- **R/trade:** -0.1138
- **Trades:** 2,270
- **Evidence:** SWING control baseline. Negative expectancy across all configurations.
  Cost decomposition: fee=0.0468R, slippage=0.0118R.
  0/6 walk-forward folds positive. Overfit gap = 0.3619.
- **What would change to reconsider:** Complete rearchitecture of the SWING mode
  pipeline, or fundamentally different market regime.
- **Verdict:** Control baseline, not an alpha. Permanent.

### 2. BTC Uptrend Pullback Long
- **Alpha IDs:** `fs_btc_uptrend_pullback_long_SCALP_1H_FAST_long` etc.
- **R/trade:** -0.415 to -1.479 (across 3 modes)
- **Trades:** 21,628 to 39,581
- **Evidence:** The worst performing concept in the inventory. BTC uptrend-based
  long entries systematically destroy capital. The -1.48R/trade in SCALP_1H_FAST
  mode is the single worst entry.
- **What would change to reconsider:** If crypto market structure fundamentally
  changes (e.g., BTC becomes negatively correlated with altcoins during uptrends
  instead of positively).
- **Verdict:** BTC uptrend does not predict altcoin long entries in this dataset.

### 3. BTC Lead-Lag Alt Short
- **Alpha IDs:** `fs_btc_lead_lag_alt_short_*`
- **R/trade:** -0.361 to -0.650
- **Trades:** 35,738 to 71,393
- **Evidence:** The hypothesis "BTC leads, alts follow" is wrong for short entries.
  Shorting alts when BTC weakens loses money consistently.
- **What would change to reconsider:** New evidence that BTC-alts correlation
  has structurally changed, or lead-lag has inverted.
- **Verdict:** Stable negative across all modes and trade counts > 35K.

### 4. BTC Lead-Lag Alt Long
- **Alpha IDs:** `fs_btc_lead_lag_alt_long_*`
- **R/trade:** -0.363 to -0.656
- **Trades:** 35,744 to 71,495
- **Evidence:** Mirror of above. Going long on alts when BTC is strong
  loses money. Same failure pattern.
- **What would change to reconsider:** Same as BTC Lead-Lag Short.
- **Verdict:** Stable negative. BTC lead-lag is not a viable alpha source.

### 5. BTC Downtrend Breakdown Short
- **Alpha IDs:** `fs_btc_downtrend_breakdown_short_*`
- **R/trade:** -0.420 to -1.021
- **Trades:** 41,974 to 85,419
- **Evidence:** Shorting breakdowns during BTC downtrends loses money consistently.
  This may be because BTC downtrends are periods of high volatility where
  breakdowns are already priced in.
- **What would change to reconsider:** Evidence that breakdowns during BTC
  downtrends become profitable in a different market regime.
- **Verdict:** The combination of downtrend + breakdown double-counts bearish
  signals and creates a crowded trade.

---

## Summary

| # | Alpha | Reason | Irreversibility |
|---|-------|--------|-----------------|
| 1 | SWING Control | Not an alpha, just a control baseline | Permanent |
| 2 | BTC Uptrend Pullback Long | Systematically destroys capital | Unless market structure changes |
| 3 | BTC Lead-Lag Alt Short | Wrong hypothesis, 35K+ trades | Stable evidence |
| 4 | BTC Lead-Lag Alt Long | Wrong hypothesis, 35K+ trades | Stable evidence |
| 5 | BTC Downtrend Breakdown Short | Double-counts bearish | Unless regime changes |

**Total permanently rejected: 5 of 170 entries (2.9%)**

These 5 are genuinely unrecoverable. Most other negative alphas have
some theoretical rescue path (inversion, segment, regime, cost).
