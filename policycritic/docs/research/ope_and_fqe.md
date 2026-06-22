# Off-Policy Evaluation (OPE) / Fitted Q-Evaluation (FQE)

## Abstract

Off-Policy Evaluation (OPE) answers: "How good is this new policy using only data from the old policy?" Fitted Q-Evaluation (FQE) is the most practical OPE method: learn Q^π_new from behavioral data, estimate V^π_new by averaging Q over initial states, compare to behavioral policy. Fu et al. (2021, ICLR) established FQE as the most reliable OPE method across D4RL benchmarks.

## Why It Matters for V7

OPE/FQE is **MANDATORY** before any live critic deployment. Without OPE, we cannot: distinguish skill from luck, detect backtest overfitting, estimate real-world performance, or calibrate critic recommendations. The analyst's analogy: you wouldn't fly a new airplane design with passengers without wind-tunnel testing. OPE is the wind tunnel for RL policies.

## What the Literature Says

### FQE Algorithm

1. Split behavioral data into training and evaluation sets
2. On training set: fit Q^π_new(s,a) via iterative Bellman minimization (same as offline RL training)
3. On evaluation set: estimate V^π_new = E_{s~D_eval, a~π_new(·|s)} [Q^π_new(s,a)]
4. Compare V^π_new to behavioral policy performance V^π_β

### Key Findings from Fu et al. (2021)

- FQE consistently outperforms importance sampling (IS) and doubly robust (DR) methods
- IS methods have prohibitively high variance with long horizons and continuous actions
- FQE is robust to moderate distribution shift
- Spearman rank correlation with true policy values is high (>0.8 on most tasks)

### Importance Sampling Limitations in Trading

IS reweights behavioral trajectories by π_new(a|s)/π_β(a|s). For trading: (a) action space is small (3 actions), so IS variance is lower than continuous control, (b) but long episode horizons amplify variance exponentially, (c) behavioral policy may never take some actions → weight = 0 → IS fails.

## How It Applies to V7

1. **V2→V3 gate**: FQE must show that IQL critic's estimated value overlaps observed performance
2. **Ongoing monitoring**: Compare FQE estimates to realized outcomes during shadow burn-in
3. **FQE CI width**: If 95% CI > 1.0R, uncertainty too high → HOLD
4. **Evaluation pipeline**: DSR + PBO + FQE together provide multi-angle validation

## How It Can Fail

| Failure Mode | Mitigation |
|-------------|-----------|
| FQE Q-function overfits | Regularization; early stopping on validation |
| CI too wide to be useful | More data; accept wider CI as honest uncertainty |
| Distribution shift too large | Cannot evaluate — must collect more behavioral data first |
| FQE estimates diverge from realized | Suspect OPE failure; do not deploy; investigate |

## Decision: USE LATER (V2+ evaluation gate)

FQE is mandatory for V2→V3 and V3→V4 transitions. Must be implemented as part of Phase 3 evaluation infrastructure before any critic influence is enabled.
