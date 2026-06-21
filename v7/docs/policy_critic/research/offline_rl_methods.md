# Research: Offline RL Methods for Financial Trading

## Summary
For a single-instrument crypto/perp trading system with a modest, OOD-prone historical sample, the best primary choice is Implicit Q-Learning (IQL). Rationale tied to the key question: (1) Overestimation avoidance - IQL is the only method among the six that STRUCTURALLY never queries the Q-function on out-of-distribution actions. Instead of penalizing OOD Q-values after the fact (CQL) or constraining the action set via a generative model (BCQ), IQL replaces the Bellman max with expectile regression over ONLY the actions present in the dataset, so OOD overestimation - the dominant offline-RL failure mode - cannot arise by construction. CQL also directly targets overestimation and is the strongest alternative, but it controls overestimation via a conservative penalty weight that is hard to calibrate on small data and tends to over-pessimism, suppressing legitimately good in-distribution trades. (2) Practicality on small data - IQL has essentially one hyperparameter (the expectile tau), no generative model to fit (unlike BCQ's CVAE, which is brittle on small samples), and no large transformer to train (unlike Decision Transformer, which is data-hungry and trajectory-count-sensitive). For a single perp instrument where you may have ~10^4-10^6 logged transitions but narrow action coverage and non-stationary regimes, IQL's in-sample-only updates are the most sample-efficient and the least likely to hallucinate value on unseen position sizes / leverage choices. (3) Recommended configuration: use IQL with a conservative expectile (tau ~0.7-0.8, not 0.9, to stay pessimistic on thin support), advantage-weighted regression for policy extraction with a temperature that prevents the policy from drifting to unsupported actions, and clip/normalize the Q-targets. Secondary: if you can later collect a small amount of live/paper interaction, layer AWAC-style online fine-tuning on top of the IQL warm-start rather than switching to a purely online method. Avoid Decision Transformer unless you have many trajectories and stable regime structure; avoid BCQ unless you can robustly fit a behavior-policy VAE; use CQL only as a cross-check / ensemble member to verify the IQL policy is not silently overestimating. Cross-validate any offline policy with simulation-based cost-aware backtesting (the simulation truth authority) before live promotion - offline-RL pass is NOT live-promotion evidence, consistent with the V7 truth hierarchy.

## Key Methods
### Conservative Q-Learning (CQL)
Penalizes Q-values of out-of-distribution actions so the learned Q-function lower-bounds the true policy value, directly attacking OOD overestimation.
- **Best for:** Diverse, multi-modal offline datasets where you want a provable pessimistic lower bound on policy value; strong on D4RL MuJoCo/AntMaze/Kitchen.
- **Weakness:** The conservative penalty weight (lambda/alpha) is sensitive to tune; on small or narrow data it can become over-pessimistic and suppress good in-distribution actions, and the log-sum-exp CQL(H) variant is compute-heavy.
- **Source:** https://proceedings.neurips.cc/paper/2020/file/0d2b2061826a5df3221116a5085a6052-Paper.pdf

### Implicit Q-Learning (IQL)
Never queries the Q-function on unseen actions; uses expectile regression on in-sample actions to approximate the max, then extracts a policy via advantage-weighted regression.
- **Best for:** Small/narrow offline datasets and OOD-prone regimes: it structurally avoids OOD overestimation (no max over unseen actions) and has essentially one hyperparameter (expectile tau).
- **Weakness:** Performance is bounded by the support of the behavior data; if the dataset is very suboptimal or the action support is thin, the expectile cannot approximate the true max and improvement over the behavior policy is limited.
- **Source:** https://offline-rl-neurips.github.io/2021/pdf/24.pdf

### Batch-Constrained Q-Learning (BCQ)
Restricts the action set used in the Bellman max to actions plausibly produced by the behavior policy (via a state-conditioned VAE + perturbation net), eliminating extrapolation error at the source.
- **Best for:** Continuous-control offline RL where you can fit a reliable generative model of the behavior policy; the original 'no exploration' baseline.
- **Weakness:** Requires training a CVAE generative model of actions, which is data-hungry and brittle on small samples; the perturbation/policy Phi network adds tuning and can still drift if the VAE coverage is poor.
- **Source:** https://proceedings.mlr.press/v97/fujimoto19a/fujimoto19a.pdf

### TD3+BC
Minimalist offline RL: adds a weighted behavior-cloning term (alpha * ||pi(s)-a||^2) to the TD3 actor loss and normalizes Q-values; only one extra hyperparameter.
- **Best for:** Quick, low-tuning baseline on modest datasets where you want a simple policy-constraint method that stays close to logged behavior.
- **Weakness:** The BC anchor limits how much the policy can improve over the behavior data; on low-quality or narrow data it collapses toward the (possibly bad) behavior policy, and it does not explicitly bound Q-overestimation.
- **Source:** https://github.com/sfujim/TD3_BC

### Advantage Weighted Actor-Critic (AWAC)
Trains an off-policy critic with TD learning and an actor weighted by exp(advantage), implicitly constraining the policy to high-advantage in-distribution actions; designed for offline pretrain + online fine-tune.
- **Best for:** Settings where you have an offline dataset AND can collect a small amount of online interaction (e.g. paper/sim-to-live fine-tuning), with expert-ish demonstrations.
- **Weakness:** Pure-offline performance is weaker than IQL/CQL; the advantage weighting assumes the critic is reasonable, so on small OOD-prone data the critic itself can mislead the weighted actor before online correction kicks in.
- **Source:** https://arxiv.org/abs/2006.09359

### Decision Transformer (sequence-modeling)
Casts RL as conditional sequence modeling: a GPT-style transformer autoregressively predicts actions conditioned on return-to-go, states, and past actions, with no Bellman backup and no Q-value maximization.
- **Best for:** Long-horizon credit assignment and regimes where you want to avoid value-function bootstrapping entirely; no OOD Q-overestimation by construction.
- **Weakness:** Data-hungry (transformer + autoregressive trajectory modeling needs many trajectories), sensitive to the return-to-go conditioning at inference, and struggles to stitch together suboptimal trajectories into a better policy; impractical on a single instrument's modest history.
- **Source:** https://arxiv.org/abs/2106.01345

## Failure Modes

- Q-value overestimation on OOD actions: the dominant offline-RL failure - bootstrapping from unseen actions accumulates optimistic bias via the Bellman backup (CQL/IQL/BCQ mitigate; standard TD3/SAC do not).
- Over-pessimism / conservative collapse: too-large a CQL penalty or too-low an IQL expectile suppresses all in-distribution actions, yielding a near-no-op policy that avoids trading.
- Behavior-policy collapse: TD3+BC and AWAC anchor to the logged behavior; if the logged strategy is suboptimal (common in early crypto logs), the learned policy cannot exceed it by much.
- Generative-model brittleness (BCQ): a CVAE trained on small/narrow action data under-covers the real action space, so the constrained max still drifts OOD.
- Non-stationarity / regime shift: financial data is time-varying, so the 'offline distribution' itself shifts; any method's pessimism/constraint is calibrated to a regime that may no longer hold at deployment (OOD in the state distribution, not just actions).
- Thin action support for rare but important actions (e.g. large deleveraging): in-sample-only methods (IQL) cannot upweight actions barely present in the data, so tail-risk behavior is under-learned.
- Return-conditioning failure (Decision Transformer): at inference the return-to-go prompt is an extrapolation target; if the dataset never achieved that return, the model produces out-of-distribution behavior.
- Critic misestimation misleading the actor (AWAC): on small data the off-policy critic can be wrong, and the advantage-weighted actor amplifies the wrong actions before any online correction.
- Confusing offline backtest with live evidence: an offline-RL policy that looks good on held-out historical data can still fail live due to transaction costs, slippage, funding, and adversarial market response - simulation cost modeling must gate promotion.

## Sources
- https://proceedings.neurips.cc/paper/2020/file/0d2b2061826a5df3221116a5085a6052-Paper.pdf
- https://offline-rl-neurips.github.io/2021/pdf/24.pdf
- https://proceedings.mlr.press/v97/fujimoto19a/fujimoto19a.pdf
- https://github.com/sfujim/TD3_BC
- https://arxiv.org/abs/2006.09359
- https://arxiv.org/abs/2106.01345
- https://www.emergentmind.com/topics/conservative-q-learning-cql-model
- https://www.emergentmind.com/topics/implicit-q-learning-iql
- https://www.emergentmind.com/topics/batch-constrained-q-learning-bcq
- https://arxiv.org/html/2408.10932v3
- https://link.springer.com/article/10.1007/s00521-026-11966-8
- https://transferlab.ai/pills/2023/implicit-q-learning
- https://bair.berkeley.edu/blog/2020/09/10/awac
- https://proceedings.neurips.cc/paper/2021/hash/7f489f642a0ddb10272b5c31057f0663-Abstract.html

## Notes
All six methods were surveyed with primary sources (NeurIPS/ICML papers and author repos). Preference given to 2023-2026 surveys where available: the Springer 2026 survey on distribution shift/OOD in offline RL (link.springer.com/article/10.1007/s00521-026-11966-8) and the 2024 'Evolution of Reinforcement Learning in Quantitative Finance' survey (arxiv 2408.10932) confirm that limited data coverage and non-stationarity are the binding constraints for financial offline RL, supporting the IQL-first recommendation. The Decision Transformer finance angle is active (LiT limit-order-book transformer, Frontiers in AI 2025) but those are forecasting/LOB models, not offline-RL policy learners, so they do not change the policy-learning recommendation. Key tradeoff captured: CQL gives the strongest formal overestimation bound but is the hardest to tune on small data; IQL gives the most robust practical overestimation avoidance via in-sample-only updates with minimal tuning. BCQ, TD3+BC, and AWAC are viable but each has a structural disadvantage on small OOD-prone financial data (generative-model fit, behavior-anchor collapse, and critic-misleads-actor respectively). Decision Transformer is data-hungry and best deferred until a large multi-regime trajectory corpus exists. All claims above are grounded in the cited URLs; no claim relies on training-data recall alone.