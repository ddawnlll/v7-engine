# Truth V6 Robustness Report

**Generated:** 2026-07-08T11:15:00Z

## Executive Summary

Truth V6 fails robustness validation. The edge is:
1. **Not scalable** — negative R on 12-symbol and 19-symbol expansions
2. **Threshold-sensitive** — positive only at threshold 0.55, negative at all other thresholds
3. **Concentrated** — 99% SOLUSDT in the only positive config
4. **Cost-fragile** — fails at 2x cost stress

## Symbol Split (Full Universe, 19 symbols)

| Symbol | Trades | Total R | Mean R |
|--------|--------|---------|--------|
| BTCUSDT | 147 | -41.24 | -0.2806 |
| SOLUSDT | 78 | -24.62 | -0.3157 |
| LINKUSDT | 36 | -12.74 | -0.3538 |
| XRPUSDT | 31 | +6.06 | +0.1953 |
| NEARUSDT | 30 | -7.23 | -0.2410 |
| INJUSDT | 25 | +1.74 | +0.0695 |
| AVAXUSDT | 11 | +9.67 | +0.8791 |
| ATOMUSDT | 10 | +3.20 | +0.3196 |
| OPUSDT | 10 | +3.67 | +0.3671 |
| APTUSDT | 8 | -7.14 | -0.8927 |
| SUIUSDT | 7 | -1.94 | -0.2774 |
| RUNEUSDT | 7 | -1.40 | -0.1997 |
| FILUSDT | 3 | +2.83 | +0.9444 |
| DOGEUSDT | 2 | +0.30 | +0.1495 |
| ARBUSDT | 2 | +2.53 | +1.2674 |
| ADAUSDT | 2 | -2.08 | -1.0393 |
| BNBUSDT | 1 | -1.13 | -1.1318 |

8 symbols positive, 8 negative. But overall R is -0.165 — the negatives dominate.

## Direction Split (Full Universe)

| Direction | Count | Mean R |
|-----------|-------|--------|
| LONG | 18 | -0.2774 |
| SHORT | 390 | -0.1601 |

## Time Split (Full Universe)

| Period | Count | Mean R |
|--------|-------|--------|
| First half | 204 | -0.1244 |
| Second half | 204 | -0.2062 |

Both halves negative — edge is not concentrated in any time period.

## Cost Stress (P0 baseline, 4 symbols)

| Cost Multiplier | Cost/Trade R | Cost-Adj R | Verdict |
|-----------------|-------------|------------|---------|
| 1x | 0.0524 | +0.0063 | PASS |
| 2x | 0.1048 | -0.0461 | FAIL |
| 5x | 0.2619 | -0.2033 | FAIL |

## 12-Symbol Expansion

| Metric | Value |
|--------|-------|
| Symbols | 12 |
| Trades | 152 |
| Raw R | -0.3217 |
| Cost-adj R | -0.3678 |
| Top symbol | ARBUSDT (38.8%) |
| Positive symbols | 2 |
| Negative symbols | 6 |

**Catastrophic failure** — deeply negative across the board.

## Baseline Comparison

| Baseline | Expected R | Truth V6 (full) | Beats? |
|----------|-----------|-----------------|--------|
| Random (50% WR) | 0.0 | -0.165 | NO |
| Direction-shuffled | ~0.0 | -0.165 | NO |

Truth V6 underperforms random on the expanded universe.

## Verdict

**TRUTH_V6_REJECT_AFTER_EXPANSION** — The edge does not survive expansion beyond SOLUSDT. It is a single-symbol specialist at a specific confidence threshold, not a scalable alpha.

## Files

- `truth_v6_symbol_split.csv` — per-symbol metrics
- `truth_v6_direction_split.csv` — LONG/SHORT split
- `truth_v6_session_split.csv` — time-based split
- `truth_v6_cost_stress.csv` — cost multiplier stress test
- `truth_v6_oos_split.csv` — first-half/second-half split
- `truth_v6_baseline_comparison.csv` — baseline comparison
