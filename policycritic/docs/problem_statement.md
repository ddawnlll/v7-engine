# Problem Statement — V7 Policy Critic

> Status: Docs/Design Only
> Created: 2026-06-23

## 1. What Exact Problem Are We Solving?

### 1.1 The Core Problem

V7 is building a trading system where:

1. **AlphaForge** (XGBoost-based scorer, planned but not implemented) proposes actions (LONG_NOW / SHORT_NOW / NO_TRADE) with calibrated probabilities and expected returns.
2. **V7 Policy Gates** apply deterministic thresholds (min confidence, min expected-R, regime consistency, degradation checks).
3. **Runtime** handles execution eligibility.

The problem: **deterministic gates cannot express everything that matters for risk assessment.** Specifically:

- **Regime-conditional risk**: A LONG with 0.65 confidence in a low-volatility trending-up regime has a very different risk profile from the same confidence in a high-volatility transition regime. Deterministic thresholds treat them identically.
- **Multi-factor interaction**: Spread widening + anomaly score elevation + regime transition + confidence degradation may each individually pass thresholds, but together they signal a dangerous trade. Gates check factors independently.
- **Expected value estimation**: Gates use thresholds (expected_R >= X), but a learned component could estimate a richer expected value considering the full state context.
- **Calibration drift**: When calibration degrades (confidence_kind → DEGRADED), gates either block everything or let everything through. A learned critic could apply nuanced confidence downweighting.
- **OOD detection**: When the market state is far from training distribution, gates have no systematic mechanism to detect this. A critic could detect and downweight OOD states.

### 1.2 What We're NOT Solving

- We are NOT replacing the AlphaForge scorer (alpha discovery stays with AlphaForge).
- We are NOT replacing V7 policy gates (deterministic safety barriers stay).
- We are NOT building the main decision engine as RL (RL is for the advisory critic only).
- We are NOT adding new trade actions or modes.
- We are NOT bypassing cost, funding, or risk holds.

## 2. Why Rule-Based Gates Alone Are Not Enough

### 2.1 What Gates Do Well

Deterministic gates excel at:
- Hard safety boundaries (max daily loss, max drawdown, circuit breaker)
- Non-negotiable constraints (confidence floor, spread limit)
- Audit trail clarity (every gate decision has a deterministic reason)
- Speed (no inference latency)
- Verifiability (you can prove a gate blocks when condition X is true)

### 2.2 What Gates Cannot Do

| Limitation | Example | Consequence |
|---|---|---|
| **Context-insensitive thresholds** | Confidence 0.55 in calm regime vs 0.55 in volatile regime — same gate treatment | Misses regime-conditional risk |
| **Single-factor decisions** | Each gate checks one condition independently | Misses dangerous factor combinations |
| **No expected value estimation** | Gates use thresholds, not learned value functions | Cannot estimate "what is this trade actually worth in expectation?" |
| **No uncertainty quantification** | Gates don't produce confidence intervals | Cannot distinguish "confident 0.55" from "uncertain 0.55" |
| **No OOD detection** | Gates don't detect distribution shift | Cannot downweight when market regime changes |
| **Static calibration** | Gate thresholds are configured once | Cannot adapt to evolving market conditions |
| **No learning from outcomes** | Gates don't improve from past mistakes | Repeatedly makes the same gate-level errors |

### 2.3 Real Example

Consider a SWING BTCUSDT 4h decision:

```
State: regime=HIGH_VOL_TRANSITION, anomaly_score=0.7, confidence=0.62,
       expected_R_long=0.8, spread=12bps, reconstruction_error=0.5

Gate check:
  confidence=0.62 >= min_confidence=0.55 → PASS
  expected_R_long=0.8 >= min_expected_r=0.5 → PASS
  spread=12bps <= max_spread=15bps → PASS
  regime=not blocked → PASS

Result: LONG_NOW executed with confidence 0.62
```

But a learned critic might notice:
- HIGH_VOL_TRANSITION regime + anomaly_score 0.7 → historically 40% win rate (vs 55% normal)
- reconstruction_error 0.5 → state is OOD (training mean was 0.1)
- Combined factors → expected value is actually -0.1R, not +0.8R

The critic recommends DOWNWEIGHT_CONFIDENCE to 0.3, which re-trips the confidence gate → NO_TRADE. Without the critic, the trade executes despite the risk.

## 3. Why RL Should NOT Be the Main Decision Engine

### 3.1 The Case Against RL as Primary Decision-Maker

1. **Financial data is low signal-to-noise**: RL needs consistent reward signals. Trading PnL is mostly noise.
2. **Non-stationarity**: Market regimes shift. An RL policy optimal in one regime may be catastrophic in another.
3. **Sample inefficiency**: Online RL would require thousands of losing trades to converge. Offline RL suffers from distribution shift.
4. **Reward hacking**: RL agents are extremely good at maximizing specified rewards in unintended ways (overtrading, regime cherry-picking, survivorship bias exploitation).
5. **Black-box risk**: You cannot formally verify that an RL policy respects all safety constraints.
6. **Trees beat deep RL on tabular data** (Grinsztajn et al. 2022): For the scale of data V7 will have (10^4-10^6 transitions), gradient-boosted trees outperform neural networks.
7. **Backtest overfitting** (Bailey & Lopez de Prado 2014): RL policies are especially prone to overfitting noise in financial data. DSR and PBO are mandatory.

### 3.2 Why Supervised (XGBoost) Is the Right Primary Engine

- Interpretable feature importance
- Robust to uninformative features
- Sample-efficient on tabular data
- Well-understood calibration (isotonic, Platt, beta)
- The AlphaForge design already commits to XGBoost

## 4. Why an Advisory Policy Critic Is Safer

### 4.1 Shield Architecture (Alshiekh et al. 2018)

The safe RL literature proves: learned components must sit UNDER deterministic, verified shields. V7 follows this exactly:

```
Runtime Risk Gate (deterministic) → SUPREME VETO
    ↑
Final Operational Gate (deterministic) → VETO
    ↑
V7 Policy Gates (deterministic) → VETO
    ↑
Policy Critic (learned, future) → ADVISORY ONLY
    ↑
AlphaForge Scorer (supervised) → PROPOSES
```

### 4.2 What "Advisory" Means in Practice

- The critic produces a **recommendation with evidence**, not a decision.
- V7 policy gates **enact** the critic's recommendation — the critic does not directly change any execution state.
- If the critic is unavailable or degraded, the system **continues unchanged** (safe degrade).
- The critic's verdict is **always visible** in `DecisionEvent.runtime_interpretation` — no hidden veto.

### 4.3 Why This Architecture Is Correct

1. **No single point of learned failure**: Even if the critic learns a terrible policy, gates block execution.
2. **Evidence-gated progression**: The critic must prove itself in shadow mode before any influence.
3. **Auditability**: Every critic decision is recorded with full lineage.
4. **Rollback safety**: The critic can be disabled per-mode or globally without architectural change.
5. **Compliance with safe RL theory**: Matches the shielding framework proven in Alshiekh et al. (2018) and Garcia & Fernandez (2015).

## 5. What Failure Modes Are Being Prevented?

| Failure Mode | Prevention Mechanism |
|---|---|
| **OOD overestimation** | IQL structurally prevents OOD action queries; CQL cross-check |
| **Conservative collapse** | τ ~0.7-0.8 (not 0.9); veto rate bounded away from 1 |
| **Regime overfitting** | Walk-forward validation; multi-regime coverage requirement |
| **Backtest overfitting** | DSR p<0.05 + PBO<0.10 mandatory before any transition |
| **Reward hacking** | Decomposable multi-component reward; hard gates outside RL |
| **Silent suppression** | Every verdict visible in runtime_interpretation |
| **Live authority creep** | Human approval required for ANY live influence |
| **Cost bypass** | Simulation engine is single economic truth; critic cannot compute alternative costs |
| **Survivorship bias** | Delisted/inactive assets included in training data |
| **Look-ahead leakage** | Strict temporal splits; purging + embargo |

## 6. What Is Out of Scope?

### 6.1 Permanently Out of Scope

- RL as the main decision engine
- Policy Critic opening or closing trades
- Policy Critic bypassing any gate
- New action enums or trading modes
- Autonomous live trading without human approval
- Replacing AlphaForge's alpha discovery role
- Replacing simulation's economic truth role

### 6.2 Out of Scope for This Docs Task

- Any implementation code
- Any runtime behavior changes
- Any test changes
- Contract registration (design sketch only)
- Replay buffer implementation

## 7. What Measurable Outcomes Define Success?

### 7.1 V1 (Rule-Based Shadow Critic)

| Metric | Target | Measurement |
|---|---|---|
| Shadow recording rate | 100% of scan decisions | `ShadowPolicyRepository` row count |
| NO_TRADE recommendation rate | > 0% and < 50% | Prevents both "never recommends NO_TRADE" and "always recommends NO_TRADE" |
| Runtime stability | Zero crashes in 30 days | Error logs |
| Audit trail completeness | Every decision has PolicyCriticReview | Repository query |

### 7.2 V2 (Supervised Critic)

| Metric | Target | Measurement |
|---|---|---|
| Expected value calibration | realized vs predicted r² > 0.1 | Held-out test split |
| DSR | p < 0.05 | Deflated Sharpe Ratio test |
| PBO | < 0.10 | CSCV procedure |
| Walk-forward consistency | ≥ 4/5 folds | WF-CV with purge + embargo |
| Champion anti-regression | No safety metric degradation vs V1 | Shadow comparison |

### 7.3 V3 (IQL Critic)

| Metric | Target | Measurement |
|---|---|---|
| FQE CI overlap | 95% CI overlaps observed performance | Fitted Q-Evaluation |
| Bellman error | Not monotonically increasing | Training monitoring |
| IQL/CQL disagreement rate | Bounded (not diverging) | Ensemble cross-check |
| All V2 metrics maintained | DSR, PBO, WF, anti-regression | Same procedures |

### 7.4 V4 (Constrained Optimizer)

| Metric | Target | Measurement |
|---|---|---|
| Shield compliance | 100% (zero violations) | Formal verification |
| Sizing proposal acceptance | Within gate bounds | Gate audit log |
| All V3 metrics maintained | FQE, DSR, PBO, WF, anti-regression | Same procedures |

### 7.5 Business Metrics (Phase 6)

| Metric | Target | Measurement |
|---|---|---|
| Net expectancy improvement | Positive vs baseline (DSR significant) | Shadow comparison over 90+ days |
| Drawdown profile | No worsening vs baseline | Max drawdown comparison |
| Regime-conditional performance | No single-regime degradation | Per-regime breakdown |
| Live shadow OPE vs realized | Approx equal | Ongoing comparison |
