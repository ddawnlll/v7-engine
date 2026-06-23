# Implicit Q-Learning (IQL) — Deep Dive

## Abstract

IQL (Kostrikov, Nair, Levine 2021, ICLR 2022) is an offline RL algorithm that **structurally avoids querying Q-values on out-of-distribution actions**. It works in three stages: (1) learn V(s) via expectile regression over in-sample actions, (2) learn Q(s,a) only on dataset actions, (3) extract policy via advantage-weighted regression (AWR). IQL achieves state-of-the-art on D4RL benchmarks with a simple, stable architecture (SARSA-like TD update + AWR).

## Why It Matters for V7

IQL is the **recommended primary offline RL algorithm for V3 Policy Critic**. Its key property — never evaluating Q on unseen actions — eliminates the dominant offline RL failure mode (OOD overestimation) by construction. For trading, where historical data is naturally limited to a cautious behavioral policy, this is essential.

## What the Literature Says

### Three-Stage Architecture

**Stage 1: Learn V(s) via expectile regression**
```
L_V(ψ) = E_{(s,a)~D} [L_2^τ(Q_θ(s,a) - V_ψ(s))]
```
Where L_2^τ is the expectile loss: L_2^τ(u) = |τ - 1(u<0)| · u². Expectile τ controls conservatism: τ > 0.5 pushes V(s) above the mean (optimistic), τ < 0.5 pushes below (pessimistic). For trading, τ ≈ 0.7-0.8 recommended (slightly optimistic — the critic should find value when it exists).

**Stage 2: Learn Q(s,a) on in-sample actions**
```
L_Q(θ) = E_{(s,a,r,s')~D} [(r + γ V_ψ(s') - Q_θ(s,a))²]
```
Standard SARSA-style TD update. Q is only evaluated on actions actually taken in the dataset.

**Stage 3: Extract policy via AWR**
```
L_π(φ) = E_{(s,a)~D} [exp(β · (Q_θ(s,a) - V_ψ(s))) · log π_φ(a|s)]
```
Advantage-weighted regression: actions with high advantage get higher weight. The exponential weight keeps the extracted policy close to the data distribution.

### Key Hyperparameter: Expectile τ

| τ | Behavior | Trading Context |
|---|---------|----------------|
| 0.5 | Standard mean regression | Neutral — learns expected value |
| 0.7 | Slightly optimistic | Learns what good outcomes look like |
| 0.9 | Very optimistic | Near-max — dangerous for trading |
| 0.3 | Slightly pessimistic | Conservative lower bound |

### D4RL Results

IQL matches or exceeds CQL on most D4RL tasks (Ant Maze, Kitchen, Adroit) with simpler implementation and fewer hyperparameters.

### Distributional IQL Extension

The canonical V7 design specifies a **distributional IQL** variant: each Q-head outputs 16-32 quantiles of the return distribution instead of a single mean. This enables risk-aware gating from calibrated lower quantiles (e.g., 20th percentile).

## How It Applies to V7

1. **V(s)**: "What is the expected return from this market state?" Used as baseline value.
2. **Q(s, LONG_NOW)**: "If I go long now, what's the expected return?" Learned only from historical long trades.
3. **Q(s, SHORT_NOW)**: Same for short.
4. **Q(s, NO_TRADE)**: "What's the expected return of staying out?" Includes saved_loss_r and missed_opportunity_r.
5. **Advantage A(s,a)**: Drives confidence adjustment. If A(s, LONG_NOW) < 0, recommend NO_TRADE.
6. **Distributional lower-quantile**: The 20th percentile of Q(s,a) is the calibrated risk estimate. If the 20th percentile is negative, VETO_TO_NO_TRADE even if the mean is positive.

## How It Can Fail

| Failure Mode | Cause | Mitigation |
|-------------|-------|-----------|
| **Expectile τ misspecified** | τ too high → overestimation; too low → always NO_TRADE | Sensitivity analysis; empirical calibration |
| **Financial non-applicability** | IQL tested on MuJoCo, not trading | Shadow burn-in; OPE validation |
| **Insufficient NO_TRADE data** | Historical data has few NO_TRADE decisions | Synthesize NO_TRADE tuples from simulation |
| **Distributional instability** | Quantile regression may not converge on financial noise | Fewer quantiles (16, not 32); Huber loss |
| **Conformal coverage violation** | Time-series violates exchangeability | Weighted/time-aware CP; accept approximate coverage |

## Business Implication

IQL enables a learned critic that can estimate expected value for any proposed trade without ever exploring dangerous actions in live markets. The training cost is fixed (compute + replay buffer infrastructure). The potential value is in avoiding negative-expectancy trades that deterministic gates miss.

## Implementation Implication

- XGBoost expectile regression: implement custom objective for expectile loss in XGBoost
- Three separate models (one per action) or one multi-output model
- Quantile regression for distributional variant: XGBoost supports `objective='reg:quantileerror'`
- Conformal calibration as post-training retrofit
- CQL cross-check as separate model trained with conservative penalty

## Citations

- Kostrikov, I., Nair, A., & Levine, S. (2021). "Offline Reinforcement Learning with Implicit Q-Learning". ICLR 2022. arXiv:2110.06169.
- Kostrikov, I. (2021). Official IQL implementation. https://github.com/ikostrikov/implicit_q_learning
- Peng, X.B., Kumar, A., Zhang, G., & Levine, S. (2019). "Advantage-Weighted Regression". arXiv:1910.00177.

## Decision: USE LATER (V3 primary algorithm)

IQL is the recommended primary algorithm for V3 Policy Critic (distributional variant with conformal calibration). Prerequisites: replay buffer ≥ 10,000 tuples, FQE validated, V2 critic operating in shadow. Not suitable for V1-V2 (too complex; use heuristic then supervised).
