# v0.31A — Model Failure Analysis

## 1. Fold-by-Fold Performance
| Fold | Train Acc | OOS Acc | Gap | Active Trades | Low Conf % |
|------|-----------|---------|-----|---------------|------------|
| 1 | 0.6749 | 0.4173 | 0.2575 | 1216 | 80.8% |
| 2 | 0.5959 | 0.4341 | 0.1618 | 207 | 96.7% |
| 3 | 0.5654 | 0.4042 | 0.1612 | 1262 | 80.1% |
| 4 | 0.5427 | 0.4331 | 0.1095 | 450 | 92.9% |
| 5 | 0.5377 | 0.4221 | 0.1156 | 255 | 96.0% |
| 6 | 0.5275 | 0.4450 | 0.0826 | 12 | 99.8% |

## 2. Per-Class Accuracy (OOS, no threshold)
| Fold | LONG Acc | SHORT Acc | NO_TRADE Acc |
|------|----------|-----------|--------------|
| 1 | 0.0736 | 0.8933 | 0.0343 |
| 2 | 0.8924 | 0.1207 | 0.0069 |
| 3 | 0.7948 | 0.1940 | 0.0028 |
| 4 | 0.4611 | 0.5637 | 0.0000 |
| 5 | 0.5902 | 0.4183 | 0.0000 |
| 6 | 0.2088 | 0.8236 | 0.0011 |

## 3. Confusion Matrix (OOS, all folds)

| True \ Pred | LONG | SHORT | NO_TRADE |
|-------------|------|-------|----------|
| LONG       |   7955 |   7657 |     87 |
| SHORT      |   7905 |   8182 |     91 |
| NO_TRADE   |   3004 |   3068 |     49 |

**Column dominance:** The model's most-predicted class for each true label: {0: 0, 1: 1, 2: 1}
**Correct predictions:** 42.6%
**Off-diagonal (errors):** 57.4%

## 4. Fold Stability
| Metric | Value |
|--------|-------|
| Mean OOS acc | 0.4260 |
| Std OOS acc  | 0.0132 |
| Min OOS acc  | 0.4042 |
| Max OOS acc  | 0.4450 |
| Fold stability (1 - CV) | 0.9691 |

## 5. Diagnosis

**BORDERLINE:** Train (57.4%) > OOS (42.6%), gap=14.8%. May improve with regularization.