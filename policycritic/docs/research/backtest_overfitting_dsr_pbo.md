# Backtest Overfitting — DSR, PBO, CSCV

## Abstract

Backtest overfitting is the primary failure mode in quantitative finance: a strategy that performs brilliantly in backtest but loses money out-of-sample. Bailey & Lopez de Prado (2014, 2016) developed two key tools: the **Deflated Sharpe Ratio (DSR)** corrects the Sharpe ratio for selection bias under multiple testing, and the **Probability of Backtest Overfitting (PBO)** estimates via Combinatorially Symmetric Cross-Validation (CSCV) the probability that the "best" in-sample strategy underperforms the median out-of-sample.

## Why It Matters for V7

Every Policy Critic version transition requires DSR p < 0.05 and PBO < 0.10. These are non-negotiable evidence gates. Without them, any apparent critic improvement is indistinguishable from backtest overfitting noise.

## What the Literature Says

### Deflated Sharpe Ratio (DSR)

```
DSR = P[SR_true > 0 | SR_observed, N_trials, T_obs, skew, kurtosis]
```

- Corrects for: selection bias (N trials), non-Normal returns (skew, kurtosis), sample length (T)
- Larger N → lower DSR (harder to be significant)
- For N=100 trials, T=5 years, SR_observed=1.0: DSR p ≈ 0.3 (NOT significant at 0.05)
- Implication: most published backtests are statistically insignificant

### Probability of Backtest Overfitting (PBO)

```
PBO = P[SR_OOS(IS-optimal) < Median(SR_OOS_all)]
```

CSCV procedure:
1. Split returns into N equal-sized blocks
2. Form all combinations of k blocks as train, remaining as test
3. For each combination: compute SR_IS and SR_OOS
4. Build distribution of logits: λ = log(SR_IS / (1 - SR_OOS))
5. PBO = ∫_{-∞}^0 f(λ) dλ — mass where IS-optimal underperforms OOS median

### "Pseudo-Mathematics and Financial Charlatanism" (Bailey et al. 2014)

Key finding: "Minimum backtest length for SR=1.0 to be significant at 5% is ~64 years under random walk null." Most strategies with impressive backtests have near-zero OOS performance. PBO is typically 50-95% for overfit strategies.

## How It Applies to V7

1. **DSR gate**: Any critic version claiming improvement must have DSR p < 0.05 after correcting for the number of critic variants tested
2. **PBO gate**: PBO < 0.10 means <10% chance that the "best" critic configuration is actually worse than random selection
3. **Both required**: DSR and PBO together provide complementary protection — DSR protects against multiple testing, PBO protects against overfitting the selection process

## How It Can Fail

| Failure Mode | Mitigation |
|-------------|-----------|
| N_trials underestimated | Overcount: log every hyperparameter combination tested |
| Non-Normal returns violate DSR assumptions | DSR already corrects for skew and kurtosis |
| CSCV block size mis-specified | Sensitivity analysis across block sizes |
| PBO computation expensive | Acceptable — offline evaluation only |

## Decision: USE NOW (mandatory for all version transitions)

DSR and PBO are non-negotiable evidence gates. V1→V2, V2→V3, V3→V4 all require both. Infrastructure must be built in Phase 3.
