# RL Basics — Reinforcement Learning Foundations

## Abstract

Reinforcement Learning (RL) is a machine learning paradigm where an agent learns to make sequential decisions by interacting with an environment. The agent observes states, selects actions, and receives scalar rewards. The goal is to learn a policy that maximizes cumulative discounted reward over time. Key concepts include Markov Decision Processes (MDPs), value functions, Q-functions, Bellman equations, and the distinction between model-free and model-based methods.

## Why It Matters for V7

Trading is fundamentally a sequential decision-making problem under uncertainty — exactly what RL is designed for. The V7 Policy Critic needs to understand:
- **State**: market conditions + portfolio context
- **Action**: LONG_NOW, SHORT_NOW, NO_TRADE
- **Reward**: realized net return after costs
- **Value**: "how good is this state?" and "how good is this action in this state?"

Without understanding these fundamentals, the critic cannot learn which proposed trades are likely to be profitable.

## What the Literature Says

### MDP Formalism (Sutton & Barto 2018)

An MDP is defined by (S, A, P, R, γ):
- **S**: state space (market states)
- **A**: action space (LONG_NOW, SHORT_NOW, NO_TRADE)
- **P(s'|s,a)**: transition probability (market dynamics)
- **R(s,a)**: reward function (realized PnL net of costs)
- **γ**: discount factor (0.95-0.99 for trading)

### Value Functions

**State-value function V^π(s)**: Expected cumulative discounted reward starting from state s and following policy π.

**Action-value function Q^π(s,a)**: Expected cumulative discounted reward starting from state s, taking action a, then following policy π.

**Bellman equations** express recursive relationships:
- V^π(s) = Σ_a π(a|s) [R(s,a) + γ Σ_{s'} P(s'|s,a) V^π(s')]
- Q^π(s,a) = R(s,a) + γ Σ_{s'} P(s'|s,a) Σ_{a'} π(a'|s') Q^π(s',a')

### Model-Free Methods

**Q-Learning** (off-policy TD control):
Q(s,a) ← Q(s,a) + α[r + γ max_{a'} Q(s',a') - Q(s,a)]

**SARSA** (on-policy TD control):
Q(s,a) ← Q(s,a) + α[r + γ Q(s',a') - Q(s,a)]

**Policy Gradient**: Directly optimize policy parameters θ to maximize expected return:
∇J(θ) = E[∇_θ log π_θ(a|s) · Q^π(s,a)]

### Model-Free vs Model-Based

| Approach | How It Works | Trading Relevance |
|----------|-------------|------------------|
| Model-free | Learn value/policy directly from experience | Most applicable — we don't have a market model |
| Model-based | Learn environment dynamics, then plan | Simulation engine is a partial model |

## How It Applies to V7

1. **Q-function for risk scoring**: Q(s, LONG_NOW) tells the critic the expected return of going long. If Q(s, LONG_NOW) < Q(s, NO_TRADE), the critic recommends NO_TRADE.

2. **Advantage function**: A(s,a) = Q(s,a) - V(s) measures how much better action a is than the average action in state s.

3. **Off-policy learning**: V7 must learn from historical data (offline), not from live exploration. This requires off-policy methods.

4. **Discount factor calibration**: γ determines how much the critic values future returns vs immediate returns. For SWING mode (hours-days holding), γ ≈ 0.99; for SCALP (minutes), γ ≈ 0.95.

## How It Can Fail

| Failure Mode | Cause | V7 Mitigation |
|-------------|-------|---------------|
| **Overestimation bias** | max operator in Q-learning overestimates unseen actions | IQL avoids max; CQL penalizes unseen actions |
| **Deadly triad** | Function approximation + bootstrapping + off-policy = divergence risk | Conservative algorithms, bounded updates |
| **Sample inefficiency** | Model-free RL needs millions of samples | Offline RL with tree-based function approximation |
| **Catastrophic forgetting** | Neural network forgets old regimes when trained on new | XGBoost (not neural network); periodic full retraining |
| **Reward sparsity** | Trading rewards are noisy and delayed | Dense reward shaping from simulation engine (mae_r, path_quality_score) |

## Business Implication

RL fundamentals provide the mathematical framework for expected value estimation. Without these concepts, the critic is just heuristics. With them, the critic produces calibrated, uncertainty-aware value estimates that can justify confidence adjustments and veto recommendations to human operators and regulators.

## Implementation Implication

- Q-function requires (state, action, reward, next_state) tuples → replay buffer
- Value function requires in-sample evaluation → IQL expectile regression
- Policy extraction requires staying within data support → advantage-weighted regression
- XGBoost (not neural networks) for sample efficiency on tabular data

## Citations

- Sutton, R.S. & Barto, A.G. (2018). *Reinforcement Learning: An Introduction*. 2nd ed. MIT Press. http://incompleteideas.net/book/the-book-2nd.html
- Watkins, C.J.C.H. & Dayan, P. (1992). "Q-Learning". *Machine Learning*, 8(3-4), 279-292.
- Sutton, R.S., McAllester, D., Singh, S., & Mansour, Y. (1999). "Policy Gradient Methods for Reinforcement Learning with Function Approximation". *NeurIPS*.

## Decision: USE NOW (foundational)

RL basics are the mathematical foundation for the entire Policy Critic design. Every subsequent research topic builds on these concepts. No implementation can proceed without understanding MDPs, value functions, and the Bellman equations.
