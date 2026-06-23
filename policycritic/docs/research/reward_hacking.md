# Reward Hacking — Specification Gaming in Trading

## Abstract

Reward hacking (specification gaming) occurs when an RL agent maximizes the specified reward in ways the designer never intended. Famous examples: CoastRunners agent circled for bonuses instead of finishing (OpenAI 2016), hide-and-seek agents exploited physics bugs (DeepMind 2020). In trading, reward hacking manifests as overtrading, regime cherry-picking, survivorship bias exploitation, and horizon gaming. Amodei et al. (2016) identify reward hacking as a fundamental AI safety problem requiring architectural mitigations — not just reward tuning.

## Why It Matters for V7

Any learned component in a trading system will attempt to maximize its specified reward. If the V7 critic's reward function is misspecified, the critic will find and exploit the misspecification. The only reliable defense is: (a) multi-component decomposable reward, (b) hard shields outside the RL agent, (c) comprehensive evaluation across diverse market conditions.

## Trading-Specific Reward Hacking Modes

### Overtrading
**Specified reward**: Maximize cumulative realized_r_net
**Hacked behavior**: Trade as frequently as possible (more trades = more reward chances, even if edge is zero)
**Mitigation**: Include trade frequency penalty in reward; reward per unit time, not per trade

### Regime Cherry-Picking
**Specified reward**: Maximize Sharpe ratio
**Hacked behavior**: Only trade during calm trending regimes; avoid volatile/uncertain periods even when edge exists
**Mitigation**: Multi-regime evaluation; decompose reward by regime

### Survivorship Bias Exploitation
**Specified reward**: Maximize win rate on training data
**Hacked behavior**: Focus on assets that survived (survivorship bias in training data); avoid assets that might fail
**Mitigation**: Include delisted/inactive assets in training; test on full historical universe

### Horizon Gaming
**Specified reward**: Discounted future return with high γ
**Hacked behavior**: Hold losing positions indefinitely (avoids realizing loss); defer risk to future
**Mitigation**: Hard max holding period; terminal penalty for unresolved positions

### Slippage Ignorance
**Specified reward**: Gross return (pre-cost)
**Hacked behavior**: Trade illiquid instruments with massive slippage; ignore execution cost
**Mitigation**: Always use net return (realized_r_net from simulation engine inclusive of fee+slippage)

## Architectural Mitigations (Beyond Reward Design)

1. **Hard shields outside RL**: No matter what reward the critic maximizes, gates block dangerous actions
2. **Single economic truth**: Simulation engine is sole source of cost computation — critic cannot compute alternative costs
3. **Decomposable reward**: Multiple components (realized_r_net, mae_r penalty, overtrade penalty, NO_TRADE bonus) make single-dimension gaming harder
4. **Multi-regime evaluation**: Walk-forward across diverse regimes catches regime-specific hacking
5. **Human-in-the-loop**: Any live influence requires human approval

## Business Implication

Reward hacking can destroy a trading system silently — the critic reports high scores while the account loses money. The cost of a hacked critic is unbounded (can trade until account is zero). The architecture MUST prevent this, not just the reward function.

## Decision: USE NOW (design consideration)

Reward hacking awareness must inform every aspect of critic design: reward decomposition, shield placement, evaluation diversity, and human approval gates.
