# Pipeline Labels

**Intended path:** `docs/v7/pipeline/labels.md`

## Purpose

Defines how V7 converts simulation truth into normalized supervised targets.

It answers:

> Given one simulated comparative outcome family, what classification and regression targets should the model consume?

---

## Core Decision

V7 labels are derived from the single simulation truth layer.

The first-phase label design is explicitly **hybrid**:

- classification labels define action preference
- regression labels define economic quality and risk

Labels are market-first, cost-aware, comparative, and no-trade aware.

---

## Inputs

- comparative simulation output
- simulation-family version
- horizon family
- cost family
- path-quality family
- label interpretation config

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

The action with the best net economic outcome after costs, subject to ambiguity rules.

### `long_success_label`

A binary or ternary target describing whether the long outcome clears the configured minimum acceptable R and path-quality thresholds.

### `short_success_label`

Same as long, but for short.

### `no_trade_quality_label`

Labels no-trade as correct, missed opportunity, saved loss, or ambiguous depending on comparative outcomes.

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

If the gap between the best and second-best action is below the configured ambiguity threshold:

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
- both directional actions fail the minimum acceptable realized-R threshold, or
- saved-loss score exceeds the configured threshold and no-trade is preferred

---

## Config Surface

Key config families:

- label interpretation version
- minimum acceptable R
- ambiguity threshold
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

- best-action assignment
- long/short success labels
- no-trade quality labels
- regression R targets match simulation output
- cost-adjusted R targets match cost model
- unresolved simulation yields unresolved label
- ambiguity threshold emits ambiguous label
- invalid rows preserve invalidity reason

---

## Final Position

Labels are not the model and not the outcome itself. They are one versioned interpretation of simulation truth for supervised learning. In V7, they must support both action classification and economic regression.
