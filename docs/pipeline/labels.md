# Pipeline Labels

**Intended path:** `docs/v7/pipeline/labels.md`

## Purpose

Defines how V7 converts simulation truth into normalized training and evaluation labels.

It answers:

> Given one simulated comparative outcome family, what supervised targets should later systems consume?

---

## In Scope

- market-first label generation
- long / short / no-trade comparative labels
- regret-aware labels
- path-quality-aware labels
- unresolved / invalid label handling
- ambiguity handling

---

## Out of Scope

- feature extraction
- dataset splitting
- model architecture
- runtime gating
- broker execution behavior

---

## Core Decision

V7 labels are derived from the **single simulation truth layer**, not from historical runtime actions.

That means:
- labels are market-first
- labels are cost-aware
- labels are comparative
- no-trade is first-class

Label horizons are `model_scope`-specific. Swing labels, scalp labels, and aggressive-scalp immediate-continuation labels are not interchangeable. Each `model_scope` chooses its own configured simulation/horizon profile through the shared simulation engine.

---

## Inputs

- simulation outputs from `pipeline/simulation.md`
- simulation family versions
- `model_scope`
- horizon family / `label_horizon_family`
- cost family
- slippage family
- comparative family rules

---

## Outputs

A normalized label record should minimally include:

- best action
- second-best action
- realized R for best action
- regret relative to best action
- no-trade correctness signals
- path quality family
- label validity status
- label interpretation version

---

## First-Phase Label Family

First phase should optimize for a compact action family:

- `LONG_NOW`
- `SHORT_NOW`
- `NO_TRADE`

Do **not** expand the action family aggressively in first phase.

Possible later timing variants such as:
- `WAIT_1_BAR_LONG`
- `WAIT_1_BAR_SHORT`

may exist in future comparative families, but are not first-phase authority.

---

## Rules

### 1. Do not learn runtime history as truth
A skipped live trade can still label as a high-quality long if the market path says so.

### 2. No unresolved labels
If simulation is unresolved, the label must stay unresolved.

### 3. No hidden hindsight leakage
Labels must only use the approved future window and simulation rules.

### 4. Comparative labels only
The system must know not only what was good, but what was better than alternatives.

### 5. No-trade is explicit
A correct no-trade must be labelable and evaluable.

### 6. Path matters
Clean +1R and chaotic +1R do not have to label identically if path quality rules say otherwise.

### 7. Scope-specific horizons
Do not use swing labels for `SCALP` model training, scalp labels for `SWING` model training, or either for `AGGRESSIVE_SCALP`. Aggressive scalp labels require stricter immediate-continuation / very-short-horizon and cost-aware semantics.

---

## Ambiguity Rule

V7 must support an explicit ambiguous label state.

### First-phase convention
If the gap between the best and second-best comparative actions is below the configured ambiguity threshold, emit:
- `label_validity = AMBIGUOUS`
- `best_action_label = AMBIGUOUS_STATE`

Do **not** force an artificial winner when the comparative gap is too small.

### Config requirement
The ambiguity threshold must be config-driven.
Recommended first-phase interpretation:
- compare best and second-best action quality in R-space
- use a small non-zero ambiguity margin

---

## Path Quality Buckets

First-phase path quality buckets:
- `HIGH`
- `MEDIUM`
- `LOW`

Default mapping uses `path_quality_score` from simulation:
- `HIGH` if `path_quality_score >= 0.70`
- `MEDIUM` if `0.40 <= path_quality_score < 0.70`
- `LOW` if `path_quality_score < 0.40`

These defaults are config-overridable but must remain versioned.

---

## `skip_was_correct` Rule

First-phase convention:
`skip_was_correct = true` when:
- `best_action_label = NO_TRADE`, or
- both directional actions fail to exceed the configured minimum acceptable realized-R threshold, or
- the saved-loss score exceeds the configured saved-loss threshold and no-trade is the preferred comparative outcome

This must remain config-driven and explicit.

---

## Timing Extension Policy

The result contract may expose:
- `entry_readiness`
- `entry_valid_for_bars`

These are **not first-phase learned primary targets**.

First phase policy:
- keep them advisory / derived
- measure them against later outcomes
- only promote them to learned targets with explicit evidence

This avoids unnecessary target explosion.

---

## Label Families

Recommended first-phase label outputs:
- `best_action_label`
- `counterfactual_best_action`
- `regret_r`
- `skip_was_correct`
- `saved_loss_score`
- `missed_opportunity_score`
- `path_quality_bucket`
- `label_validity`

Keep the label family compact and explicit.

---

## Failure / Fallback

If a state cannot produce a valid label:
- mark invalid
- preserve reason
- exclude from strict supervised training unless explicitly allowed by dataset config

No silent coercion.

---

## Config Surface

Key config families:
- label interpretation version
- regret thresholds
- no-trade correctness thresholds
- path quality thresholds
- ambiguity threshold
- invalid / ambiguous label filtering rules

---

## Interfaces

Upstream:
- `pipeline/simulation.md`

Downstream:
- `pipeline/dataset.md`
- `pipeline/evaluation.md`
- `contracts/trade_outcome.md`

---

## Test Requirements

Minimum label tests:
- correct best-action assignment
- correct no-trade assignment
- unresolved simulation yields unresolved label
- ambiguity threshold emits ambiguous label
- regret is consistent with comparative outcome
- path-quality buckets are deterministic
- `skip_was_correct` matches configured thresholds

---

## Final Position

Labels are not a substitute for outcomes.
They are one normalized interpretation of simulation truth for training and evaluation.
