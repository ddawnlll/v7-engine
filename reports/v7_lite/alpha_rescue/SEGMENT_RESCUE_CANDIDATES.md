# Segment Rescue Candidates

**Generated:** 2026-07-08
**Total segment rescue candidates:** 9 (across 6 unique concepts)

---

## Methodology

A segment rescue candidate is an alpha that is negative overall but has
a plausible subset where it works:
- A specific symbol (BTCUSDT)
- A specific regime (downtrend SHORT)  
- A specific session (liquid hours)
- A specific spread/volume percentile
- A specific volatility percentile
- A specific confidence threshold

**Key insight from 12K trade analysis:** The overall 10K-trade dataset has 
+0.00085R mean, but the BTCUSDT × downtrend SHORT segment has +0.0231R.
Segment filtering can rescue weak overall signals.

---

## Priority 1: Operation SCALP 0.05 (HIGH)

### Candidates
| Name | Overall R | Trades | Breakeven needed |
|------|-----------|--------|------------------|
| SCALP Baseline (taker) | -0.0951R | 4,726 | +0.1451R |
| SCALP Maker-pessimistic | -0.0828R | 4,726 | +0.1328R |

### Rescue Approach
1. **Symbol whitelist:** Test top-6 most liquid symbols (not 12). 
   From the 12K trade analysis, BTCUSDT alone contributes +457% of profit.
   Filtering to BTCUSDT, ETHUSDT, SOLUSDT may reduce noise from illiquid symbols.

2. **Confidence threshold:** At threshold=0.55, the selectivity shows +0.1784R but
   only 131 trades. Try threshold=0.52-0.53 to get trade count up while keeping R high.

3. **Maker execution:** Already confirmed +0.0124R improvement. Combine with symbol
   whitelist for cumulative gain.

4. **Regime filter:** SHORT trades in non-uptrend regimes only.
   From the 12K analysis, SHORT in downtrend = +0.0064R, SHORT in range = +0.0034R,
   SHORT in uptrend = +0.0056R. All positive!

### Rescue Probability: **35%**
The gap is 0.13R/trade. Symbol filtering (whitelist to 4 best) + maker execution
could close 0.03-0.05R. Regime filtering another 0.02-0.03R. Still 0.05-0.08R short.

---

## Priority 2: Factor Sprint Concepts (MEDIUM)

### Candidates
| Concept | Overall R (SWING proxy) | Regime hypothesis |
|---------|------------------------|-------------------|
| Trend Pullback EMA | -0.1033R | May work in TREND regime only |
| Compression Breakout Regime | -0.1061R | May work near BREAKOUT events |
| Spread Contraction Signal | -0.1101R | May work in LIQUID markets only |
| Corwin-Schultz Spread Proxy | -0.1164R | Spread signal, may work in HIGH_SPREAD regimes |
| Volume Climax Reversal | -0.1143 to -0.1227R | May work after VOLUME CLIMAX events |
| Session Volatility Regime | -0.2439R | May work in HIGH_VOL regimes |

### Rescue Approach
1. **Regime gate:** Each of these concepts is a regime-dependent signal. They should
   have been tested WITH regime gating. Add a regime filter that only allows the
   signal when the detecting regime is active.

2. **Proxy-to-central migration:** All 6 are proxy-only results. They need to be
   re-run on the central simulation engine.

3. **Combine with Truth V6:** If Truth V6 provides a reliable regime filter,
   apply it as a meta-gate to these signals.

### Rescue Probability: **20%**
Most of these are weak concepts even in their native regime. The regime gate is 
unlikely to transform -0.10R into +0.10R.

---

## Required Test Protocol

For each segment rescue candidate:

1. Load trade-level data from outcome cache
2. Filter by symbol: only BTCUSDT + top performer
3. Filter by regime: use regime_trend from cache
4. Filter by direction: if SHORT is better, drop LONG
5. Filter by volatility percentile: if high-vol is better, drop low-vol
6. Compute corrected R after all filters
7. Apply cost model to filtered subset
8. Report n_trades after filtering (must be ≥ 200)
9. If cost-adjusted R > 0, classify as RESCUED

The required data for all these tests already exists in the outcome cache
(12K records with symbol, regime, direction, volatility columns).
