# v0.31A — Confidence Calibration

## 1. Bucket Analysis

| Confidence | Count | % of Total | Accuracy | LONG | SHORT | NO_TRADE |
|------------|-------|------------|----------|------|-------|----------|
| 0.30-0.35 | 66 | 0.2% | 0.3788 | 28 | 23 | 15 |
| 0.35-0.40 | 1485 | 3.9% | 0.3859 | 699 | 671 | 115 |
| 0.40-0.45 | 14109 | 37.1% | 0.4216 | 6206 | 7823 | 80 |
| 0.45-0.50 | 12317 | 32.4% | 0.4372 | 6016 | 6290 | 11 |
| 0.50-0.55 | 6619 | 17.4% | 0.4211 | 3964 | 2650 | 5 |
| 0.55-0.60 | 2551 | 6.7% | 0.4269 | 1522 | 1029 | 0 |
| 0.60-1.00 | 851 | 2.2% | 0.4442 | 429 | 421 | 1 |

## 2. Decision Rule Check

- Accuracy above 0.55: 0.4312 (3402 samples)
- Accuracy below 0.55: 0.4255 (34596 samples)
- **Verdict:** Confidence does NOT meaningfully predict accuracy. Threshold tuning would be blind.