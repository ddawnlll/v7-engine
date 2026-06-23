# Decision Transformer — Sequence Modeling for RL

## Abstract

Decision Transformer (DT, Chen et al. 2021, NeurIPS 2021) reframes offline RL as conditional sequence modeling: given a desired return, past states, and past actions, predict the next action. It uses a causally masked GPT-style transformer and avoids all traditional RL machinery (no bootstrapping, no value functions, no policy gradients). DT matches or exceeds specialized offline RL algorithms on D4RL benchmarks.

## Why It Matters for V7

DT represents an alternative paradigm — RL without Q-functions. Understanding DT is important for V7 because it clarifies what we're NOT doing and why. The approach is elegant but unsuitable for V7's current scale and infrastructure.

## What the Literature Says

### Architecture

```
Input: (..., R_{t-1}, s_{t-1}, a_{t-1}, R_t, s_t)
Output: a_t
```

- **Return-to-go (R_t)**: The desired cumulative future return, specified by the user at inference time
- **States (s_t)**: Raw observations
- **Actions (a_t)**: Past actions
- The transformer auto-regressively predicts the next action

### Key Innovation

DT eliminates bootstrapping entirely. Traditional RL methods bootstrap (use estimated values to improve estimates), which creates instability and OOD extrapolation risk. DT just does supervised sequence modeling — no bootstrapping, no divergence.

### Limitations

1. **Return conditioning is brittle**: You must specify the "desired return" at inference. If you specify too high, the model produces dangerous actions. If too low, it underperforms. There's no principled way to choose the right conditioning.
2. **Massive data requirements**: Transformers need millions of tokens. V7 will have ~10^4-10^6 transitions.
3. **No explicit risk modeling**: There's no value function, no uncertainty estimate, no risk-awareness beyond what's implicitly in the training data.
4. **All tested on D4RL**: No financial domain evidence.

## How It Applies to V7

**It doesn't — yet.** Decision Transformer is explicitly rejected for V7 because:
- V7's data scale (10^4-10^6 transitions) is far below transformer requirements (10^6+)
- Return conditioning is an open research problem — dangerous for financial applications
- No risk quantification (no confidence intervals, no distribution over returns)
- AlphaForge design commits to XGBoost, not transformers

## How It Can Fail (If Applied Prematurely)

| Failure Mode | Mechanism |
|-------------|----------|
| **Return mis-specification** | Setting desired return too high → dangerous over-trading |
| **Data insufficiency** | Transformer overfits on small financial dataset |
| **No risk awareness** | Cannot distinguish "confident good trade" from "lucky good trade" |
| **Regime shift** | Sequence patterns from trending market don't transfer to ranging |

## Decision: REJECT (for V1-V4)

Decision Transformer is not suitable for any planned V7 Policy Critic version. Revisit no earlier than V5+ if data scale, infrastructure, and return-conditioning research advance significantly.
