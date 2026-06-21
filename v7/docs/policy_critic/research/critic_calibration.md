# Research: Critic and Calibration Patterns for Trading

## Summary
Build the V7 PolicyCritic as a small, calibrated off-policy value evaluator rather than a free-running online critic. Concretely: (1) Train the critic with Fitted Q Evaluation (FQE) on the existing logged (state, proposed_action, realized_net_R, next_state) tuples — this evaluates the actor's proposed action WITHOUT re-collecting data, which is the defining constraint of small-data trading. The critic's target is realized net R (post-cost, post-slippage), so its Q(s,a) is directly on the scale of the outcome you care about, satisfying 'critic_value correlates with realized net R'. (2) Make the critic distributional (QR-DQN / IQN with a small N such as 16-32 quantiles) so it outputs a return distribution, not just a mean — this gives downside-aware uncertainty (lower-quantile / CVaR) for the veto decision instead of a single overfit point estimate. (3) Calibrate that distributional critic against realized outcomes with conformal prediction: hold out a calibration slice of realized trades, compute nonconformity scores |realized_net_R - critic_mean| (or quantile-violation scores), and derive a finite-sample coverage-valid interval / veto threshold. This is the COPP / 'Conformal Prediction Beyond the Horizon' pattern adapted to trading, and it is the only step that gives a real (distribution-free) confidence guarantee rather than a heuristic score. (4) Guard against the dominant small-data failure mode — Q-overestimation on out-of-distribution actions — by adding a Cal-QL-style conservative penalty with a behavior-policy reference lower bound, so the critic stays on the scale of realized returns instead of drifting optimistic. (5) Emit the critic's output as an adjusted confidence = P(return >= 0 | s, a) estimated from the calibrated quantile distribution, plus a hard VETO when the calibrated lower bound of the return interval is below zero at the chosen coverage level. In practice, prefer the retrofittable 'Conformal Calibration' post-training route first (lowest implementation risk on small data): train a modest FQE+QR-DQN critic, then conformal-calibrate its output against realized net R, before investing in full Cal-QL pre-training. Keep N small and regularize heavily; on small data the calibrated interval width is the honest signal of how much you do not know.

## Key Methods
### Actor-Critic (Critic evaluates Actor's proposed action)
Separates policy (actor) from value estimator (critic); the critic critiques the actor's action via a TD error / advantage and drives policy updates.
- **Best for:** Directly maps to the V7 PolicyCritic pattern: a learned critic reviews a proposed action and outputs an evaluation that can be turned into an adjusted confidence or veto.
- **Weakness:** Critic is only as good as its value estimate; on small/noisy trading data the critic itself overfits and its TD-error signal becomes a noisy, miscalibrated veto.
- **Source:** http://incompleteideas.net/book/ebook/node66.html

### QR-DQN (Quantile Regression DQN)
Distributional RL that predicts N quantiles of the return distribution per state-action instead of a single mean Q-value, using Huber quantile regression loss.
- **Best for:** Capturing return uncertainty and risk-sensitive selection (e.g. maximize a lower quantile / CVaR) — useful when net R is heavy-tailed and a mean hides downside.
- **Weakness:** Fixed discrete quantile support; quantile estimates are point values without coverage guarantees, so 'confidence' is relative, not calibrated to realized outcomes.
- **Source:** https://cdn.aaai.org/ojs/11791/11791-13-15319-1-2-20201228.pdf

### IQN (Implicit Quantile Networks)
Extends QR-DQN by learning the full continuous quantile function via sampled quantile fractions, approximating any return distribution given capacity.
- **Best for:** Flexible, continuous return-distribution modeling; supports risk criteria computed at arbitrary quantile levels without retraining.
- **Weakness:** Higher compute/memory; still no finite-sample calibration guarantee — quantile spread is a heuristic uncertainty signal, not a coverage-calibrated interval.
- **Source:** https://proceedings.mlr.press/v80/dabney18a/dabney18a.pdf

### Conformal Prediction (calibrated intervals)
Distribution-free method that uses nonconformity scores on a held-out calibration set to build prediction intervals with finite-sample coverage guarantees.
- **Best for:** Turning any critic's raw value/score into a calibrated confidence interval or veto threshold tied to a guaranteed coverage of realized outcomes.
- **Weakness:** Requires exchangeable calibration data and enough realized-outcome samples; trading time series violate exchangeability and need weighted/subsampled variants.
- **Source:** https://en.wikipedia.org/wiki/Conformal_prediction

### Conformal Off-Policy Prediction (COPP)
Applies weighted conformal prediction to off-policy evaluation, producing prediction intervals for a target policy's return from logged data under distribution shift.
- **Best for:** Building a calibrated critic whose value intervals are valid under the behavior/target policy mismatch typical of small-data trading logs.
- **Weakness:** Importance-sampling weights suffer the curse of horizon (variance explodes over long horizons); needs careful weighting and enough calibration data.
- **Source:** https://proceedings.mlr.press/v206/zhang23c/zhang23c.pdf

### Conformal Prediction Beyond the Horizon (distributional RL + CP)
Integrates distributional RL with conformal calibration via pseudo-returns from truncated rollouts and time-aware experience-replay subsampling to restore exchangeability.
- **Best for:** Distribution-free, calibrated return intervals for infinite-horizon on/off-policy evaluation — closest off-the-shelf recipe for a calibrated trading critic under temporal dependence.
- **Weakness:** Approximate exchangeability only; asymptotic coverage bounds depend on Wasserstein-quality distributional fit; complex to implement on small samples.
- **Source:** https://arxiv.org/html/2510.26026v1

### Fitted Q Evaluation (FQE)
Off-policy evaluation that iteratively regresses Q(s,a) toward r + gamma*Q(s',pi(s')) on logged data to estimate a target policy's value without re-collecting data.
- **Best for:** Evaluating/Vetoing a proposed policy on existing trade logs — no live re-collection needed; minimax-optimal in tabular/linear cases; gives a critic value directly comparable to realized net R.
- **Weakness:** Exponential error amplification in horizon with linear function approximation; can diverge off-policy without strong representation/regularization; needs deep-RL tricks (ResNet, shared repr) for stability.
- **Source:** https://offline-rl-neurips.github.io/2021/pdf/17.pdf

### Bootstrapping FQE (off-policy inference)
Adds bootstrap resampling on top of FQE to infer the distribution of the policy-evaluation error, enabling confidence intervals on the FQE value estimate.
- **Best for:** Attaching uncertainty/CIs to the FQE critic value so a veto threshold can be set with statistical meaning on small logged data.
- **Weakness:** Asymptotic guarantees only; bootstrap is costly and assumes the logged sample is representative — fragile under regime change in markets.
- **Source:** https://proceedings.mlr.press/v139/hao21b/hao21b.pdf

### Cal-QL (Calibrated Offline RL)
Conservative offline Q-learning whose learned Q-values are calibrated: lower-bounded by a reference (behavior) policy's true value and upper-bounded by the learned policy's value.
- **Best for:** Prevents both overestimation (OOD actions) and underestimation (over-conservative collapse) — keeps critic values on the scale of ground-truth returns so they correlate with realized net R.
- **Weakness:** Calibration is w.r.t. a reference policy's value, not realized per-trade outcomes; still needs offline data coverage and a sensible reference policy.
- **Source:** https://arxiv.org/html/2303.05479v4

### Conformal Calibration (post-training, retrofittable)
A post-training stage that retrofits conformal prediction onto any value-based RL critic to induce pessimism/robustness at inference without retraining the agent.
- **Best for:** Minimal-change path to a calibrated veto: take the existing V7 PolicyCritic output and conformal-calibrate it against realized outcomes to get a coverage-valid abstain/veto threshold.
- **Weakness:** Post-hoc only — cannot fix a structurally biased critic; exchangeability assumptions need handling for time-series trading data.
- **Source:** https://www.alexinch.com/assets/pdfs/ucl_msc_thesis.pdf

## Failure Modes

- Q-value overestimation on out-of-distribution / unseen actions: the dominant offline-RL failure; on small trading data the critic confidently approves actions it has never seen, producing false vetoes-or-approvals (Cal-QL/CQL mitigate but do not eliminate).
- Exponential error amplification over the horizon in FQE with linear/poor function approximation — value estimates blow up over multi-step horizons, so long-horizon SWING critics diverge first.
- Loss of exchangeability in conformal calibration: trading time series are temporally dependent and non-stationary (regime change), violating the core conformal assumption; naive CP intervals mis-cover. Needs weighted/subsampled (COPP-IS) or time-aware (experience-replay subsampling) variants.
- Curse of horizon in importance-sampling-weighted COPP: IS weights multiply variance across steps, making calibrated intervals uselessly wide on long horizons.
- Small calibration set: conformal coverage guarantees are finite-sample but require enough calibration points; with few realized trades the intervals are either too wide to be useful or unstable.
- Distributional model misfit (QR-DQN/IQN): if the learned return distribution is a poor fit (e.g. multimodal regime returns), quantile-based 'confidence' is misleading even if the mean looks right.
- Over-conservative collapse: pure pessimism (CQL without Cal-QL calibration) drives Q-values too low, vetoing everything and producing a critic that never approves — useless as an action reviewer.
- Reference-policy sensitivity in Cal-QL: calibration is relative to a chosen reference (behavior) policy; a bad reference on small data yields a miscalibrated lower bound.
- Regime drift between calibration and deployment: a critic calibrated on a bull/sideways regime mis-covers in a crash — realized-net-R correlation breaks exactly when you need it.
- Bootstrap FQE variance inflation: bootstrapping on a small logged sample gives unstable CIs that understate true uncertainty.

## Sources
- http://incompleteideas.net/book/ebook/node66.html
- https://cdn.aaai.org/ojs/11791/11791-13-15319-1-2-20201228.pdf
- https://proceedings.mlr.press/v80/dabney18a/dabney18a.pdf
- https://en.wikipedia.org/wiki/Conformal_prediction
- https://proceedings.mlr.press/v206/zhang23c/zhang23c.pdf
- https://arxiv.org/html/2510.26026v1
- https://neurips.cc/virtual/2025/poster/118031
- https://offline-rl-neurips.github.io/2021/pdf/17.pdf
- https://proceedings.mlr.press/v139/hao21b/hao21b.pdf
- https://arxiv.org/abs/2202.04970
- https://arxiv.org/html/2303.05479v4
- https://neurips.cc/virtual/2023/poster/72205
- https://www.alexinch.com/assets/pdfs/ucl_msc_thesis.pdf
- https://www.imperial.ac.uk/media/imperial-college/faculty-of-natural-sciences/department-of-mathematics/math-finance/TobyWestonSubmission.pdf
- https://pmc.ncbi.nlm.nih.gov/articles/PMC11888913

## Notes
The actor-critic separation is the structural match to V7's PolicyCritic: actor = the policy proposing the trade, critic = a learned value evaluator that reviews the proposed action. The research chain that best fits 'small-data, calibrated, no-re-collection' is FQE (off-policy evaluation on logged trades) + distributional QR-DQN/IQN (return uncertainty) + conformal calibration (finite-sample coverage against realized net R) + Cal-QL-style conservatism (overestimation guard). Two important caveats for trading specifically: (a) conformal exchangeability is violated by time series — use weighted/time-aware variants (COPP, Conformal Prediction Beyond the Horizon), and accept only approximate coverage; (b) FQE error amplifies with horizon, so calibrate the critic per-horizon and prefer the SWING baseline horizon first. Distributional RL alone (QR-DQN/IQN) gives uncertainty shape but NOT calibration — it must be paired with conformal calibration to make critic_value a statistically meaningful function of realized net R. Cal-QL's notion of 'calibration' is scale-calibration w.r.t. a reference policy's value, which is complementary but different from conformal outcome-calibration; both are useful. On small data, start with the retrofittable post-training conformal-calibration route before full Cal-QL pre-training.