# RL Introduction for V7

> Purpose: Teach RL concepts relevant to the V7 Policy Critic. No prior RL knowledge assumed.
> Target audience: Trading engineers working on the V7 policy stack.
> Status: Docs/Design Only — No RL implementation exists in this repo.

---

## 1. Why RL Matters for Trading

Reinforcement learning (RL) is the only ML paradigm that directly models **sequential decision-making under uncertainty** — exactly what trading is. Unlike supervised learning (predict a label), RL learns to maximize cumulative reward over time by choosing actions and observing outcomes.

However, RL in live trading is **dangerous** without extensive safeguards. This document explains:
- What RL is
- Which RL approaches are plausible for V7
- Which are not
- What prerequisites are required before any RL implementation

**Key warning**: v7/src/ is greenfield (only `.gitkeep`). No RL implementation exists. The AlphaForge scorer (XGBoost-based) is planned but not implemented. The V6 inference engine (sibling repo) is the current live decision path.

---

## 2. RL Fundamentals

### 2.1 The Core Loop

```
┌──────────┐  action a_t   ┌──────────────┐
│  Agent   │ ─────────────▶│ Environment  │
│ (Policy) │               │  (Market)    │
└──────────┘ ◀─────────────└──────────────┘
              state s_{t+1}
              reward r_{t+1}
```

At each timestep:
1. Agent observes **state** `s_t` (market conditions, portfolio position, etc.)
2. Agent selects **action** `a_t` (LONG_NOW, SHORT_NOW, NO_TRADE)
3. Environment transitions to **next state** `s_{t+1}`
4. Agent receives **reward** `r_{t+1}` (realized PnL, costs, drawdown)

### 2.2 Core Concepts

| Concept | Notation | Trading Meaning | V7 Equivalent |
|---|---|---|---|
| **State** | `s_t` | Market snapshot + portfolio state | Canonical state from AlphaForge snapshot builder |
| **Action** | `a_t` | Trade decision | LONG_NOW / SHORT_NOW / NO_TRADE |
| **Reward** | `r_{t+1}` | Realized return net of costs | `realized_r_net` from `simulation/engine/engine.py` |
| **Policy** | `π(a\|s)` | Decision rule: probability of action given state | AlphaForge scorer + V7 policy gates |
| **Value function** | `V^π(s)` | Expected future return from state s following policy π | Not yet implemented |
| **Q-function** | `Q^π(s,a)` | Expected future return after taking action a in state s | Not yet implemented |
| **Episode** | — | From signal to outcome resolution | DecisionEvent → TradeOutcome lifecycle |
| **Return** | `G_t` | Sum of discounted future rewards | Cumulative `realized_r_net` |

### 2.3 Key Distinction: RL vs Supervised Learning

| Dimension | Supervised Learning | Reinforcement Learning |
|---|---|---|
| Feedback | Labeled correct answer | Scalar reward, possibly delayed |
| Goal | Predict label accurately | Maximize cumulative reward |
| Data | Static labeled dataset | Trajectories (s, a, r, s') |
| Exploration | Not applicable | Must balance explore/exploit |
| Bootstrapping | Not applicable | Value estimates depend on other estimates |
| Example | XGBoost predicts LONG/SHORT/NO_TRADE | Critic learns Q(s, LONG) = expected return |

Supervised learning answers "what is the correct label?" RL answers "what action leads to the best outcome?"

### 2.4 On-Policy vs Off-Policy

- **On-policy**: Learns from actions the current policy would take. Data must be from current policy. Inefficient with historical data.
- **Off-policy**: Learns from any behavioral data. Can use historical trading records. **This is what V7 needs.**

---

## 3. The State/Action/Reward/Policy/Value/Q Mental Model

### 3.1 In Trading Terms

```
State s_t:
  {
    symbol: "BTCUSDT"
    mode: "SWING"
    confidence: 0.72
    p_long: 0.65, p_short: 0.12, p_no_trade: 0.23
    expected_R_long: 1.2, expected_R_short: -0.3
    regime: "trending_up"
    anomaly_score: 0.1
  }

Action a_t:
  LONG_NOW  (proposed by AlphaForge scorer)

Reward r_{t+1}:
  {
    realized_r_net: +1.8      ← net return in R-multiples (from simulation engine)
    mae_r: -0.6               ← maximum adverse excursion
    fee_cost_r: 0.05
    slippage_cost_r: 0.02
    saved_loss_r: 0.0         ← for NO_TRADE evaluation
  }

Next state s_{t+1}:
  State at next scheduled analysis for BTCUSDT SWING
```

### 3.2 Value Function V(s)

V(s) answers: "Starting from this market state, what's my expected total return?"

- V(s) > 0: Favorable conditions ahead
- V(s) ≈ 0: Neutral, no edge
- V(s) < 0: Unfavorable, avoid trading

### 3.3 Q-Function Q(s,a)

Q(s,a) answers: "If I go LONG right now, what's my expected total return?"

- Q(s, LONG_NOW) > Q(s, NO_TRADE): Go long
- Q(s, SHORT_NOW) > Q(s, NO_TRADE): Go short
- Q(s, NO_TRADE) > max(Q(s, LONG_NOW), Q(s, SHORT_NOW)): Stay out

The **advantage** A(s,a) = Q(s,a) - V(s) tells you: "How much better is this action than average?"

### 3.4 Policy π(a|s)

The policy is the decision rule. In V7, the planned policy stack is:

1. **AlphaForge Scorer** proposes action (supervised XGBoost policy)
2. **V7 Policy Gates** filter/gate (deterministic policy)
3. **Policy Critic** (future) adjusts confidence (learned advisory policy)

---

## 4. Offline RL (Batch RL)

### 4.1 The Problem

Online RL (trial-and-error in the real market) is **financially suicidal**:
- Suboptimal actions cost real money
- Market regimes shift (non-stationary environment)
- Episodes are slow (hours between decision and outcome)

**Offline RL** solves this: learn entirely from historical data without any market interaction.

### 4.2 The Central Challenge: Distribution Shift

The fundamental problem of offline RL (Levine et al. 2020):

1. You have data from a **behavioral policy** (e.g., historical trading decisions)
2. You want to learn a **better policy** (e.g., more selective entries)
3. But your learned policy might consider actions **not in the dataset**
4. The Q-function **overestimates** these unseen actions (extrapolation error)
5. Your policy then selects overestimated actions → terrible real performance

**Analogy**: You have data from a cautious driver. You want to learn to be a race car driver. The cautious data says nothing about racing speeds. If you extrapolate, you crash.

### 4.3 Why Trading Needs Offline RL

- Historical candle data is the only "environment"
- Online exploration = real financial losses
- But offline RL's distribution shift problem IS the trading failure mode (overtrading, regime overfitting)

---

## 5. IQL — Implicit Q-Learning

**Source**: Kostrikov, Nair, Levine 2021 (ICLR 2022)
**Status**: Recommended first offline RL algorithm for V3 (after prerequisites)

### 5.1 Core Idea

IQL avoids ever querying Q-values for unseen (out-of-distribution) actions. It works in three steps:

1. **Learn V(s)** via expectile regression — only evaluates on actions in the dataset
2. **Learn Q(s,a)** only on in-sample actions — never extrapolates to unseen actions
3. **Extract policy** via advantage-weighted regression — stays close to dataset actions

### 5.2 What "In-Sample" Means

"In-sample" = only looking at actions that were actually taken in the historical data.

- Traditional Q-learning: `max_a Q(s,a)` — evaluates ALL possible actions, including ones never taken
- IQL: `V(s) ≈ E[Q(s,a)]` over dataset actions only — never looks at unseen actions

This is naturally aligned with trading: you only learn from your actual trading history.

### 5.3 Why IQL Is Plausible for V3

| Property | Why Good for Trading |
|---|---|
| No OOD queries | Prevents overestimation of risky actions |
| Simple (3 losses, few hyperparameters) | Easier to validate and debug |
| Expectile regression | Controllable conservatism via τ parameter |
| Advantage-weighted regression | Extracted policy stays close to data |
| State-of-the-art on D4RL | Validated on standard benchmarks |

### 5.4 Limitations (Honest)

- Tested on D4RL (game/simulator tasks), not financial data
- Requires structured (s,a,r,s') tuples → needs replay buffer
- Expectile τ is task-dependent (financial optimal τ is unknown)
- Assumes data covers "good enough" actions → may not hold for poor historical data

---

## 6. CQL — Conservative Q-Learning

**Source**: Kumar et al. 2020 (NeurIPS 2020)
**Status**: Alternative/complement to IQL for V3+

### 6.1 Core Idea

CQL takes a different approach: it explicitly penalizes Q-values on out-of-distribution actions.

```
CQL loss = standard Q-loss + α · [E[Q(s, OOD_action)] - E[Q(s, dataset_action)]]
```

This pushes down Q-values for unfamiliar actions and pushes up Q-values for familiar ones. Produces a **lower bound** on the true policy value — systematically pessimistic.

### 6.2 IQL vs CQL Comparison

| Dimension | IQL | CQL |
|---|---|---|
| Approach | Avoid OOD queries | Penalize OOD queries |
| Conservatism control | Expectile τ | Penalty weight α |
| Simplicity | Simpler | More hyperparameters |
| Theoretical guarantees | Weaker | Stronger (lower bound) |
| Stability | More stable | α-sensitive |
| Recommendation | First choice for V3 | Ensemble member for cross-check |

### 6.3 IQL/CQL Ensemble for V3

When IQL and CQL disagree: emit `REQUIRE_REVIEW` verdict. This dual-approach provides:
- IQL as primary (structurally prevents OOD overestimation)
- CQL as cross-check (enforces conservative lower bound)
- Disagreement as a reliability signal (regime shift, OOD state)

---

## 7. Decision Transformer

**Source**: Chen et al. 2021 (NeurIPS 2021)
**Status**: NOT recommended for V7 — too early

### 7.1 Core Idea

Treats RL as conditional sequence modeling:
- Input: (desired_return, state, action) tokens
- Output: Next action
- Trained like GPT on historical trajectories

### 7.2 Why Too Early for V7

- Requires transformer architecture (not in V7 stack)
- Requires massive trajectory data (millions of timesteps)
- "Return-to-go" conditioning is an open research problem
- No evidence of success on financial data
- Requires infrastructure V7 does not have (event bus, experience buffer)

---

## 8. Distributional RL / Quantile Q-Learning

**Source**: Dabney et al. 2017 (AAAI 2018), Dabney et al. 2018 (ICML 2018)
**Status**: Future V3+ feature

### 8.1 Core Idea

Instead of learning just the **mean** expected return E[G], learn the **full distribution** Z(s,a).

```
Standard Q:   Q(s, LONG) = +1.5R  ("Expected +1.5R")
Quantile Q:   Q(s, LONG) = {5%: -2.0R, 50%: +0.5R, 95%: +3.0R}
```

The risk manager cares about the 5th percentile more than the mean.

### 8.2 Why This Matters for a Future Critic

- QR-DQN: Learns N quantiles of the return distribution
- IQN: Learns the full continuous quantile function
- A distributional critic could output: "Expected +0.5R but 5th percentile is -2.0R — BLOCK"
- Enables **risk-aware gating** without explicit risk rules
- The V7 canonical design (`v7/docs/policy_critic/design.md`) specifies a **distributional IQL** with 16-32 quantile Q-heads

### 8.3 Why Not Now

- Requires distributional RL infrastructure
- Requires large replay buffer with diverse outcomes
- Adds significant complexity
- V3+ feature, not V1-V2

---

## 9. OPE / FQE — Off-Policy Evaluation

**Source**: Fu et al. 2021 (ICLR 2021)
**Status**: MANDATORY before any live critic deployment

### 9.1 Core Idea

OPE answers: "How good is this new policy using only data from the old policy?"

Fitted Q-Evaluation (FQE) is the most practical method:
1. Learn Q^π_new from behavioral data
2. Estimate V^π_new by averaging Q^π_new over initial states
3. Compare to known behavioral policy performance

### 9.2 Why Mandatory

Without OPE:
- Cannot distinguish skill from luck
- Cannot detect backtest overfitting
- Cannot estimate real-world performance
- Cannot calibrate critic recommendations

**Analogy**: You wouldn't fly a new airplane design with passengers without wind-tunnel testing. OPE is the wind tunnel for RL policies.

---

## 10. Safe RL / Shielding

**Source**: Alshiekh et al. 2018 (AAAI 2018), Garcia & Fernandez 2015 (JMLR)
**Status**: Validates the V7 architecture

### 10.1 Core Idea

A **shield** is a deterministic, verified safety component that sits between the RL policy and the environment. It can:
- **Allow** the action (safe)
- **Block** the action (unsafe)
- **Modify** the action (correct to safe alternative)

### 10.2 V7 Already Has This (in Design)

The V7 policy gates and operational hard gates **ARE** the shield:

```
AlphaForge Scorer (future) → V7 Policy Gates (shield) → Market
Policy Critic (future) → V7 Policy Gates (shield) → Market
```

The shield:
- Enforces confidence floor
- Enforces expected-R floor
- Enforces regime consistency
- Applies portfolio + risk limits
- Applies operational hard gates (exchange health, cooldown, exposure, kill switches)

### 10.3 Why This Is Architecturally Correct

Safe RL literature (Alshiekh et al. 2018) proves:
- Safety constraints should be external to the RL agent
- Shields should be formally verified
- RL agents should not be trusted with safety
- Shielding preserves optimality while ensuring safety

V7's architecture (deterministic gates above learned critic) follows this principle exactly.

---

## 11. Reward Hacking

**Source**: OpenAI 2016, DeepMind 2020, Amodei et al. 2016
**Status**: Active design consideration for any V7 reward function

### 11.1 What Is Reward Hacking?

RL agents are **extremely good** at maximizing the specified reward — in ways their designers never intended.

| Domain | Specified Reward | Hacked Behavior |
|---|---|---|
| CoastRunners | Finish race, score points | Circle indefinitely collecting bonuses |
| Hide-and-seek | Hide from seekers | Exploit physics bugs to launch into space |
| Trading | Maximize realized_r | Overtrade (more trades = more reward chances) |
| Trading | Maximize Sharpe | Cherry-pick calm-regime trades, avoid real risk |
| Trading | Maximize win rate | Hold losers hoping they recover |

### 11.2 Trading-Specific Failure Modes

| Failure Mode | Cause | Mitigation |
|---|---|---|
| **Overtrading** | More trades = more reward events | Include all costs in reward; reward rate per unit time |
| **Regime overfitting** | Training data from trending market only | Train on multi-regime data; walk-forward validation |
| **Survivorship bias** | Only surviving coins in dataset | Include delisted/losing assets |
| **Look-ahead leakage** | Future data leaks into state | Strict temporal train/val/test splits |
| **Slippage ignorance** | Agent assumes zero-cost execution | Include slippage in reward function |
| **Gambler's ruin** | Agent doubles down on losses | Hard position limits; max drawdown gate |
| **Horizon mismatch** | Agent optimizes for short-term | Discount factor calibrated to holding period |

### 11.3 Mitigation Principles for V7

1. **Include ALL costs in reward**: fees, slippage (funding DEFERRED for spot-only)
2. **Keep hard risk limits outside RL**: shield ensures no bypass
3. **Multi-regime evaluation**: test across trending, ranging, volatile, low-volatility
4. **Conservative discount factor**: avoid myopic behavior
5. **Walk-forward validation**: detect regime-specific overfitting
6. **Use simulation engine as single economic truth**: `realized_r_net` from `simulation/engine/engine.py`

---

## 12. Why These Concepts Matter for Trading

### 12.1 The Core Problem

Trading is an **adversarial, non-stationary, partially observable environment with delayed, noisy rewards and fat-tailed outcomes**. This is about the hardest possible RL setting.

### 12.2 Why V7 Must Not Implement Production RL Now

| Reason | Evidence |
|---|---|
| No replay buffer | No (s,a,r,s',terminal) tuples exist |
| No reward shaper | No unified reward computation pipeline |
| No OPE protocol | Cannot evaluate any RL policy |
| No event bus | All execution is synchronous; no trajectory streaming |
| v7/src/ greenfield | No V7-native decision infrastructure |
| AlphaForge not implemented | P5/P6/P9 phases not started |
| Trees beat deep RL on tabular data | Grinsztajn et al. 2022 |

### 12.3 The Correct Path

1. Build infrastructure (replay buffer, reward tuple emitter from simulation engine)
2. Build evaluation (OPE, DSR, PBO, walk-forward)
3. Build simple critics (rule-based → supervised → IQL)
4. Build evidence (shadow burn-in, staged validation)
5. THEN consider live influence — with human approval

---

## 13. Further Reading

### Primary Sources

- Sutton & Barto 2018, "Reinforcement Learning: An Introduction" — [incompleteideas.net](http://incompleteideas.net/book/the-book-2nd.html)
- Levine et al. 2020, "Offline Reinforcement Learning: Tutorial, Review, and Perspectives" — [arXiv:2005.01643](https://arxiv.org/abs/2005.01643)
- Kostrikov et al. 2021, "Offline RL with Implicit Q-Learning" — [arXiv:2110.06169](https://arxiv.org/abs/2110.06169)
- Kumar et al. 2020, "Conservative Q-Learning for Offline RL" — [arXiv:2006.04779](https://arxiv.org/abs/2006.04779)

### Related V7 Docs

- [[policy_critic_design.md]] — Architecture and authority hierarchy
- [[pipeline.md]] — Staged implementation plan
- [[authority_and_boundaries.md]] — Detailed boundary specification
- [[source_inventory.md]] — Full bibliography with trust ratings
- `v7/docs/policy_critic/design.md` — Canonical design recommendation
- `v7/docs/policy_critic/codebase_maps/simulation_map.md` — Simulation reward surface
