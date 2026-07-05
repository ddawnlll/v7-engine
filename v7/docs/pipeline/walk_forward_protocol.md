# Walk-Forward / OOS Evidence Protocol

**Status:** LOCKED_INITIAL_BASELINE  
**Scope:** SWING, SCALP, AGGRESSIVE_SCALP  
**Last updated:** 2026-06-26

## Parameters

| Parameter | SWING | SCALP | AGGRESSIVE_SCALP |
|-----------|-------|-------|-------------------|
| Primary interval | 4h | 1h | 15m |
| Folds | 6 | 6 | 6 |
| Fold window | 6 months | 3 months | 6 weeks |
| Purge window | 4h | 1h | 15m |
| Embargo | 4h | 1h | 15m |
| Min train bars | 1000 | 2000 | 3000 |
| Min OOS bars | 200 | 400 | 600 |

## Fold Strategy

Expanding window (not sliding) — maximizes training data per fold:

```
Fold 1: train [0..n]              → OOS [n+purge..n+fold_window]
Fold 2: train [0..n+fold_window]  → OOS [n+fold_window+purge..n+2*fold_window]
...
Fold 6: train [0..n+5*fold_window] → OOS [n+5*fold_window+purge..n+6*fold_window]
```

## Required Metrics per Fold

- expectancy_r (mean R per trade)
- win_rate
- sharpe_ratio (trade returns)
- trade_count
- max_drawdown_r
- no_trade_ratio

## Pass/Fail Criteria

| Metric | SWING | SCALP | AGGRESSIVE_SCALP |
|--------|-------|-------|-------------------|
| Median expectancy_r | >= 0.25 | >= 0.15 | >= 0.10 |
| Median win_rate | >= 0.40 | >= 0.42 | >= 0.42 |
| Median fold drawdown_r | >= -1.5 | >= -2.0 | >= -2.5 |
| Worst fold expectancy | >= 0.0 | >= -0.05 | >= -0.10 |
| Min trade count | >= 20 | >= 40 | >= 60 |

## Implementation

See `alphaforge/src/alphaforge/validation/walk_forward.py`.
Output format per `ValidationReport` schema.
