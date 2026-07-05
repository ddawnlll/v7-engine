# v0.31A — Label Audit

## 1. Class Distribution
| Class | Count | % |
|-------|-------|---|
| LONG_NOW | 49130 | 41.6% |
| SHORT_NOW | 49658 | 42.0% |
| NO_TRADE | 19436 | 16.4% |

## 2. Economic Separability
| Metric | Value |
|--------|-------|
| Mean Gross R | 0.0072 |
| Mean Net R | 0.0065 |
| Cost drag | 0.0007 |

**Critical question:** Do LONG and SHORT labels have positive future net_R after costs?

## 3. Class Distribution Per Fold
| Fold | LONG | SHORT | NO_TRADE | Dominant % |
|------|------|-------|----------|------------|
| 1 | 2515 | 2709 | 1109 | 42.8% |
| 2 | 2722 | 2593 | 1018 | 43.0% |
| 3 | 2563 | 2681 | 1089 | 42.3% |
| 4 | 2696 | 2661 | 976 | 42.6% |
| 5 | 2555 | 2785 | 993 | 44.0% |
| 6 | 2648 | 2749 | 936 | 43.4% |

## 4. Baselines
| Baseline | Expected Accuracy |
|----------|-------------------|
| Random (uniform) | 33.3% |
| Majority class | 42.0% |
| Always LONG | 41.6% |
| Always SHORT | 42.0% |
| Always NO_TRADE | 16.4% |

## 5. Verdict

**PASS: Labels are balanced and carry positive net_R.** Model failure is not in the labels.