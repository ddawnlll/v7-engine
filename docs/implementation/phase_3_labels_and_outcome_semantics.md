# Phase 3 — Hybrid Labels & Outcome Semantics (Planned)

**Status:** Planned  
**Owner:** Labels / lifecycle track  
**Last updated:** 2026-05-23  
**Delivery status:** Not started

---

## 1. Purpose

Convert runtime simulation outputs into the hybrid supervised target family used by V7 — **with mode-specific thresholds**.

This phase answers:

> What should the classifier learn, what should the regressors learn (per mode), and how do those targets align with later `TradeOutcome` records?

---

## 2. Stable Rules

- Labels are derived from simulation truth (mode-configured), not runtime action history.
- No-trade remains first-class.
- Unresolved and invalid simulation outputs do not enter strict supervised training.
- Ambiguous states remain explicit.
- Labels and outcomes must not contradict the simulation family.

---

## 3. Workstream A — Mode-Specific Classification Label Builder

The primary classification target is:

```python
best_action_label in {LONG_NOW, SHORT_NOW, NO_TRADE, AMBIGUOUS_STATE}
```

But thresholds are **mode-specific** (see mode-centric architecture section 4.2):

| Threshold | SWING | SCALP | AGGRESSIVE_SCALP |
|-----------|-------|-------|------------------|
| min_net_r_for_success | 0.75 | 0.20 | 0.10 |
| max_mae_r_for_success | -0.60 | -0.25 | -0.10 |
| ambiguity_gap_r | 0.20 | 0.10 | 0.05 |
| no_trade_default | False | False | True |

Derived fields:

- `second_best_action`
- `action_gap_r`
- `regret_r`
- `skip_was_correct`
- `saved_loss_score`
- `missed_opportunity_score`
- `path_quality_bucket`
- `label_validity`
- **`mode`** (SWING | SCALP | AGGRESSIVE_SCALP)

### Acceptance Criteria

- [ ] best-action label exists (per mode).
- [ ] no-trade correctness is explicit.
- [ ] regret outputs exist.
- [ ] ambiguous states are not forced into fake winners.
- [ ] mode-specific thresholds are applied correctly.

---

## 4. Workstream B — Mode-Specific Regression Target Builder

The regression target family supports economic-quality learning, **per mode**. Targets differ because success thresholds and holding horizons differ.

First-phase required targets:

```python
expected_r_target_long = realized_r_long  # mode-specific horizon
expected_r_target_short = realized_r_short  # mode-specific horizon
```

Recommended first-phase optional targets, if simulation outputs are stable enough:

```python
adverse_r_target_long = mae_r_long
adverse_r_target_short = mae_r_short
cost_adjusted_r_target_long = net_realized_r_long
cost_adjusted_r_target_short = net_realized_r_short
# SCALP and AGGRESSIVE_SCALP:
time_to_mfe_target_long
ime_to_mfe_target_short
# AGGRESSIVE_SCALP only:
instant_adverse_label
```

No-trade may expose review targets, but first phase should not force a no-trade regressor unless evaluation shows a need:

```python
no_trade_opportunity_cost_target
saved_loss_target
```

### Regression validity rules

- Directional regression targets are valid only when the corresponding simulated directional action is resolved.
- Invalid or unresolved directional outcomes must be marked invalid, not coerced to zero.
- Regression targets must preserve cost model and horizon lineage.

### Acceptance Criteria

- [ ] long and short expected-R regression targets exist (per mode).
- [ ] invalid/unresolved target rows are excluded or flagged by dataset rules.
- [ ] target lineage is preserved.
- [ ] mode-specific regression fields are present.

---

## 5. Workstream C — Mode-Specific Ambiguity & Path Quality

Default config values (per mode):

| Parameter | SWING | SCALP | AGGRESSIVE_SCALP |
|-----------|-------|-------|------------------|
| ambiguity_gap_r_threshold | 0.20 | 0.10 | 0.05 |
| path_quality_high_threshold | 0.70 | 0.70 | 0.70 |
| path_quality_medium_threshold | 0.40 | 0.40 | 0.40 |
| min_acceptable_directional_realized_r | 0.35 | 0.15 | 0.08 |

These are defaults, not permanent constants.

### Acceptance Criteria

- [ ] ambiguity threshold emits `AMBIGUOUS_STATE` (per mode).
- [ ] path-quality buckets are deterministic.
- [ ] `skip_was_correct` follows configured semantics.

---

## 6. Workstream D — TradeOutcome Alignment

`TradeOutcome` must later support comparison of:

- predicted action probabilities
- predicted expected-R values
- realized action/outcome
- realized R
- regret
- no-trade saved-loss / missed-opportunity evidence

Outcome helpers may include:

```python
outcome_label
is_good_decision
is_good_no_trade
realized_vs_projected_r_error
```

### Acceptance Criteria

- [ ] outcome interpretation helpers align with label semantics.
- [ ] projected-vs-realized R can be computed later.
- [ ] timing echo fields can be preserved without becoming primary targets.

---

## 7. Workstream E — Test Coverage

Minimum tests:

- best-action assignment
- no-trade correctness
- ambiguity threshold behavior
- long expected-R target creation
- short expected-R target creation
- unresolved simulation exclusion
- regression target lineage preservation
- path-quality bucket mapping
- regret consistency
- outcome alignment

---

## 8. Pre-Run Audit

Before Phase 4:

- [ ] no unresolved simulation becomes a valid training target
- [ ] ambiguous states are not silently forced into directional class labels
- [ ] regression targets are not filled with fake zero values
- [ ] labels consume runtime simulation adapter outputs only
- [ ] no label-only simulator exists

---

## 9. Definition of Done

- [ ] classification labels exist.
- [ ] expected-R regression targets exist.
- [ ] ambiguity and path quality are implemented.
- [ ] outcome semantics align with label truth.
- [ ] tests pass.

---

## 10. What Phase 4 Inherits

Phase 4 inherits a target family with both:

- classification target: `best_action_label`
- regression targets: long/short expected-R and approved risk/economic targets
