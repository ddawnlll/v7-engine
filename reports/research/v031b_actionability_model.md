# v0.31B — Variant C — Actionability (TRADE vs NO_TRADE)

**Config:** SCALP, 1h, ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT'], 6-fold WFV

## Variant C — Actionability (TRADE vs NO_TRADE)

### Aggregate
| Metric | Value | Baseline | Delta |
|--------|------|----------|-------|
| Accuracy | 0.8389 | 0.426 | +0.4129 |
| Balanced Acc | 0.5001 | 0.3402 | +0.1599 |
| Correct/Total | 31877/37998 | |
| Net R (mean) | 0.007541 | 0.007551 |
| Net R (sum) | 240.3797 | 122.2239 |
| Active Trades | 37998 | |

### Per-Class Accuracy
- class_0: 0.0002
- class_1: 1.0000

### Confusion Matrix

| True \\ Pred | 0 | 1 |
|---|---|---|
| 0 | 1 | 6120 |
| 1 | 1 | 31876 |

### Per-Fold

  Fold   1 | acc=0.8249 | net_R=0.004383 | trades=6333
  Fold   2 | acc=0.8393 | net_R=0.007406 | trades=6333
  Fold   3 | acc=0.8280 | net_R=0.008793 | trades=6333
  Fold   4 | acc=0.8459 | net_R=0.011500 | trades=6333
  Fold   5 | acc=0.8432 | net_R=0.005996 | trades=6333
  Fold   6 | acc=0.8522 | net_R=0.007111 | trades=6333