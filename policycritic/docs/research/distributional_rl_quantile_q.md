# Distributional RL / Quantile Q-Learning

## Abstract

Distributional RL models the **full distribution of returns** Z(s,a) rather than just the expected value Q(s,a). QR-DQN (Dabney et al. 2017, AAAI 2018) learns N quantiles of the return distribution via quantile regression. IQN (Dabney et al. 2018, ICML 2018) extends this to a continuous quantile function via implicit representation. Distributional RL enables **risk-aware decision making**: instead of "expected return = +1.5R", the critic outputs "5th percentile = -2.0R, 50th = +0.5R, 95th = +3.0R."

## Why It Matters for V7

The V7 canonical design specifies a **distributional IQL** with 16-32 quantile Q-heads. The risk manager cares about the lower tail (5th-20th percentile) more than the mean. A distributional critic can calibrate its verdict to a specific quantile: "VETO_TO_NO_TRADE if the 20th percentile of Q(s, LONG_NOW) is negative." This is the core mechanism for risk-aware gating.

## What the Literature Says

### QR-DQN

- Represents Z(s,a) as a uniform mixture of N Diracs at positions θ_i(s,a)
- Each θ_i corresponds to quantile τ_i = (i-0.5)/N
- Trained with quantile Huber loss: ρ_τ^κ(δ) = |τ - I{δ<0}| · L_κ(δ) / κ
- Wasserstein contraction: the distributional Bellman operator is a contraction in ∞-Wasserstein distance
- Atari-57: 864% human-normalized mean (vs DQN 228%)

### IQN

- Learns implicit quantile function: input τ ~ U(0,1) → output quantile value
- Can query any quantile, not just N fixed ones
- Enables risk-sensitive policies via distortion risk measures
- Atari-57: 1019% human-normalized mean

### Risk-Sensitive RL

By distorting the quantile sampling distribution at decision time (e.g., sampling only low quantiles), the policy becomes risk-averse without retraining.

## How It Applies to V7

1. **V3 critic outputs**: Q(s,a) at 16-32 quantile levels (not just mean)
2. **Calibrated lower-quantile**: The 20th percentile of Q(s, LONG_NOW) compared to 0 determines VETO
3. **Confidence adjustment from quantile spread**: Wide interquartile range → high uncertainty → DOWNWEIGHT_CONFIDENCE
4. **Conformal calibration**: Post-training calibration of quantile coverage against realized outcomes

## How It Can Fail

| Failure Mode | Mitigation |
|-------------|-----------|
| Quantile crossing (θ_i > θ_j for i < j) | Monotonicity constraint or post-processing sort |
| Tail quantile instability (1st/99th) | Use 5th-95th range, not extremes |
| Financial noise → unstable quantiles | Fewer quantiles (16); Huber loss for robustness |
| Distributional Bellman operator not contraction with function approximation | Empirical validation; bounded updates |

## Decision: USE LATER (V3 distributional IQL)

Distributional RL is essential for risk-aware gating in V3. QR-DQN-style quantile regression integrates naturally with XGBoost (`objective='reg:quantileerror'`). IQN is reserved for V4+.
