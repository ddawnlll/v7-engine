# Alpha Thesis Validation Plan

## Overview

Three hypotheses will be tested independently first, then combined into a composite signal.

| Hypothesis | Data Source | Test Period | Target R-Multiple |
|------------|-------------|-------------|-------------------|
| Altcoin Delay | Binance klines (1h, 4h) | 2021-01 to 2024-12 | > 1.5 |
| Volatility Compression | Binance klines (1h) | 2021-01 to 2024-12 | > 1.5 |
| Funding + Spot Divergence | Binancefutures funding + spot | 2021-01 to 2024-04* | > 1.5 |

*Funding rate history limited on Binance — verify data availability first.

---

## General Test Requirements

### Data Handling
- **All data must be free** — use Binance public API only
- **Download once** — cache locally in `data/raw/`, do not fetch per test run
- **Backtest window**: 4 years minimum (2021-2024 covers bull/bear/sideways/transitional regimes)
- **Universe**: Top 60 symbols by volume on Binance futures
- **Minimum data requirement**: 90% data completeness per symbol — drop symbols with gaps

### Walk-Forward Validation
- **12 folds** (monthly out-of-sample from Jan 2022 to Dec 2024)
- **Train window**: 6 months rolling (e.g., train on Jul-Dec 2021, test on Jan 2022)
- **In-sample**: First 6 months (Jul-Dec 2021)
- **Bootstrap**: 100 random subsamples per fold to verify stability
- **Metric**: Median R-multiple across all folds must be > 1.5

### Baseline Comparison
Every hypothesis must be compared against:
1. **Random entry** — enter random direction at same frequency as signal
2. **Buy-and-hold** — just hold BTC
3. **Naive momentum** — enter when price moves > X% regardless of signal

If hypothesis doesn't beat all 3 baselines → reject.

---

## Hypothesis 1: Altcoin Delay

### Theory
When BTC moves > 3% in 4 hours, altcoins (SOL, ADA, AVAX, etc.) follow with 1-4 hour delay. Large players allocateBTC first, then rotate to altcoins.

### Signal Definition

```
SIGNAL = 1 (LONG ALTCOIN) WHEN:
- BTC_4h_return > 3%
- Time_since_BTC_move = 1h OR 2h OR 4h
- Altcoin_4h_return < BTC_4h_return (delay confirmed)

SIGNAL = -1 (SHORT ALTCOIN) WHEN:
- BTC_4h_return < -3%
- Time_since_BTC_move = 1h OR 2h OR 4h  
- Altcoin_4h_return > BTC_4h_return (delay confirmed)
```

### Parameters to Optimize
- `btc_threshold`: [2.0%, 3.0%, 4.0%, 5.0%]
- `delay_window`: [1h, 2h, 4h] — which delay produces strongest alpha?
- `altcoin_universe`: [top 10 by volume, top 20, top 40]

### What to Measure
1. **Directional accuracy**: % of signals that move in predicted direction within 8h
2. **R-multiple distribution**: mean, median, 10th/90th percentile
3. **Regime breakdown**: performance in TRENDING vs RANGE vs TRANSITION
4. **Delay optimality**: which delay window (1h/2h/4h) has highest edge?

### What MUST Be Tested And MUST NOT BeIgnored
- [ ] **Survivorship bias**: Ensure altcoins are included even if they were delisted (e.g., LUNA) — cold hard truth, survivor bias kills many algos
- [ ] **Transaction costs**: Apply 0.05% maker fee + 0.1% taker fee per trade
- [ ] **Slippage**: Add 0.1% for TIER_1, 0.3% for TIER_2, 0.5% for TIER_3
- [ ] **Out-of-sample only**: Parameter optimization on train window only, never on test folds
- [ ] **Correlation with BTC**: If altcoin delay just = BTC momentum, reject

### Exit Rules (Fixed, Not Optimized)
- **Stop loss**: 2% on altcoin position
- **Take profit**: 4% on altcoin position (2R target)
- **Max hold**: 24 hours — if neither TP nor SL hit, exit at market close

### Rejection Criteria
- Median R-multiple < 1.0 → REJECT
- Only works in 1 regime → REJECT
- Loses to random baseline → REJECT

---

## Hypothesis 2: Volatility Compression

### Theory
After 72 hours of compressed volatility (< 50% of 30-day average ATR), price breakout in either direction has momentum. Direction is uncertain, but movement certainty is high.

### Signal Definition

```
VOL_30D_AVG = 30-period average of ATR(14)
VOL_CURRENT = ATR(14) on current candle

COMPRESSION = VOL_CURRENT < (VOL_30D_AVG * 0.50)

BREAKOUT = 
  - COMPRESSION == True for 72+ hours (3 consecutive days)
  - Current candle breaks high OR low of compression period
  
DIRECTION = 
  - If breakout up: LONG
  - If breakout down: SHORT
```

### Parameters to Optimize
- `compression_threshold`: [0.40, 0.50, 0.60] — ATR as % of 30d avg
- `compression_duration`: [48h, 72h, 96h]
- `atr_period`: [14, 20, 28]

### What to Measure
1. **Breakout success rate**: % of breakouts that reach 2R before hitting stop
2. **Mean R-multiple** when breakout occurs (ignoring time in compression)
3. **False breakout rate**: breakouts that immediately reverse
4. **Regime sensitivity**: does compression in TRENDING perform differently than in RANGE?

### What MUST Be Tested And MUST NOT Be Ignored
- [ ] **Excluded data during compression**: Don't count time sitting in compression as "no return" — only measure post-breakout moves
- [ ] **Stop hunts**: Did price briefly break and return? Count as stop-loss, not false signal
- [ ] **Direction randomness**: Signal says "move coming" but not "direction" — verify you aren't accidentally using future data to pick direction
- [ ] **Variable holding period**: Some breakouts take 4h, some take 20h — use ATR-based hold time, not fixed

### Exit Rules (Fixed, Not Optimized)
- **Stop loss**: 2R (2 × entry ATR)
- **Take profit**: 4R (4 × entry ATR) — compression breakouts tend to be big moves
- **Max hold**: 48 hours — if no exit, close at end

### Rejection Criteria
- Breakout success rate < 40% → REJECT
- Loses to "random direction after compression" → REJECT (direction skill required, not just movement detection)

---

## Hypothesis 3: Funding + Spot Divergence

### Theory
When funding rate is high (> 0.1% per 8h = 1.1% daily) but spot price isn't rising, longs are paying to hold but price momentum is failing. This divergence predicts short-term downward move.

### Signal Definition

```
FUNDING_RATE_8H = current funding rate (from endpoint)
SPOT_4h_RETURN = (spot_price_now - spot_price_4h_ago) / spot_price_4h_ago
FUTURES_4h_RETURN = (futures_price_now - futures_price_4h_ago) / futures_price_4h_ago

DIVERGENCE_LONG = FUNDING_RATE_8H > 0.1% AND SPOT_4h_RETURN < 0.5%
DIVERGENCE_SHORT = FUNDING_RATE_8H < -0.1% AND SPOT_4h_RETURN > -0.5%
```

Note: You need funding rate data. Verify Binance API provides historical funding rate — if only current, this hypothesis is UNTESTABLE and must be marked as blocked.

### Parameters to Optimize
- `funding_threshold`: [0.05%, 0.1%, 0.15%, 0.2%]
- `spot_threshold`: [0.0%, 0.5%, 1.0%] — how much "failure" to require
- `hold_duration`: [4h, 8h, 12h]

### What to Measure
1. **Directional accuracy**: Does high funding + flat spot predict DOWN more often than random?
2. **Entry timing**: Is 4h the right window, or should we wait longer after funding spike?
3. **Funding regime**: High funding during TRENDING markets vs RANGE markets — does signal strength change?

### What MUST Be Tested And MUST NOT Be Ignored
- [ ] **Data availability check FIRST**: If historical funding not available via free API → BLOCK THIS HYPOTHESIS, move to next
- [ ] **Funding frequency**: Funding settles every 8h — align signals to funding timestamps, not arbitrary hours
- [ ] **Survivorship in funding**: Some symbols have discontinuous funding history — handle or exclude
- [ ] **Funding resets**: After funding event, rate drops to 0 — confirm signal doesn't just catch the reset

### Exit Rules (Fixed, Not Optimized)
- **Stop loss**: 2%
- **Take profit**: 4% (2R)
- **Max hold**: 12 hours

### Rejection Criteria
- Directional accuracy < 45% → REJECT (worse than coin flip)
- Only works on BTC, not on other symbols → REJECT (too narrow)

---

## Composite Signal (All 3 Combined)

### Design Decision Point
Test the 3 hypotheses independently FIRST. Only move to composite if:
- At least 2 of 3 hypotheses show R-multiple > 1.5 independently
- They are not highly correlated (correlation < 0.6)

If both conditions met → design composite:

```
COMPOSITE_LONG = SIGNAL_1 == 1 AND SIGNAL_2 == 1 AND (SIGNAL_3 == 1 OR SIGNAL_3 == 0)
COMPOSITE_SHORT = SIGNAL_1 == -1 AND SIGNAL_2 == 1 AND (SIGNAL_3 == -1 OR SIGNAL_3 == 0)
```

Note: Hypothesis 2 (volatility compression) signals "movement coming" but not direction. Use Hypothesis 1 and 3 for direction, Hypothesis 2 as filter (only trade when compression breaks + directional signal fires).

### Composite Exit Rules
- Same as individual: 2% stop, 4% TP, 12h max hold

---

## Deliverables Per Hypothesis

For each hypothesis (1, 2, 3), the test must produce:

1. **`results_{hypo_name}.csv`**:
   - `timestamp`, `symbol`, `signal_direction`, `entry_price`, `exit_price`, `r_multiple`, `hold_duration_hours`, `regime`

2. **`stats_{hypo_name}.json`**:
   - `total_signals`, `median_r_multiple`, `mean_r_multiple`, `std_r_multiple`, `win_rate`, `avg_hold_hours`, `regime_breakdown`

3. **`baseline_comparison_{hypo_name}.json`**:
   - `random_baseline_r`, `momentum_baseline_r`, `buy_hold_r`, `hypothesis_r`

4. **`fold_results_{hypo_name}.json`**:
   - Array of 12 fold results with train period, test period, r_multiple for each

5. **`rejection_decision_{hypo_name}.txt`**:
   - Either "ACCEPTED: R-multiple X across Y folds" or "REJECTED: reason"

---

## Test Execution Order

```
Week 1-2: Hypothesis 1 (Altcoin Delay)
Week 3-4: Hypothesis 2 (Volatility Compression)
Week 5-6: Hypothesis 3 (Funding Divergence) — BLOCK if data unavailable
Week 7-8: Composite design + validation if 2+ accepted
Week 9-10: Final report + system integration decision
```

---

## Critical Gating Rules

1. **If any single hypothesis passes** (R > 1.5, beats all baselines, works in 2+ regimes) → proceed to system integration plan
2. **If NONE pass** → STOP. Do not build execution pipeline on zero-expectancy strategy. Revisit alpha search.
3. **If only 1 passes** → Write that one into V7, but mark it as single-point-of-failure. Continue alpha search in parallel.
4. **Never optimize exit rules** — all exits are fixed at 2R/4R per spec. This prevents overfitting.

---

## Data Verification Checklist (Before Any Testing)

- [ ] Binance klines for 60 symbols from 2021-01-01 to 2024-12-31 available
- [ ] No gaps > 24h in any symbol's data
- [ ] Funding rate history accessible (test API before starting Hypho 3)
- [ ] Disk space: ~500MB for raw data + cache

If any item fails → fix data pipeline BEFORE writing backtest logic.
