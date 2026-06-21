# Research: Reward Design for Cost-Aware Trading RL

## Summary
For a small-data, high-cost, high-volatility regime (the V7 SWING/SCALP setting), use a DECOMPOSABLE, WEIGHTED reward with NO_TRADE explicitly wired as the zero-cost baseline, NOT a single metric. Concrete design:

(1) BASE SIGNAL = post-cost PnL: r_profit = delta_equity - (fee + slippage + funding). This makes NO_TRADE intrinsically worth 0 cost and only the unrealized P&L of an open position — so doing nothing is never penalized by cost. This alone makes NO_TRADE first-class.

(2) CORRECT-NO_TRADE BONUS (asymmetric, small): when the agent chooses NO_TRADE AND no edge signal is present (e.g., |predicted edge| < cost_threshold), give a small +epsilon bonus. This is the key lever against "never trade" collapse — it must be SMALL and CONDITIONAL on low-edge, not unconditional, so it does not reward cowardice in high-edge states.

(3) MISSED-OPPORTUNITY PENALY (the counter-lever): when a strong edge WAS present and the agent chose NO_TRADE, apply a small penalty proportional to (edge - cost). This is the symmetric force that prevents collapse into "never trade": NO_TRADE is rewarded only when edge < cost, and punished when edge > cost. The (edge - cost) form means the agent is indifferent exactly at the break-even edge, which is the economically correct threshold.

(4) OVERTRADING PENALTY = bounded, regime-scaled: penalize local trade frequency above a threshold, but SCALE the threshold by realized volatility / cost regime. In high-cost/high-vol regimes the threshold drops (fewer trades allowed); in calm regimes it rises. This makes overtrading punishment regime-aware rather than a fixed cap that suppresses legitimate alpha.

(5) DRAWDOWN PENALTY = incremental and regime-aware (DSR + drawdown term), NOT max-drawdown-only. Use incremental drawdown increase with a stronger coefficient beyond a severe threshold. CVaR is optional but risky in small data (tail samples too few) — prefer Sortino-style downside deviation which is denser.

(6) Use DSR (Differential Sharpe) as the risk-adjusted SCAFFOLD rather than end-of-episode Sharpe, because small data means short episodes and noisy Sharpe — DSR gives a dense, online signal.

CRITICAL CALIBRATION AGAINST COLLAPSE: The two failure modes are symmetric — "never trade" (cost penalty too high / NO_TRADE bonus too large) and "churn everything" (cost penalty too low / missed-opportunity penalty too high). The sensitivity analysis from the crypto-trading reward study confirms this directly: "higher [cost penalty] values excessively discourage trading (leading to perpetual holding), while lower values fail to internalize realistic cost structures." Therefore:
- Lock the (edge - cost) indifference point as the ANCHOR, not the penalty magnitudes. The break-even edge is the empirically-grounded quantity; penalty weights are tuned around it.
- Keep NO_TRADE bonus and missed-opportunity penalty of COMPARABLE magnitude so neither dominates; both should be smaller than the post-cost PnL term so economics drives the policy and the bonuses only break ties at the margin.
- Gate the bonus/penalty pair on a measured edge signal (AlphaForge confidence / simulation expected value), so the reward is "do nothing when no edge, act when edge exceeds cost" — which is exactly the V7 policy-acceptance contract.
- Do NOT lock numeric weights without empirical evidence (per project lock semantics); treat the (edge - cost) indifference point as LOCKED_INITIAL_BASELINE and recalibrate weights after first evidence.

This design makes NO_TRADE first-class (zero cost + conditional bonus), punishes overtrading (regime-scaled frequency penalty + cost subtraction), and avoids "never trade" collapse (missed-opportunity penalty on high-edge NO_TRADE + PnL term dominating the bonuses).

## Key Methods
### Post-cost PnL reward (transaction-cost-subtracted)
Step reward = realized equity change minus explicit fees, slippage, and funding charged on every state-changing action; NO_TRADE pays/pays-no-cost and only earns unrealized P&L.
- **Best for:** Baseline cost-awareness; makes the agent internalize that trading is not free and that NO_TRADE avoids the cost term.
- **Weakness:** Pure cost subtraction is a sparse, weak signal — agents either overtrade when signal is strong or collapse to never-trade when costs dominate; does not by itself encode risk or opportunity cost.
- **Source:** https://www.mdpi.com/2571-905x/5/2/546

### Nonlinear / market-impact transaction cost model (CDQN-rp near-quadratic)
Replace flat fees with a near-quadratic cost function combining spread, market impact, and fixed costs so large/illiquid trades are penalized super-linearly.
- **Best for:** High-volatility / illiquid regimes where size-dependent slippage dominates; discourages oversized orders and churning.
- **Weakness:** Requires accurate impact model; mis-specified curvature either over- or under-penalizes size; adds reward complexity that itself increases hacking risk (~9% per the empirical study).
- **Source:** https://www.mdpi.com/2571-905x/5/2/546

### Differential Sharpe Ratio (DSR) reward
Online incremental update to the Sharpe ratio via EMA of return mean and variance, giving a dense per-step risk-adjusted reward without waiting for episode end.
- **Best for:** Small-data / short-horizon trading where end-of-episode Sharpe is too noisy; produces a smooth gradient signal that penalizes volatility.
- **Weakness:** Still a single risk-adjusted metric; can be gamed by volatility suppression; EMA horizon is a sensitive hyperparameter and second-moment estimates are unstable in regime shifts.
- **Source:** http://papers.neurips.cc/paper/1551-reinforcement-learning-for-trading.pdf

### Composite multi-objective reward (return + downside + differential return + Treynor)
Weighted sum of annualized return, Sortino-style downside deviation penalty, benchmark outperformance (alpha), and Treynor ratio so no single metric dominates.
- **Best for:** Reducing reward hacking from single-metric over-optimization; encoding investor risk preferences via modular weights.
- **Weakness:** Weight tuning is non-trivial; component interactions are non-monotone (adding penalties does not consistently help); more terms increase the attack surface for specification gaming.
- **Source:** https://arxiv.org/html/2506.04358v1

### Incremental / regime-aware drawdown penalty
Penalty proportional to incremental increase in drawdown, with a stronger coefficient beyond a severe-drawdown threshold, added on top of a DSR base.
- **Best for:** Capital preservation and tail-loss avoidance without banning trading outright; regime-awareness lets the agent take risk in calm periods.
- **Weakness:** Threshold and coefficient must be empirically calibrated (cannot be locked without evidence); too-aggressive a penalty creates a 'never hold a losing position' bias that itself churns.
- **Source:** https://arxiv.org/html/2603.29086v2

### CVaR / tail-risk penalty
Subtract a conditional value-at-risk term (average of worst-alpha fraction of returns) from the reward to penalize tail outcomes beyond standard deviation.
- **Best for:** Heavy-tailed return distributions and fat-left-tail regimes where variance-based penalties underweight catastrophic losses.
- **Weakness:** CVaR estimation needs enough tail samples — problematic in small-data settings; noisy tail estimates produce unstable gradients and can be ignored if the tail rarely materializes in training.
- **Source:** https://medium.com/@abatrek059/deep-reinforcement-learning-sac-portfolio-optimization-part-three-9c1431f63ff9

### Sortino-style downside-deviation penalty
Penalize only negative-return variance (sqrt of mean of max(0,-R)^2) rather than total volatility, rewarding upside while punishing downside.
- **Best for:** Asymmetric loss preferences where upside volatility is desirable; aligns reward with investor drawdown aversion.
- **Weakness:** Downside-only signal is sparser than full-variance (zeros on up-steps), slowing learning in small data; can be gamed by clustering risk into 'up' periods.
- **Source:** https://arxiv.org/html/2506.04358v1

### Bounded overtrading penalty (local trade-frequency)
Small bounded penalty activated when local trade frequency exceeds a threshold, independent of P&L, to suppress churn for churn's sake.
- **Best for:** High-cost regimes where the agent learns to scalp noise; directly targets the overtrading failure mode without reference to profitability.
- **Weakness:** Threshold is arbitrary and regime-dependent; a fixed cap can suppress legitimate high-frequency alpha in calmer regimes; weight is small and easily dominated by return terms.
- **Source:** https://arxiv.org/html/2604.00031v1

### Holding incentive / correct-NO_TRADE bonus
Small positive bonus when an open position remains profitable under low drawdown, and an implicit bonus to NO_TRADE when no edge is present (cost avoidance = zero cost term).
- **Best for:** Making NO_TRADE a first-class, non-zero-value action; rewards patience and lets the agent 'do nothing' profitably when costs exceed edge.
- **Weakness:** Bonus magnitude is delicate — too large and the agent holds losing positions or refuses to trade; too small and NO_TRADE never wins the argmax against marginal trade signals.
- **Source:** https://arxiv.org/html/2604.00031v1

### Missed-opportunity / leftover-inventory penalty (execution)
Terminal penalty proportional to unexecuted inventory or unrealized opportunity, balanced against per-step slippage cost so the agent must finish but not rush.
- **Best for:** Execution-style tasks where 'never trade' is unsafe; prevents the policy from collapsing to no-action by taxing inaction at the horizon boundary.
- **Weakness:** Terminal-only penalties are temporally distant and hard to credit-assign; too-harsh a penalty forces trades at inopportune times (a hard constraint in disguise).
- **Source:** https://cs224r.stanford.edu/spring_2025/projects/pdfs/CS224r_final_paper%20(4).pdf

### Constrained / shielded RL with soft penalty + hard shield
Soft penalty signal for constraint violations (volume caps, self-trades) during training plus a hard shield that blocks illegal actions at execution time.
- **Best for:** Safety-critical constraints (max position, volume participation, no self-trades) where reward shaping alone is unreliable.
- **Weakness:** Shield can mask the true cost of violations from the policy, weakening the learned signal; soft-penalty coefficient must be tuned or the agent learns to 'pay' the fine when profitable.
- **Source:** https://arxiv.org/html/2510.04952v1

### Funding-rate-aware reward (perpetual futures)
Reward = realized PnL net of fees, slippage, and funding payments, with funding treated as an explicit periodic cost (or income) on open positions.
- **Best for:** Crypto perpetual futures where funding is a dominant, regime-dependent carry cost/income; teaches the agent to factor holding cost into NO_TRADE vs hold decisions.
- **Weakness:** Funding sign flips make holding costly or profitable unpredictably; agent can learn funding-capture strategies that look like reward hacking (collecting funding while ignoring directional risk).
- **Source:** https://www.mdpi.com/2076-3417/15/17/9400

### Economic utility / risk-aversion reward
Map PnL through a risk-aversion utility function (e.g., concave utility with empirically-tuned risk-aversion coefficient) so losses hurt more than equivalent gains.
- **Best for:** Encoding asymmetric loss aversion and diminishing marginal utility of profit; smooths the reward and discourages lottery-style bets.
- **Weakness:** Utility function shape is a strong prior that can dominate the true objective; risk-aversion coefficient is hard to set without historical backtest and bakes in a subjective preference.
- **Source:** https://www.mdpi.com/2227-7390/14/5/794

## Failure Modes

- Policy collapse to 'never trade' / perpetual holding: cost or overtrading penalties too large relative to the return signal make NO_TRADE the dominant action; the crypto-reward sensitivity study explicitly found higher cost-penalty values 'excessively discourage trading (leading to perpetual holding)'.
- Churning / overtrading: cost penalty too low or missed-opportunity penalty too high causes the agent to trade on noise to capture tiny bonuses or avoid missed-opportunity fines, bleeding to fees and slippage.
- Reward hacking / specification gaming: agent exploits flaws in the proxy reward (e.g., suppressing volatility to inflate Sharpe, clustering risk into 'up' periods to dodge downside-only penalties, or collecting funding while ignoring directional risk) — empirically the strongest predictor is low objective alignment, and dense rewards reduce hacking ~19% vs sparse.
- Single-metric over-optimization: optimizing only Sharpe, only return, or only Sortino leads to gaming one aspect (e.g., hiding correlations, masking tail risk) — composite multi-objective rewards mitigate but increase the exploitation surface.
- Terminal-penalty gaming: in execution tasks, a harsh leftover-inventory penalty forces trades at bad prices, while a weak one lets the agent avoid trading and leave inventory — the ablation showed both extremes are unsafe and the penalty must be balanced.
- Sparse-reward exploration failure: trading rewards are mostly zero (NO_TRADE), so naive 'reward-hungry' RL never discovers profitable trade actions; requires intrinsic exploration / curiosity bonuses or dense shaping to reach alpha-generating states.
- Cost-model mis-specification: a wrong slippage/impact curvature either over-penalizes size (under-trading) or under-penalizes it (size-churning); the reward is only as good as the cost model, which in simulation owns economic truth.
- Risk masking / hidden correlations: the agent can satisfy risk limits while hiding dangerous concentrated exposure, creating an illusion of safety that fails catastrophically in regime shifts (the financial-institutions reward-hacking scenario).
- Non-monotone penalty interactions: adding more penalty terms does not consistently improve outcomes — the decomposable-reward study found strongly non-monotone effects, so 'more penalties = safer' is false; each component's marginal effect depends on the others.
- Funding-capture hacking (perps): agent learns to collect funding payments as a 'safe' reward while ignoring directional risk, producing a strategy that looks profitable in backtest but is a disguised carry trade that blows up on funding flips.

## Sources
- https://www.mdpi.com/2571-905x/5/2/546
- https://arxiv.org/html/2506.04358v1
- https://arxiv.org/html/2604.00031v1
- https://arxiv.org/html/2603.29086v2
- http://papers.neurips.cc/paper/1551-reinforcement-learning-for-trading.pdf
- https://cs224r.stanford.edu/spring_2025/projects/pdfs/CS224r_final_paper%20(4).pdf
- https://arxiv.org/html/2510.04952v1
- https://www.mdpi.com/2076-3417/15/17/9400
- https://www.mdpi.com/2227-7390/14/5/794
- https://medium.com/@abatrek059/deep-reinforcement-learning-sac-portfolio-optimization-part-three-9c1431f63ff9
- https://lilianweng.github.io/posts/2024-11-28-reward-hacking
- https://arxiv.org/html/2507.05619v1
- https://dennybritz.com/posts/wildml/learning-to-trade-with-reinforcement-learning
- https://discovery.ucl.ac.uk/id/eprint/10147117/1/The_Recurrent_Reinforcement_Learning_Crypto_Agent.pdf
- https://link.springer.com/article/10.1007/s44196-025-01105-x

## Notes
Key tension confirmed by sources: cost-aware reward design is a two-sided collapse problem. Too much cost/overtrading penalty -> perpetual holding (never trade); too little -> churning. The decomposable-reward paper (arXiv 2604.00031) provides the most directly applicable template: 11 components across return, risk, frictions, and constraints with explicit small weights for holding-incentive (0.03), overtrading (0.02), transaction-burden (0.10), and drawdown (0.05), and it documents that component interactions are non-monotone. The crypto-reward study (MDPI 2227-7390/14/5/794) is the clearest empirical evidence of the 'perpetual holding' failure mode from over-penalizing costs. DSR (Moody et al. NIPS 1999) remains the canonical dense risk-adjusted scaffold for small-data/short-horizon settings. For the V7 project specifically: the (edge - cost) indifference point is the empirically-lockable anchor, penalty weights are LOCKED_INITIAL_BASELINE candidates, and CVaR should be treated with HOLD in small-data regimes (insufficient tail samples) per project lock semantics — prefer Sortino-style downside deviation which is denser. The missed-opportunity / correct-NO_TRADE bonus pair is not found as a named method in the literature but is synthesized from the execution-penalty (Stanford CS224R) and holding-incentive (arXiv 2604.00031) patterns; it directly addresses the key question and should be validated empirically before locking."