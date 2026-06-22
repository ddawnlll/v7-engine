# Safe RL and Shielding

## Abstract

Safe RL addresses the problem of ensuring reinforcement learning agents do not take dangerous actions during learning or deployment. **Shielding** (Alshiekh et al. 2018, AAAI) is a runtime enforcement method: a deterministic, formally verified component sits between the RL policy and the environment, capable of blocking, allowing, or modifying actions. Garcia & Fernandez (2015, JMLR) provide a comprehensive survey categorizing safe RL into: modification of optimality criterion, modification of exploration, and use of external knowledge.

## Why It Matters for V7

The safe RL literature **directly validates V7's architecture**. The V7 policy gates and operational hard gates ARE the shield. The Policy Critic (a potentially learned component) sits UNDER the shield. This is not an accident — it follows the shielding framework proven in Alshiekh et al. (2018). Every design decision about the critic being "advisory only" traces back to this literature.

## What the Literature Says

### Shielding Framework (Alshiekh et al. 2018)

A shield is a reactive system that:
1. **Observes** the action proposed by the RL agent
2. **Evaluates** the action against a safety specification (typically LTL — Linear Temporal Logic)
3. **Outputs** a safe action: the original action if safe, a corrected action if unsafe, or block if no safe action exists

Key properties:
- Shield is **external** to the RL agent — the agent is not trusted with safety
- Shield is **formally verified** — its safety properties are proven
- Shield **preserves optimality** — it only intervenes when necessary for safety
- Shield can be combined with any RL algorithm

### Safety Categories (Garcia & Fernandez 2015)

| Category | Approach | V7 Equivalent |
|----------|---------|---------------|
| Modification of optimality criterion | Add safety terms to reward; constrained MDPs | Decomposable reward (includes drawdown penalty) |
| Modification of exploration | Safe exploration; teacher advice; risk-directed | Offline RL only — no live exploration |
| External knowledge | Shielding; formal methods; teacher demonstrations | V7 policy gates + operational hard gates |

### Why Rewards Alone Are Insufficient

Garcia & Fernandez (2015) demonstrate that reward-based safety (adding penalties for unsafe actions) is unreliable because: (a) rewards must be carefully balanced against task rewards, (b) RL agents may find reward-maximizing loopholes, (c) safety constraints must be hard, not soft (a penalty can be "paid" to violate safety).

## How It Applies to V7

V7 implements a **two-layer shield**:

**Layer 1 — V7 Policy Gates**: confidence floor, expected-R minimum, regime consistency, degradation checks.

**Layer 2 — Operational Hard Gate**: exchange health, cooldown, exposure limits, kill switches.

The Policy Critic (future learned component) sits UNDER both layers. The critic advises; the shield decides.

## How It Can Fail

| Failure Mode | Mitigation |
|-------------|-----------|
| Shield specification incomplete | Add constraints as new failure modes are discovered |
| Shield too conservative → blocks all trades | Per-mode threshold tuning; shadow evaluation |
| Operator disables shield under pressure | Kill-switch requires multi-party approval |
| RL agent learns to game shield boundaries | Shield is external — agent cannot modify it |

## Decision: USE NOW (architecture validated)

The shielding framework directly validates V7's gate-above-critic architecture. This is the single most important research paper for the Policy Critic design. No critic can be deployed without deterministic shields above it.
