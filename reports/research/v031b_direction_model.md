# v0.31B — Variant B — Direction-Only (LONG vs SHORT)

**Config:** SCALP, 1h, ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT'], 6-fold WFV

## Variant B — Direction-Only (LONG vs SHORT)

### Aggregate
| Metric | Value |
|--------|------|
| Accuracy | 0.4326 |
| Balanced Acc | 0.3439 |
| Correct/Total | 16437/37998 |
| Net R (mean) | 0.007580 |
| Net R (sum) | 124.5915 |
| Active Trades | 37998 |

### Per-Class Accuracy
- class_0: 0.5330
- class_1: 0.4988
- class_2: 0.0000

### Confusion Matrix

| True \\ Pred | 0 | 1 | 2 |
|---|---|---|---|
| 0 | 8367 | 7332 | 0 |
| 1 | 8108 | 8070 | 0 |
| 2 | 3107 | 3014 | 0 |

### Per-Fold

  Fold   1 | acc=0.5188 | net_R=0.004517 | trades=5224
  Fold   2 | acc=0.5182 | net_R=0.007339 | trades=5315
  Fold   3 | acc=0.5051 | net_R=0.008883 | trades=5244
  Fold   4 | acc=0.5141 | net_R=0.011605 | trades=5357
  Fold   5 | acc=0.5092 | net_R=0.005854 | trades=5340
  Fold   6 | acc=0.5283 | net_R=0.007271 | trades=5397