# ALPHAFORGE_SCALP_1H_DIRECTION_V01

**Date:** 2026-07-02 01:40 UTC
**Status:** RESEARCH_CANDIDATE — NOT V7_READY, NOT PAPER_READY, NOT LIVE_READY

## Architecture Change

| Change | Before | After | Evidence |
|--------|--------|-------|----------|
| Target | 3-class (LONG/SHORT/NO_TRADE) | 2-class (LONG vs SHORT) | NO_TRADE balanced acc = 50.01% (random) |
| Confidence threshold | 0.55 | DISABLED | Flat calibration curve, 0.5% gain for 91% trade loss |
| NO_TRADE treatment | Supervised class | REMOVED from direction training | Actionability model confirmed unlearnable |

## Config
| Param | Value |
|-------|-------|
| Mode | SCALP |
| Interval | 1h |
| Symbols | ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT'] |
| WFV folds | 6 |
| Features | 60 |
| Model | XGBoost depth=4, 200 trees |

## Results
| Metric | Value | vs Random | vs Majority |
|--------|-------|-----------|-------------|
| OOS Accuracy | 0.5149 | BEATS (0.5) | BEATS (0.5080) |
| Balanced Acc | 0.5138 | | |
| LONG Accuracy | 0.4494 | | |
| SHORT Accuracy | 0.5782 | | |
| Train/OOS Gap | 0.1827 | | |
| Net R (mean) | 0.007648 | | |
| Net R (sum) | 125.0365 | | |
| Profit Factor | 242647.8601 | | |
| Fold Stability | 0.9878 | | |
| Active Trades | 31752 | | |

## Confusion Matrix

| True \\ Pred | LONG | SHORT |
|-------------|------|-------|
| LONG       |   7021 |   8601 |
| SHORT      |   6803 |   9327 |

## Per-Fold
| Fold | Train | Val | Train Acc | Val Acc | LONG Acc | SHORT Acc | Net R |
|------|-------|-----|-----------|---------|----------|-----------|-------|
| 1 | 10584 | 5292 | 0.8101 | 0.5191 | 0.1117 | 0.8855 | 0.004723 |
| 2 | 24696 | 5292 | 0.7294 | 0.5248 | 0.7660 | 0.2718 | 0.007722 |
| 3 | 38808 | 5292 | 0.6911 | 0.5068 | 0.7406 | 0.2821 | 0.009097 |
| 4 | 52920 | 5292 | 0.6674 | 0.5127 | 0.3868 | 0.6406 | 0.011368 |
| 5 | 67032 | 5292 | 0.6498 | 0.5176 | 0.4873 | 0.5459 | 0.005819 |
| 6 | 81144 | 5292 | 0.6373 | 0.5083 | 0.1802 | 0.8219 | 0.007226 |

## DataPassport
- Source: binance
- Real data: True
- PIT safe: True
- Coverage: 100.0%
- Backtest trustworthy: False

## V7 Status

**RESEARCH_CANDIDATE** — This candidate is NOT ready for V7 gates.

| Gate | Status | Reason |
|------|--------|--------|
| V7_READY | ❌ | Research candidate, not production-ready |
| PAPER_READY | ❌ | Requires V7 promotion gate evidence |
| LIVE_READY | ❌ | Requires paper trading validation |

## Next Candidate Iteration (v0.31E)

One improvement from:
- Feature reduction (feature-family ablation)
- Regularization (shallower trees, fewer estimators)
- Funding cost correction with real funding rate data
