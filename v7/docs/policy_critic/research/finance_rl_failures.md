# Research: RL Failure Modes in Finance and Guardrails

## Summary
Consensus (2023-2026): do NOT train or explore online in live markets. Train offline on historical trajectories, evaluate the learned policy with off-policy evaluation (OPE: FQE, doubly-robust, marginalized importance sampling) BEFORE any deployment, and only ever let a learned critic influence live trading under layered guardrails. For small-data trading specifically: (1) Use a pessimistic offline critic (CQL or, preferably for low data, IQL/SCQ) so the value function never overestimates OOD actions — the single most cited failure mode in offline RL. (2) Gate promotion with high-confidence OPE confidence intervals plus the Deflated Sharpe Ratio to correct for the multiple-comparisons bias introduced by hyperparameter/seed/reward search; track and report the trial count honestly. (3) Deploy in SHADOW MODE first: the critic produces signals that are logged and compared against the actual execution policy and realized fills, with no order authority, until OPE-predicted and realized distributions match over a statistically meaningful window. (4) Wrap the agent in a hard SHIELD/KILL-SWITCH at the order-gateway layer (independent of the AI layer, per FMSB 2026 guidance) that enforces max gross exposure, position limits, banned-segment/trading-halt rules, and a deterministic safe-fallback policy that takes over on any breach. (5) Add CONSERVATIVE PENALTIES in the reward (downside risk, CVaR, differential return) rather than a single return/Sharpe metric to prevent reward hacking. (6) Continuously monitor DISTRIBUTIONAL SHIFT between the offline dataset and live market states (anomaly-score / OOD-distance on state-action pairs, as in RLAD and SCQ); auto-degrade to the fallback policy when shift exceeds a calibrated threshold. (7) Embed realistic transaction costs, slippage, and market impact in training to close the simulation-to-reality gap. (8) Use walk-forward, regime-split, and cross-asset validation rather than a single out-of-sample period. The critic should be treated as an advisory signal under a risk-gated policy authority (V7-style), never as an autonomous order-placer, until it has accumulated sufficient live shadow evidence to relax guardrails incrementally.

## Key Methods
### Offline RL for trading (surveys & benchmarks, 2024-2025)
Train policies on static historical trajectories with no live interaction; the dominant paradigm pushed by recent surveys and FinRL contests to avoid risky online exploration.
- **Best for:** Small-data, high-cost-of-exploration trading where live trial-and-error is unacceptable; enables reproducible benchmarking on withheld out-of-sample data.
- **Weakness:** Suffers from distributional shift and OOD action overestimation; performance is bounded by the coverage and quality of the offline dataset (single-policy concentrability).
- **Source:** https://arxiv.org/html/2504.02281v3

### FinRL / FinRL-Meta / FinRL Contest series (2023-2025)
The flagship open-source financial RL framework and contest ecosystem (stock, crypto, LOB, LLM-signal tasks) with standardized market environments and backtesting.
- **Best for:** Reproducible prototyping, education, and community benchmarking of DRL agents (A2C, DDPG, PPO, TD3, SAC) across asset classes.
- **Weakness:** Contests themselves note RL policies are unstable and sensitive to hyperparameters, seeds, and market noise; default backtesting on static data ignores market impact (simulation-to-reality gap); 2025 tasks still rely on online-style PPO with risk-sensitive add-ons rather than true offline evaluation.
- **Source:** https://open-finance-lab.github.io/FinRL_Contest_2025

### FinRL-DeepSeek / LLM-infused risk-sensitive RL (2025)
Successor line that injects LLM-generated risk/sentiment signals from news and SEC filings into the RL agent's state, with risk-sensitive reward shaping.
- **Best for:** Combining structured market data with unstructured text signals; aligning agents with market narratives and latent causal drivers.
- **Weakness:** Sentiment-only models fail under macro shocks; adds LLM prompt-injection and signal-noise risks on top of base RL instability; still primarily online PPO-based with limited OPE.
- **Source:** https://arxiv.org/abs/2502.07393

### Conservative Q-Learning (CQL) / pessimistic offline RL
Adds a log-sum-exp penalty that lowers Q-values for OOD actions so the policy cannot exploit extrapolation errors in the offline dataset.
- **Best for:** Offline trading datasets with limited coverage; provides a lower-bound (pessimistic) value estimate that is safe to deploy; strong even at 1-10% data fractions.
- **Weakness:** Conservatism strength alpha requires careful (often Lagrangian/dual) tuning; can be overly conservative near the data manifold, producing non-smooth Q-values and under-utilizing safe interpolatable actions.
- **Source:** https://proceedings.neurips.cc/paper/2020/file/0d2b2061826a5df3221116a5085a6052-Paper.pdf

### Implicit Q-Learning (IQL)
In-sample value learning via expectile regression that never queries unseen actions, avoiding OOD errors entirely without explicit behavior policy estimation.
- **Best for:** Low-data regimes and sparse-reward long-horizon settings; robust policy extraction via advantage-weighted cloning; matches or beats CQL on stitching suboptimal trajectories.
- **Weakness:** Cannot evaluate or improve on actions outside the dataset at all (no exploration of near-distribution actions); performance ceiling is tied to the best in-distribution behavior.
- **Source:** https://www.emergentmind.com/topics/implicit-q-learning-iql

### Strategically Conservative Q-Learning (SCQ, 2024)
Partitions OOD actions into 'easy' (near-manifold, safe to interpolate) and 'hard' (far, extrapolation-prone), applying differentiated penalties for calibrated pessimism.
- **Best for:** Reducing unnecessary over-conservatism while still guarding against hard extrapolation errors; outperforms standard CQL on MuJoCo/AntMaze.
- **Weakness:** Requires reliable OOD-distance partitioning; added complexity and hyperparameters; not yet validated in financial-market distributions.
- **Source:** https://arxiv.org/html/2406.04534v1

### Off-Policy Evaluation (OPE) — doubly-robust / marginalized IS / FQE
Estimate a target policy's value using only data from a behavior policy (importance sampling, doubly-robust, fitted-Q-evaluation) before any deployment.
- **Best for:** High-confidence, low-risk pre-deployment evaluation of a learned critic/policy; the consensus 'evaluate first' gate before live trading; handles non-stationary decision problems via predictive OPE.
- **Weakness:** High variance for long horizons (curse of horizon); importance-sampling weights explode under large behavior/target divergence; confounders and latent state bias estimates; requires sufficient behavior-policy support.
- **Source:** http://papers.neurips.cc/paper/9161-towards-optimal-off-policy-evaluation-for-reinforcement-learning-with-marginalized-importance-sampling.pdf

### Deflated Sharpe Ratio & backtest-overfitting framework (Bailey & Lopez de Prado)
Corrects reported Sharpe for selection bias under multiple testing, non-normal returns, and short track lengths to separate skill from statistical flukes.
- **Best for:** Any RL trading pipeline that tries many configs/seeds/rewards; mandatory multiple-comparisons correction before believing backtest performance.
- **Weakness:** Requires honest accounting of number of trials (often under-reported); does not itself fix market-impact or regime-shift omission; only addresses selection bias, not model misspecification.
- **Source:** https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf

### Risk-aware composite reward (anti-reward-hacking, 2025)
Multi-component differentiable reward (annualized return, downside risk, differential return, Treynor) with tunable weights to avoid single-metric reward hacking.
- **Best for:** Encoding investor risk preferences and preventing the agent from over-optimizing one objective (e.g., raw return) at the cost of tail risk.
- **Weakness:** Weight tuning becomes a new hyperparameter search surface (re-introducing overfitting risk); modular design does not by itself fix OOD or non-stationarity issues.
- **Source:** https://arxiv.org/html/2506.04358v1

### Safe RL shields / kill-switches / constrained execution (2025)
Compliance shield sits between the RL agent and the order gateway, blocking/modifying unsafe actions with zero-violation guarantees plus a kill-switch for fault conditions.
- **Best for:** Live deployment of RL execution agents where regulatory and risk limits must hold by construction; gives compliance officers verifiable trust.
- **Weakness:** Shield design must anticipate all unsafe states (incomplete coverage); over-restrictive shields cap performance; does not solve policy quality, only enforces hard constraints.
- **Source:** https://arxiv.org/html/2510.04952v1

### RL with training wheels / fallback-policy intervention (Mao et al., NeurIPS)
Online RL in production with a known-safe fallback policy that takes over whenever the system enters an unsafe state, plus extra penalties for unsafe actions.
- **Best for:** Systems that need online adaptation but cannot tolerate catastrophic actions; the fallback bounds downside during learning and deployment.
- **Weakness:** Requires a reliable 'safe' fallback policy to exist; intervention boundaries hard to define in noisy markets; fallback handoff can be unstable.
- **Source:** https://people.csail.mit.edu/hehaodele/projects/NIPS19-safety/paper.pdf

### Ensemble methods for policy instability (FinRL Contest 2024)
Train multiple RL agents and ensemble them to mitigate policy instability from hyperparameter, seed, and market-noise sensitivity (especially in crypto).
- **Best for:** High-volatility markets where single-agent policies are unstable; reduces variance in live behavior.
- **Weakness:** Multiplies training cost and the sampling bottleneck; does not address root causes of instability (value-function approximation error, non-stationarity); ensembling can mask systematic bias.
- **Source:** https://arxiv.org/html/2504.02281v3

### Regime-adaptive continual learning for portfolio management (2025-2026)
Detect regime shifts in real time, train on the prior regime, and deploy/transfer the learned policy into the new regime with continual-learning retention.
- **Best for:** Non-stationary markets where fixed-window retraining fails; explicitly addresses concept drift and regime change.
- **Weakness:** Real-time regime detection is itself unreliable; catastrophic forgetting during transfer; limited comparison so far; does not eliminate OOD risk at regime boundaries.
- **Source:** https://arxiv.org/html/2606.00143v1

## Failure Modes

- Q-overestimation / extrapolation error on OOD actions: offline Bellman backup queries unseen actions whose Q-values are optimistically biased, causing the policy to exploit non-existent high-value regions (the canonical offline RL failure; mitigated by CQL/IQL pessimism).
- Backtest overfitting & multiple-comparisons bias: trying thousands of config/seed/reward variants and selecting the best in-sample yields strategies that degrade out-of-sample; selection bias inflates Sharpe unless deflated (Bailey & Lopez de Prado).
- Non-stationarity / regime shift: markets are non-stationary; policies memorize training regimes and fail on new ones. Experience replay can make non-stationarity worse, not better; multi-agent markets become radically non-stationary.
- Reward hacking: single-metric rewards (cumulative return, Sharpe) are gamed by the agent (churning, painting the tape, influencing the market); composite risk-aware rewards reduce but do not eliminate this.
- Simulation-to-reality gap / market impact: static backtests ignore the feedback loop where the agent's own trades move prices, so strategies are fragile live; identified as the single greatest obstacle to deploying RL in finance.
- Stochastic-policy unpredictability in live trading: policy-gradient exploration that works in backtest injects random suboptimal actions in live markets where the optimal action is unequivocal; needs deterministic overrides or threshold gating.
- Multi-agent non-stationarity & market-conduct risk: multiple RL agents reacting to each other can produce emergent collusive or manipulative behavior and market-wide outages (FMSB 2026 scenario).
- Sampling bottleneck & policy instability: RL policies are highly sensitive to hyperparameters, seeds, and market noise, especially in high-volatility crypto; ensembles mitigate but do not cure the root value-approximation error.
- Data leakage / look-ahead bias in feature pipelines: future information leaking into training features inflates backtest performance and causes live collapse.
- OPE variance & confounding: long-horizon importance-sampling estimators suffer curse-of-horizon; latent confounders bias value estimates, giving false confidence in pre-deployment evaluation.

## Sources
- https://arxiv.org/html/2504.02281v3
- https://open-finance-lab.github.io/FinRL_Contest_2025
- https://arxiv.org/abs/2502.07393
- https://arxiv.org/html/2408.10932v3
- https://www.annualreviews.org/content/journals/10.1146/annurev-statistics-112723-034423
- https://proceedings.neurips.cc/paper/2020/file/0d2b2061826a5df3221116a5085a6052-Paper.pdf
- https://www.emergentmind.com/topics/implicit-q-learning-iql
- https://arxiv.org/html/2406.04534v1
- http://papers.neurips.cc/paper/9161-towards-optimal-off-policy-evaluation-for-reinforcement-learning-with-marginalized-importance-sampling.pdf
- https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf
- https://www.quantresearch.org/Publications.htm
- https://portfoliooptimizationbook.com/book/8.3-dangers-backtesting.html
- https://arxiv.org/html/2506.04358v1
- https://arxiv.org/html/2510.04952v1
- https://people.csail.mit.edu/hehaodele/projects/NIPS19-safety/paper.pdf
- https://www.emergentmind.com/topics/safe-reinforcement-learning
- https://openreview.net/forum?id=QtSw71HJ6M
- https://alphaarchitect.com/reinforcement-learning-for-trading
- https://arxiv.org/html/2606.00143v1
- https://ojs.aaai.org/index.php/AAAI/article/view/41493/45454
- https://stockalpha.ai/alpha-learning/ai-powered-trading-bots-using-reinforcement-learning-for-market-strategy-optimiz
- https://fmsb.com/wp-content/uploads/2026/02/FMSB-AI-in-Trading_Final_12.02.26_FINAL.pdf
- https://www.emergentmind.com/topics/conservative-q-learning-cql
- https://proceedings.mlr.press/v162/shi22c.html
- https://github.com/AI4Finance-Foundation/FinRL

## Notes
The 2023-2026 literature converges on a clear hierarchy: offline training + off-policy evaluation FIRST, then shadow deployment under hard external shields, then incremental relaxation of guardrails. The FinRL ecosystem remains the de facto research benchmark but its contest tasks still lean on online PPO-style agents with risk add-ons, and its own organizers acknowledge policy instability and the sampling bottleneck. The most actionable advances for a small-data trading system come from the broader offline-RL literature (CQL, IQL, SCQ, OPE/FQE, distributional-shift anomaly detection) and the financial-statistics overfitting literature (Deflated Sharpe, probability of backtest overfitting), not from the headline trading-RL papers. Key gap: most pessimistic offline-RL methods are validated on D4RL/MuJoCo, not financial distributions; practitioners must re-validate conservatism strength and OOD-distance thresholds on their own market data. The FMSB (2026) AI-in-Trading report is the strongest industry consensus document for live-deployment guardrails: independent gateway controls outside the AI layer, model-risk-management frameworks, and explicit kill-switches. For this repo (V7), the critic should be wired as an advisory signal under the existing simulation > realized > contract > runtime > model truth hierarchy, never bypassing simulation cost gates or risk gates.