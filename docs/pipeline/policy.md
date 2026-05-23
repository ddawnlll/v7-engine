# Pipeline Policy — Regime-Aware, Mode-Centric

**Intended path:** `docs/v7/pipeline/policy.md`

## Purpose

Defines how V7 converts calibrated classification and regression surfaces into a normalized engine decision — **with regime-aware modifications and mode-specific thresholding**.

It answers:

> Given action probabilities and economic estimates for a specific mode, and the detected market regime, how should V7 decide between `LONG_NOW`, `SHORT_NOW`, and `NO_TRADE`?

---

## Core Decision

Policy is the stage where learned evidence becomes a decision.

Policy combines:

- calibrated action probabilities
- calibrated confidence
- expected R estimates
- adverse-pressure estimates
- cost-adjusted expectancy
- no-trade quality
- decision margins
- timing/refinement signals
- **regime context**

Runtime later decides whether execution is operationally allowed.

---

## Inputs

- calibrated classification surfaces
- regression economic surfaces
- confidence
- expected R
- expected adverse pressure / drawdown
- cost-adjusted expectancy
- decision margins
- timing-supporting fields
- **regime signal** (from rule-based regime detector)
- **mode identifier** (SWING | SCALP | AGGRESSIVE_SCALP)
- policy config

---

## Outputs

Policy produces fields matching `AnalysisResult`, including:

- `recommended_action`
- `is_actionable`
- `confidence`
- `confidence_kind`
- `expected_r`
- `expected_drawdown` or adverse pressure
- `action_probabilities`
- `economic_quality_by_action`
- `policy_reason_codes` (includes regime reason)
- `entry_price`
- `stop_loss`
- `take_profit`
- `time_sensitivity`
- optional `entry_readiness`
- optional `entry_valid_for_bars`

---

## Decision Gates

A directional action must pass:

1. probability/confidence gate
2. no-trade comparison gate
3. decision margin gate
4. expected-R gate
5. cost-adjusted expectancy gate
6. adverse-pressure/drawdown gate
7. **regime consistency gate**
8. degradation/fallback gate

If any required gate fails, policy selects `NO_TRADE` or degraded-safe behavior.

---

## Regime-Aware Policy Modifiers

Detected market regime modifies policy thresholds:

```python
REGIME_POLICY_MODIFIERS = {
    "TREND_UP": {
        "confidence_mult": 0.9,
        "expected_r_mult": 0.9,
        "allow_long": True,
        "allow_short": False,  # Don't fight the trend
    },
    "TREND_DOWN": {
        "confidence_mult": 0.9,
        "expected_r_mult": 0.9,
        "allow_long": False,
        "allow_short": True,
    },
    "RANGE": {
        "confidence_mult": 1.1,
        "expected_r_mult": 1.2,
        "allow_long": True,
        "allow_short": True,
    },
    "TRANSITION": {
        "confidence_mult": 1.3,
        "expected_r_mult": 1.5,
        "allow_long": True,
        "allow_short": True,
        "require_no_trade": True,  # Very high barrier
    },
}
```

When regime is `TRANSITION`, policy strongly prefers `NO_TRADE`.
When regime is `TREND_UP` or `TREND_DOWN`, policy blocks counter-trend directions.

---

## Tie-Break Rule

First-phase rule:

1. evaluate directional actions against gates (including regime)
2. if both fail, select `NO_TRADE`
3. if one passes and beats `NO_TRADE` by the configured margin, select it
4. if both pass, choose the better policy score after economic quality adjustment
5. if long/short are too close, select `NO_TRADE`

No-trade is a positive decision, not a weak fallback.

---

## Policy Score (Regime-Adjusted)

The first-phase policy score should be explicit and config-driven.

```text
policy_score(action, regime) =
  calibrated_action_probability_component
+ expected_r_component * regime.expected_r_mult
- adverse_pressure_component
- friction_component
+ path_quality_component
- uncertainty_penalty
- regime_penalty
```

The exact weights belong in config and must be versioned.

Do not create hidden selector complexity outside the policy module.

---

## Timing Extension Rule

`entry_readiness` and `entry_valid_for_bars` are policy-derived first phase.

They may use:

- refinement features (per mode)
- entry-zone distance
- local momentum pressure
- time-sensitivity heuristics
- margin decay signals if configured

They are advisory-first, not primary action targets.

---

## Failure / Fallback

If policy cannot safely produce a clean actionable decision:

- emit `NO_TRADE` or degraded-safe behavior
- preserve fallback/degradation visibility
- do not emit confident but structurally incomplete actions

---

## Config Surface

Key config families:

- minimum action probability
- minimum confidence
- minimum expected R
- minimum cost-adjusted expectancy
- drawdown/adverse-pressure limits
- no-trade thresholds
- policy score weights
- decision margin
- timing extension enablement
- degraded-result behavior
- **regime policy modifiers**

---

## Interfaces

Upstream:

- `pipeline/calibration.md`

Downstream:

- `pipeline/portfolio.md`
- `pipeline/risk.md`
- `contracts/analysis_result.md`

---

## Test Requirements

Minimum tests:

- long vs short vs no-trade selection
- confidence-only cannot pass when economic gate fails
- expected-R-only cannot pass when probability gate fails
- no-trade selected explicitly
- ambiguous long/short selects no-trade
- regression-head missingness degrades visibly
- timing fields are bounded and legal
- **regime modifiers applied correctly**
- **TRANSITION regime blocks directional trades**
- **counter-trend directions blocked in trend regimes**

---

## Final Position

Policy is where V7 becomes profitability-aware and regime-aware. It must use classification, regression, regime, and mode context together, while staying explicit, compact, and auditable.
