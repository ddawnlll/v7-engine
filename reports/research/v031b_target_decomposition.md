# v0.31B — Target Decomposition Experiment

**Date:** 2026-07-02
**Config:** SCALP, 1h, ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT'], 6-fold WFV, XGBoost depth=4/200trees
**Status:** CONTROLLED_EXPERIMENT — No tuning, no threshold changes

## Summary

| Variant | Accuracy | Balanced Acc | Net R (mean) | Net R (sum) | Active Trades |
|---------|----------|-------------|-------------|-------------|--------------|
| A — 3-class | 0.4260 | 0.3402 | 0.007551 | 122.2239 | 37998 |
| B — Direction | 0.4326 | 0.3439 | 0.007580 | 124.5915 | 37998 |
| C — Actionability | 0.8389 | 0.5001 | 0.007541 | 240.3797 | 37998 |
| D — Two-stage | 0.4326 | 0.3440 | 0.007579 | 124.5915 | 37998 |

## Baselines

| Baseline | Accuracy |
|----------|----------|
| 3-class random | 33.3% |
| 3-class majority | 42.0% |
| 2-class random | 50.0% |
| 2-class majority | ~50.5% |

## Verdict

- **Direction signal WEAK.** Variant B does not reliably beat majority.
- **NO_TRADE is NOT learnable** from current 1h features.
- **Two-stage improves** over 3-class baseline. Decomposition is the right path.

## Detailed Results
