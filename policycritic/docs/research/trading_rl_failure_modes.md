# Trading RL Failure Modes — OOD, Regime Shift, Look-Ahead, Survivorship

## Abstract

RL applied to trading faces systematic failure modes beyond standard ML concerns. These include: (1) **OOD overestimation** — Q-values explode for actions outside the training distribution, (2) **regime shift** — a policy optimal in one market regime fails catastrophically in another, (3) **look-ahead bias** — future information leaks into training data, inflating backtest performance, (4) **survivorship bias** — training only on assets that survived, ignoring delisted/losing assets, (5) **backtest overfitting** — selecting the best of many tested configurations, (6) **execution gap** — ignoring real-world slippage, fees, and liquidity constraints. Each failure mode must be explicitly addressed in the Policy Critic design.

## Why It Matters for V7

These failure modes are not hypothetical — they are the primary reasons RL-based trading systems fail in live markets. The V7 Policy Critic architecture must prevent each one explicitly. Understanding these failures is essential for any engineer working on the critic.

## Failure Mode Details

### 1. OOD Overestimation

**Mechanism**: Q-learning's max operator evaluates ALL possible actions. For actions never taken in the training data, Q-values are extrapolated from insufficient evidence → grossly overestimated. The agent then selects these overestimated actions.

**Trading example**: Training data only contains cautious small-position trades. The critic learns Q(s, MASSIVE_LONG) = +5R (wildly overestimated). Live deployment selects MASSIVE_LONG → catastrophic loss.

**V7 prevention**: IQL never queries Q on OOD actions. CQL explicitly penalizes OOD Q-values. Both prevent this failure by construction.

### 2. Regime Shift

**Mechanism**: Training data from bull market (trending up). Policy learns "always go long." Deployed in ranging/bear market → consistent losses.

**Trading example**: BTC bull run 2020-2021 trained critic learns "LONG always works." Deployed in 2022 bear market → loses on every trade.

**V7 prevention**: Multi-regime training (≥3 regimes). Walk-forward validation across regimes. Per-regime performance monitoring. Auto-degrade on regime mismatch.

### 3. Look-Ahead Bias

**Mechanism**: Training uses information not available at decision time. E.g., using the day's close price to make an intraday decision, or using future volatility to size a position.

**Trading example**: Training feature includes "next_24h_volatility" — information not available at decision time. Model appears prescient in backtest, useless in live.

**V7 prevention**: Strict temporal splits. Purge+embargo in cross-validation. Point-in-time feature construction. Simulation engine uses only pre-decision candles.

### 4. Survivorship Bias

**Mechanism**: Training data only includes assets that are still actively traded. Assets that went to zero or were delisted are excluded → overestimates performance.

**Trading example**: Training on top-20 crypto by current market cap. Missing the 100+ tokens that went to zero in 2022. Model appears to have 60% win rate; true rate on full historical universe is 40%.

**V7 prevention**: Include delisted/inactive assets in training data. Test on full historical universe.

### 5. Backtest Overfitting

**Mechanism**: Testing 1000 hyperparameter combinations → select the best → report its performance as the model's capability. The reported performance is the maximum of 1000 noisy estimates, not the true capability.

**V7 prevention**: DSR (corrects for multiple testing). PBO via CSCV (estimates overfitting probability). Walk-forward ≥ 4/5 folds required.

### 6. Execution Gap

**Mechanism**: Backtest assumes zero-cost execution. Live trading incurs fees, slippage, spread, funding. The gap can be larger than the edge.

**V7 prevention**: Simulation engine includes fee_cost_r + slippage_cost_r in realized_r_net. Critic trained on NET return, never gross. Funding cost DEFERRED (spot-only valid until implemented).

## Decision: USE NOW (design requirements)

Each failure mode maps to a specific V7 prevention mechanism. The Policy Critic architecture must pass all six prevention checks before any live influence.
