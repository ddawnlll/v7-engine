# Conservative Q-Learning (CQL) — Deep Dive

## Abstract

CQL (Kumar et al. 2020, NeurIPS 2020) is an offline RL algorithm that explicitly penalizes Q-values on out-of-distribution actions while pushing up Q-values on dataset actions. It produces a **provable lower bound** on the true policy value — systematically pessimistic estimates. CQL augments the standard Bellman error with a simple Q-value regularizer, making it straightforward to implement on top of existing Q-learning frameworks.

## Why It Matters for V7

CQL is recommended as the **ensemble cross-check** for IQL in V3. When CQL and IQL disagree significantly, the critic emits REQUIRE_REVIEW. CQL's theoretical lower-bound guarantee provides a safety net that IQL's implicit in-sample approach does not formally prove. For financial applications where overestimation = real money loss, a provably conservative estimate is valuable.

## What the Literature Says

### The CQL Regularizer

```
L_CQL = standard_Bellman_error + α · (E_{s~D, a~π}[Q(s,a)] - E_{s~D, a~D}[Q(s,a)])
```

- The first expectation pushes DOWN Q-values for actions the learned policy would select (potentially OOD)
- The second expectation pushes UP Q-values for actions in the dataset
- The net effect: Q-values for OOD actions are systematically penalized
- Result: E_{π}[Q^CQL(s,a)] ≤ E_{π}[Q^true(s,a)] — a lower bound

### Key Hyperparameter: α

| α | Behavior | Risk |
|---|---------|------|
| Small (0.1) | Mild conservatism | May still overestimate |
| Medium (1.0) | Moderate conservatism | Typical starting point |
| Large (10.0) | Strong conservatism | May be overly pessimistic → conservative collapse |

### Theoretical Guarantees

CQL provides stronger theoretical guarantees than IQL: it provably lower-bounds the true policy value under certain assumptions. IQL lacks this formal guarantee (it relies on the empirical property that in-sample evaluation prevents OOD queries).

### D4RL Comparison

CQL and IQL achieve comparable performance on D4RL benchmarks. CQL is slightly better on datasets with narrow behavior policy coverage; IQL is slightly better on datasets with broader coverage and is more stable across hyperparameter settings.

## How It Applies to V7

1. **Cross-check with IQL**: Train both. When IQL says ALLOW and CQL says VETO → REQUIRE_REVIEW.
2. **Conservative baseline**: CQL provides the "pessimistic" estimate; IQL provides the "realistic" estimate. The truth is likely between them.
3. **Safety-critical regime**: In HIGH_VOL_TRANSITION or anomaly-detected states, CQL's conservative estimate may be more appropriate than IQL's.

## How It Can Fail

| Failure Mode | Cause | Mitigation |
|-------------|-------|-----------|
| **Conservative collapse** | α too high → Q-values driven to minimum → always NO_TRADE | α tuning; bounded veto rate check |
| **α sensitivity** | Small α changes produce large behavior changes | Sensitivity analysis in training |
| **Over-penalization of good OOD actions** | Some OOD actions are genuinely better; CQL penalizes them all | IQL as primary; CQL as cross-check |
| **Computational overhead** | Training two models doubles cost | Acceptable for offline training (not inference) |

## Decision: USE LATER (V3 ensemble cross-check)

CQL is the recommended ensemble member for V3. Train alongside IQL; use disagreement as reliability signal. Not suitable as primary (IQL is simpler and empirically more stable).
