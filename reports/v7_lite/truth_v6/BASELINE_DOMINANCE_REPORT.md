# Baseline Dominance Report — PARTIAL

**Status:** `PARTIAL` — aggregate data only, no trade-level data for proper comparison
**Generated:** 2026-07-08
**Alpha:** Discovery Pipeline V6 (Truth V6)
**Run ID:** `run-alpha-truth-v6-20260707`

---

## Executive Summary

Truth V6 (+0.0515R, 49.66% WR, 870 trades) is compared against simple baselines.
**The comparison is limited** because exact baseline simulations require the same
candle data, entry timing, and trade-level outputs.

**Preliminary verdict:** Truth V6 does NOT clearly beat simple baselines.
Its win rate is indistinguishable from random (50%), and its Sharpe (0.79) is
below the threshold that would indicate a genuine edge over trend-following
or volatility-based benchmarks.

---

## Baseline 1: Random Same-Frequency

| Metric | Truth V6 | Random (theoretical) | Truth V6 Wins? |
|--------|----------|---------------------|-----------------|
| Win rate | 49.66% | 50.0% (fair coin) | ❌ (essentially tied) |
| Expected R | +0.0515 | 0.0 | ✅ (positive vs zero) |
| Sharpe | 0.79 | 0.0 | ✅ |

**Method:** For 870 trades at 50% WR with symmetric R distribution, expected R = 0.
Truth V6's +0.0515R/trade edge has an information ratio of 0.79.

**Significance test:** t = 0.79 / sqrt(1/870) = 0.79 / 0.0339 = 23.3 standard errors from zero.
BUT this ignores multiple testing (selected best from 170 candidates).

**Deflated Sharpe (preliminary):**
Using the deflated Sharpe ratio (DSR) formula from Bailey & López de Prado (2014):
- Number of trials: 170 (approximate independent alphas)
- Observed Sharpe: 0.79
- Expected max Sharpe under null (N=170, T=870): ~2.5-3.0
- With T=870 and N=170 independent trials, E[max(Sharpe)] ≈ sqrt(2*ln(170)) = sqrt(10.07) ≈ 3.17
- **Result:** Observed Sharpe 0.79 is far below the expected maximum from random trials (3.17).
  Truth V6 does NOT beat the multiple-testing-adjusted null.

**Conclusion:** After accounting for 170-way selection, Truth V6's Sharpe is consistent
with the best of 170 random strategies.

---

## Baseline 2: Simple ATR Threshold

**Method:** Enter LONG when close > entry + 0.5×ATR; enter SHORT when close < entry - 0.5×ATR.
Hold for same bars as Truth V6. Exit at stop/target/time.

**Comparison:** Not directly computable without Truth V6's entry timestamps and ATR values.
However:
- Truth V6 uses ATR-based stops and targets (standard for SCALP mode at 1.5-2.0× ATR)
- Any directional strategy using ATR-based exits will have similar return distribution
- The 1.11 profit factor is barely above 1.0 — a simple ATR breakout with 1.5:1 reward:risk
  needs only 40% win rate to achieve profit_factor = 1.0
- Truth V6's 49.66% win rate with 1.11 PF is **consistent with a break-even ATR strategy**

**Conclusion:** Cannot rule out that Truth V6 ≈ ATR threshold with noise.

---

## Baseline 3: Simple Bollinger Band Threshold

**Method:** LONG when close < lower band (oversold), SHORT when close > upper band (overbought).
50% mean reversion assumption.

**Comparison:** The BB Position Mean-Reversion v1 alpha (same trading thesis) had
only +0.0043R (CONTAMINATED). After correction, BB v2 is awaiting re-validation.
Truth V6's thesis mentions "residual momentum" which is BB-adjacent.

**Conclusion:** Truth V6 likely captures some of the same regime as BB mean-reversion,
but at +0.0515R vs BB's +0.0043R, it appears to be a **different or enhanced signal**.

---

## Baseline 4: Simple Momentum Baseline

**Method:** Goes LONG when short-term MA > long-term MA; SHORT otherwise.

**Comparison:** Factor sprint trend-following alphas (trend_pullback_ema) achieved
-0.1033R to -0.15R across all modes. Truth V6's +0.0515R beats these, but the
factor sprint ran on 20 symbols without the regime/label refinements of Truth V6.

**Conclusion:** Truth V6 likely beats naive momentum, but this may be due to
better entry timing/regime filtering rather than unique alpha.

---

## Baseline 5: Simple Mean-Reversion Baseline

**Method:** LONG after N consecutive down closes; SHORT after N consecutive up closes.

**Comparison:** No directly comparable run. The SCALP 1h Direction v01 (+0.0076R)
uses the same data but is a different methodology.

**Conclusion:** Truth V6 (+0.0515R) beats SCALP 1h Direction (+0.0076R) by ~6.8×,
suggesting the discovery pipeline enhancements (residual momentum, regime filtering,
debias) provide genuine improvement over the basic XGBoost approach.

---

## Baseline 6: Volatility-Only Baseline

**Method:** Enter during high volatility regimes only; direction based on prior return.

**Comparison:** The factor sprint volatility alphas (range_zscore, volume_zscore,
session_volatility_regime) all had negative R (-0.13 to -0.92R). Conclusion: volatility
alone is not alpha.

**Conclusion:** Truth V6 beats volatility-only baselines, confirming it captures
something beyond volatility exposure (likely directional or regime components).

---

## Baseline 7: BTC Regime Proxy

**Method:** Trade based on BTC trend for altcoins.

**Comparison:** Factor sprint BTC-dependent alphas (btc_uptrend_pullback, btc_lead_lag,
btc_downtrend_breakdown) all had strongly negative R (-0.36 to -0.42R).

**Conclusion:** Truth V6 beats BTC regime proxies handily, suggesting it is not
simply a BTC regime tracker.

---

## Decision Question

**Q: Does Truth V6 beat simple baselines, or is it a complicated version of ATR/BB/volatility exposure?**

**A: PARTIALLY UNKNOWN.**

What we know:
1. Truth V6 clearly beats momentum-only (+0.0515R vs -0.10R to -0.15R)
2. Truth V6 clearly beats BTC regime proxies (+0.0515R vs -0.36R to -0.42R)
3. Truth V6 clearly beats volatility-only (+0.0515R vs -0.13R to -0.92R)
4. Truth V6 beats SCALP 1h Direction (+0.0076R) by 6.8× — pipeline improvements work

What we cannot determine:
1. Whether Truth V6 beats a well-tuned ATR breakout baseline
2. Whether Truth V6 beats BB mean-reversion on corrected data
3. Whether Truth V6 beats a random strategy after multiple-testing correction
4. Which specific regime/symbol split carries the edge

**Strong hypothesis based on evidence:**
Truth V6 is a **genuine weak edge** that is:
- Too small for realistic deployment after costs
- Statistically fragile given the 170-trial selection
- Likely concentrated in a specific regime/symbol combination
- An excellent candidate for the V7-Lite validation accelerator research track,
  but NOT for promotion or revenue

---

## Required Action for Full Dominance Report

To produce a definitive baseline dominance verdict, the following are needed:

1. **Re-run Truth V6 with trade-level output** (same script, different run ID)
2. **Implement these baselines on the exact same candle data:**
   - ATR breakout (1.0×, 1.5×, 2.0× multipliers)
   - BB position (fixed thresholds at 0.2, 0.8)
   - Momentum (1h and 4h cross)
   - Mean reversion (1-bar and 4-bar reversal)
3. **Compare at trade level** using the same simulation profile
4. **Compute deflated Sharpe** across all 170 candidates
5. **Report which baseline family** Truth V6 most resembles
