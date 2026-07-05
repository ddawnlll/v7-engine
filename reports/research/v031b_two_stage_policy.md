# v0.31B — Variant D — Two-Stage Policy

**Config:** SCALP, 1h, ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT'], 6-fold WFV

## Variant D — Two-Stage Policy

### Aggregate
| Metric | Value | Baseline | Delta |
|--------|------|----------|-------|
| Accuracy | 0.4326 | 0.426 | +0.0066 |
| Balanced Acc | 0.344 | 0.3402 | +0.0038 |
| Correct/Total | 16438/37998 | |
| Net R (mean) | 0.007579 | 0.007551 |
| Net R (sum) | 124.5915 | 122.2239 |
| Active Trades | 37998 | |

### Per-Class Accuracy
- class_0: 0.5330
- class_1: 0.4988
- class_2: 0.0002

### Confusion Matrix

| True \\ Pred | 0 | 1 | 2 |
|---|---|---|---|
| 0 | 8367 | 7331 | 1 |
| 1 | 8108 | 8070 | 0 |
| 2 | 3107 | 3013 | 1 |

### Per-Fold

  Fold   1 | acc=0.4281 | net_R=0.004515 | trades=6333
  Fold   2 | acc=0.4349 | net_R=0.007339 | trades=6333
  Fold   3 | acc=0.4183 | net_R=0.008883 | trades=6333
  Fold   4 | acc=0.4349 | net_R=0.011605 | trades=6333
  Fold   5 | acc=0.4293 | net_R=0.005854 | trades=6333
  Fold   6 | acc=0.4502 | net_R=0.007271 | trades=6333