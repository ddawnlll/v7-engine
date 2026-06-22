# Offline RL — Learning Without Interaction

## Abstract

Offline RL (batch RL) learns policies entirely from previously collected static datasets, without any environment interaction. This is critically different from online RL, where the agent explores and receives feedback in real-time. The central challenge is **distribution shift**: the learned policy may select actions not present in the training data, causing the Q-function to extrapolate erroneously and produce dangerously overestimated values for unseen actions.

## Why It Matters for V7

V7 **cannot** do online RL. Trial-and-error in live markets costs real money. Offline RL is the only viable path: learn from historical trading data (candles, past decisions, simulation outcomes) without ever placing a live exploratory trade. But offline RL's distribution shift problem is exactly the trading failure mode — overtrading, regime overfitting, and overestimating the value of risky actions never taken in the historical record.

## What the Literature Says

### The Distribution Shift Problem (Levine et al. 2020)

1. Data comes from a **behavioral policy** π_β (historical trader / previous model version)
2. We want to learn a **better policy** π_new
3. π_new may consider actions a' where π_β(a'|s) ≈ 0
4. Q(s, a') is extrapolated from insufficient data → **overestimation**
5. π_new selects overestimated actions → **catastrophic real-world performance**

### Algorithm Taxonomy

| Family | Examples | Mechanism |
|--------|---------|-----------|
| **Policy constraints** | BCQ, BEAR | Constrain π_new to stay close to π_β support |
| **Conservative value** | CQL | Penalize Q-values on OOD actions |
| **In-sample only** | IQL | Never query Q on OOD actions |
| **Model-based** | MOPO, COMBO | Learn dynamics model; penalize uncertain regions |
| **Sequence modeling** | Decision Transformer | Cast as conditional generation; avoid bootstrapping |

### Why Standard Off-Policy Methods Fail Offline

Standard algorithms (DQN, DDPG, SAC) all use some form of max or greedy operator over Q-values. In offline settings, this operator queries actions for which Q is poorly estimated, producing **extrapolation error** that compounds through bootstrapping.

## How It Applies to V7

1. **V7 has only historical data**: candles, past DecisionEvents, past TradeOutcomes, simulation outputs. All learning must be offline.
2. **IQL is recommended because** it structurally never queries Q on out-of-distribution actions — the dominant offline RL failure mode cannot arise by construction.
3. **Replay buffer is mandatory**: the offline dataset must contain (state, action, realized_r_net, mae_r, next_state, terminal) tuples. No offline RL without tuples.
4. **OPE/FQE is mandatory**: without online validation, we need off-policy evaluation to estimate real-world performance before any live influence.

## How It Can Fail

| Failure Mode | Mechanism | V7 Mitigation |
|-------------|----------|---------------|
| **Extrapolation error** | Q-values explode for OOD actions | IQL (never queries OOD) + CQL cross-check |
| **Dataset bias** | Behavioral policy was bad → learned policy stays bad | Include NO_TRADE as first-class action |
| **Insufficient coverage** | Some state-action pairs never seen | Conservative estimation; confidence intervals |
| **Temporal non-stationarity** | Historical data from different regime | Multi-regime training; walk-forward validation |

## Business Implication

Offline RL is the only cost-realistic path to a learned critic. Online RL would require thousands of losing trades to converge — financially non-viable. The infrastructure cost (replay buffer, training compute, OPE validation) is fixed and modest compared to the potential improvement in trade selection.

## Implementation Implication

- Requires replay buffer emitter (Phase 2) before any training
- IQL's in-sample-only approach maps naturally to XGBoost expectile regression
- Training is batch/offline — no online updates during live trading
- OPE validation gates all transitions (DSR, PBO, FQE)

## Citations

- Levine, S., Kumar, A., Tucker, G., & Fu, J. (2020). "Offline Reinforcement Learning: Tutorial, Review, and Perspectives on Open Problems". arXiv:2005.01643.
- Fujimoto, S., Meger, D., & Precup, D. (2019). "Off-Policy Deep Reinforcement Learning without Exploration". ICML.
- Lange, S., Gabel, T., & Riedmiller, M. (2012). "Batch Reinforcement Learning". In *Reinforcement Learning* (pp. 45-73). Springer.

## Decision: USE NOW (foundational for V3+)

Offline RL is the only viable RL paradigm for trading. IQL is the recommended first algorithm. V1-V2 use simpler methods (heuristic, supervised); V3 transitions to offline IQL.
