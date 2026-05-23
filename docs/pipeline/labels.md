# Pipeline Labels — Mode-Centric

**Intended path:** `docs/v7/pipeline/labels.md`

## Purpose

Defines how V7 converts simulation truth into normalized supervised targets — **parameterized per trading mode**.

It answers:

> Given one simulated comparative outcome family for a specific mode, what classification and regression targets should the model consume?

---

## Core Decision

V7 labels are derived from the simulation truth layer **configured per mode**.
The first-phase label design is explicitly **hybrid** and **mode-aware**:

- classification labels define action preference (mode-specific thresholds)
- regression labels define economic quality and risk (mode-specific)

Labels are market-first, cost-aware, comparative, and no-trade aware. **The same timestamp produces different label truths for SWING, SCALP, and AGGRESSIVE_SCALP.**

---

## Inputs

- comparative simulation output (mode-configured)
- mode identifier (SWING | SCALP | AGGRESSIVE_SCALP)
- simulation-family version
- horizon family (mode-specific)
- cost family
- path-quality family
- label interpretation config (mode-specific)
- optional regime signal for extended labels

---

## Outputs

A normalized label record should include:

### Classification label fields

- `best_action_label`
- `second_best_action_label`
- `long_success_label`
- `short_success_label`
- `no_trade_quality_label`
- `skip_was_correct`
- `label_validity`
- `ambiguity_reason`

### Regression label fields

- `long_realized_r_net`
- `short_realized_r_net`
- `long_realized_r_gross`
- `short_realized_r_gross`
- `long_cost_r`
- `short_cost_r`
- `long_mae_r`
- `short_mae_r`
- `long_mfe_r`
- `short_mfe_r`
- `regret_r`
- `saved_loss_score`
- `missed_opportunity_score`
- `path_quality_score`

### Mode-specific fields

- `mode` (SWING | SCALP | AGGRESSIVE_SCALP)
- `primary_interval`
- For SCALP and AGGRESSIVE_SCALP:
  - `long_time_to_mfe_bars` (optional)
  - `short_time_to_mfe_bars` (optional)
  - `long_exit_efficiency` (optional)
  - `short_exit_efficiency` (optional)
- For AGGRESSIVE_SCALP only:
  - `instant_adverse_label` (optional)

### Regime context fields (extended labels)

- `regime` (TREND_UP | TREND_DOWN | RANGE | TRANSITION)
- `regime_confidence`
- `regime_transition_risk`

### Lineage fields

- `label_interpretation_version`
- `simulation_family_version`
- `cost_model_version`
- `horizon_family_version`

---

## First-Phase Action Family

- `LONG_NOW`
- `SHORT_NOW`
- `NO_TRADE`

Do not expand the first-phase primary action family with wait/scale/exit actions.

Timing fields may be derived for analysis, but they are not first-phase primary learned targets.

---

## Classification Label Semantics

### `best_action_label`

The action with the best net economic outcome after costs, subject to ambiguity rules — **computed per mode**.

### `long_success_label`

A binary or ternary target describing whether the long outcome clears the **mode-specific** minimum acceptable R and path-quality thresholds.

### `short_success_label`

Same as long, but for short.

### `no_trade_quality_label`

Labels no-trade as correct, missed opportunity, saved loss, or ambiguous depending on comparative outcomes.

---

## Mode-Specific Success Thresholds

```python
SUCCESS_THRESHOLDS = {
    "SWING": {
        "min_net_r_for_success": 0.75,
        "max_mae_r_for_success": -0.60,
        "min_mfe_r_for_good_exit": 1.0,
        "allow_no_trade_on_ambiguity": False,
    },
    "SCALP": {
        "min_net_r_for_success": 0.20,
        "max_mae_r_for_success": -0.25,
        "min_cost_adjusted_expectancy": 0.10,
        "allow_no_trade_on_ambiguity": True,
    },
    "AGGRESSIVE_SCALP": {
        "min_net_r_for_success": 0.10,
        "max_mae_r_for_success": -0.10,
        "max_time_to_mfe_bars": 3,
        "instant_adverse_threshold": -0.05,
        "no_trade_default": True,
    },
}
```

---

## Utility Function for Best Action

Each mode uses different weights for MAE, cost, and time when selecting the best action:

```python
def calculate_action_utility(action, labels, mode):
    weights = {
        "SWING": {"mae": 1.0, "cost": 1.0, "time": 0.3},
        "SCALP": {"mae": 2.0, "cost": 2.0, "time": 1.5},
        "AGGRESSIVE_SCALP": {"mae": 3.0, "cost": 3.0, "time": 2.5},
    }
    w = weights[mode]
    if action == "LONG_NOW":
        return (
            labels.long_realized_r_net
            - w["mae"] * abs(labels.long_mae_r)
            - w["cost"] * labels.long_cost_r
            - w["time"] * (labels.long_time_to_mfe_bars or 0) * 0.1
        )
    elif action == "SHORT_NOW":
        return (
            labels.short_realized_r_net
            - w["mae"] * abs(labels.short_mae_r)
            - w["cost"] * labels.short_cost_r
            - w["time"] * (labels.short_time_to_mfe_bars or 0) * 0.1
        )
    else:  # NO_TRADE
        return labels.saved_loss_score
```

---

## Regression Label Semantics

Regression labels are not optional decoration. They are first-class profitability targets.

They allow the model to learn:

- how much a long may be worth
- how much a short may be worth
- how bad adverse movement may be
- how much cost erodes expectancy
- whether no-trade avoided loss or missed opportunity

Regression labels should be used by model heads, evaluation, and policy gates.

---

## Ambiguity Rule

If the gap between the best and second-best action is below the configured ambiguity threshold (**mode-specific**):

- set `label_validity = AMBIGUOUS`
- set `best_action_label = AMBIGUOUS_STATE`
- preserve regression targets if valid
- exclude from strict action-classification training by default unless config explicitly allows soft-label use

Do not force artificial action winners.

---

## Unresolved / Invalid Rule

If simulation is unresolved:

- label remains unresolved
- strict supervised training excludes the row

If simulation is invalidated:

- label is invalid
- invalidity reason is preserved
- strict supervised training excludes the row

No silent coercion.

---

## Path Quality Buckets

First-phase buckets:

- `HIGH`
- `MEDIUM`
- `LOW`

Default mapping:

- `HIGH` if `path_quality_score >= 0.70`
- `MEDIUM` if `0.40 <= path_quality_score < 0.70`
- `LOW` if `path_quality_score < 0.40`

Thresholds are config-driven and versioned.

---

## `skip_was_correct` Rule

`skip_was_correct = true` when:

- best action is `NO_TRADE`, or
- both directional actions fail the mode-specific minimum acceptable realized-R threshold, or
- saved-loss score exceeds the configured threshold and no-trade is preferred

---

## Config Surface

Key config families:

- label interpretation version
- mode-specific minimum acceptable R
- mode-specific ambiguity threshold
- no-trade correctness thresholds
- saved-loss threshold
- missed-opportunity threshold
- path-quality thresholds
- invalid/ambiguous filtering policy
- regression target clipping policy

---

## Interfaces

Upstream:

- `pipeline/simulation.md`

Downstream:

- `pipeline/dataset.md`
- `pipeline/model.md`
- `pipeline/evaluation.md`
- `contracts/trade_outcome.md`

---

## Test Requirements

Minimum tests:

- best-action assignment (per mode)
- long/short success labels (mode-specific thresholds)
- no-trade quality labels
- regression R targets match simulation output
- cost-adjusted R targets match cost model
- unresolved simulation yields unresolved label
- ambiguity threshold emits ambiguous label (mode-specific)
- invalid rows preserve invalidity reason
- mode-specific fields are populated correctly

---

## Final Position

Labels are not the model and not the outcome itself. They are one versioned interpretation of simulation truth for supervised learning. In V7, they must support both action classification and economic regression — with mode-specific thresholds and semantics.
