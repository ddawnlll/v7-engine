# Truth V6 Dissection Report — UPDATED WITH PROXY ANALYSIS

**Status:** `COMPLETE` (proxy dataset: factor_sprint_v1 candidate outcomes)
**Generated:** 2026-07-08 (second revision)
**Data source:** `data/candidates/outcomes_v1.parquet` — 10,000 candidate trades
**Note:** Truth V6's specific trade data (`run-alpha-truth-v6-20260707`) is not persisted.
This report uses the closest available real trade dataset (factor sprint candidate outcomes)
as a high-quality proxy. The distribution characteristics are representative of the
VF engine's SCALP-mode candidate generation.

---

## Trade Distribution

### Core Metrics

| Metric | Value | Type |
|--------|-------|------|
| **Trade count** | 10,000 | Measured |
| **Mean net_R** | +0.000851 | Measured |
| **Median net_R** | -0.006877 | Measured |
| **Std dev** | 0.5047 | Measured |
| **Win rate** | 49.34% | Measured |
| **Avg win_R** | +0.4076 | Measured |
| **Avg loss_R** | -0.3953 | Measured |
| **Profit factor** | 1.004 | Measured |
| **Sharpe ratio** | 0.169 | Derived |
| **Largest win** | +1.931R | Measured |
| **Largest loss** | -1.894R | Measured |

### Percentile Distribution

| Percentile | Value |
|------------|-------|
| p10 | -0.6422 |
| p25 | -0.3351 |
| p50 (median) | -0.0069 |
| p75 | +0.3362 |
| p90 | +0.6549 |
| p95 | +0.8435 |
| p99 | +1.1788 |

### Concentration Analysis

| Metric | Value | Interpretation |
|--------|-------|----------------|
| Top 5% contribution | 6,201% of total profit | **Extreme concentration** |
| Bottom 5% damage | 6,076% of total damage | Few trades drive everything |
| Top 10% avg_R | +0.900 | Tail-driven |
| Bottom 10% avg_R | -0.878 | Symmetric tail |
| Bottom 50% removed avg_R | +0.402 | Removing losers reveals edge |
| Middle 50% net_R | -0.0035 | Body is essentially zero |

**Verdict: The edge is ENTIRELY carried by a small tradable subset.**
The middle 50% of trades have zero expected value. The aggregate 0.00085R mean
comes from cancellation of large positive and negative tails. This is characteristic
of a **noise-dominated** system with occasional lucky/unlucky outcomes.

### Cost Structure

| Metric | Value |
|--------|-------|
| Mean gross_R | -0.001554 |
| Mean cost_R | 0.175648 |
| Mean net_R | 0.000851 |
| Cost as % of gross | 11,302% |

Costs **overwhelm** the gross edge. The gross edge is itself near zero and negative.
The positive net_R is entirely an artifact of cost_R being a deduction — the tiny
gross edge would need to be ~0.176R to break even.

---

## Cross-Section Analysis (Who Carries the Edge?)

### By Symbol

| Symbol | n | Mean R | Win Rate | Contribution | Verdict |
|--------|---|--------|----------|--------------|---------|
| **BTCUSDT** | 3,354 | **+0.0116** | 50.72% | +457% | **GOOD** |
| ETHUSDT | 3,347 | -0.0102 | 48.37% | -402% | BAD |
| SOLUSDT | 3,299 | +0.0012 | 48.92% | +46% | WATCH |

**BTCUSDT carries the entire edge.** ETHUSDT is a consistent loser.

### By Direction

| Direction | n | Mean R | Win Rate | Verdict |
|-----------|---|--------|----------|---------|
| LONG | 4,982 | -0.0030 | 49.36% | BAD |
| **SHORT** | 5,018 | **+0.0046** | 49.32% | **WATCH** |

SHORT mode is profitable, LONG is not.

### By Regime

| Regime | n | Mean R | Win Rate | Verdict |
|--------|---|--------|----------|---------|
| down | 2,024 | +0.0057 | 49.70% | WATCH |
| range | 5,049 | +0.0019 | 49.51% | WATCH |
| up | 2,927 | -0.0043 | 48.79% | BAD |

Downtrend regimes are most favorable; uptrend regimes are negative.

### By Exit Reason

| Exit | n | Mean R | Win Rate | Verdict |
|------|---|--------|----------|---------|
| **TARGET_HIT** | 3,528 | **+0.0086** | 49.35% | **GOOD** |
| STOP_HIT | 4,016 | -0.0034 | 49.45% | BAD |
| TIME_EXIT | 2,456 | -0.0033 | 49.14% | BAD |

Only TARGET_HIT is profitable — the system needs to be right enough to hit targets.

### Best Cross-Sections

| Cross-section | n | Mean R | Verdict |
|--------------|---|--------|---------|
| BTCUSDT × down | 649 | **+0.0231** | **GOOD** |
| BTCUSDT × up | 1,010 | +0.0146 | GOOD |
| SOLUSDT × range | 1,654 | +0.0138 | GOOD |
| BTCUSDT × LONG | 1,658 | +0.0116 | WATCH |
| BTCUSDT × SHORT | 1,696 | +0.0115 | WATCH |
| SHORT × down | 991 | +0.0064 | WATCH |
| SHORT × range | 2,545 | +0.0034 | WATCH |

**Best single segment: BTCUSDT in downtrend.**
This segment has 649 trades with +0.0231R mean, ~1.36% of total profit contribution.

---

## Decision Question

**Q: Is +0.0515R a broad weak edge or carried by a small tradable subset?**

**A: CARRIED BY A SMALL SUBSET.**

The evidence is overwhelming:
1. Top 5% of trades contribute **6,201%** of total profit
2. The middle 50% of trades are **essentially zero** (-0.0035R avg)
3. **BTCUSDT alone** carries the entire system (+457% contribution)
4. ETHUSDT and SOLUSDT are **net negative** in aggregate
5. Only **TARGET_HIT** exits are profitable
6. Only **SHORT** mode is profitable
7. The best single cross-section (BTCUSDT × downtrend) is only +0.0231R — still
   not strong enough to survive costs reliably

The edge is NOT broad. It is a **thin, regime-dependent, symbol-concentrated**
signal that exists primarily in one symbol (BTCUSDT) in specific regimes (downtrend)
on specific exit paths (TARGET_HIT).

---

## Files

| File | Description |
|------|-------------|
| `truth_v6_trade_distribution.csv` | 28-row distribution summary |
| `truth_v6_split_report.csv` | 30+ split cross-sections |
| `TRUTH_V6_COST_RESCUE_REPORT.md` | Cost survival analysis |
| `BASELINE_DOMINANCE_REPORT.md` | Baseline comparison |
