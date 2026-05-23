# Phase 4 — Features & Hybrid Dataset (Planned)

**Status:** Planned  
**Owner:** Data / training-input track  
**Last updated:** 2026-05-23  
**Delivery status:** Not started

---

## 1. Purpose

Turn canonical state and hybrid labels into leakage-safe feature rows and walk-forward dataset families — **with mode awareness**.

This phase earns the right to train by proving rows are temporally valid, target-valid, scope-valid, and lineage-valid.

---

## 2. Stable Rules

- Features come from canonical state only (shared across modes).
- No future leakage.
- Unresolved/invalid targets stay out of strict training by default.
- Dataset rows preserve feature, label, simulation, model-scope, and **mode** lineage.
- **Datasets are mode-specific** — do not mix modes in one dataset family.
- Datasets do not call live exchange, broker, or mutable runtime account paths.

---

## 3. Workstream A — Feature Builder (Shared Across Modes)

Feature groups (computed from canonical state, consumed by all modes):

- Primary decision features (per mode interval: 4h/1h/15m)
- Higher-timeframe context features (per mode)
- Refinement/timing context features (per mode)
- symbol identity and metadata features
- regime/volatility features
- missingness/degradation flags

First phase uses one fused row per evaluated market state, not separate averaged interval predictors.

Features are built once and shared. Labels are mode-specific.

### Acceptance Criteria

- [ ] grouped feature surfaces exist.
- [ ] HTF/refinement missingness is explicit.
- [ ] symbol encoding is stable and versioned.
- [ ] same feature row can feed all three mode pipelines.

---

## 4. Workstream B — Normalization & Schema Stability

Normalization rule:

- fit normalization statistics on the training window only
- apply those statistics to that fold's validation/calibration/holdout rows
- fit separately per walk-forward fold
- do not reuse fold statistics across folds unless explicitly versioned

### Acceptance Criteria

- [ ] normalization uses training-only statistics.
- [ ] feature schema version is attached.
- [ ] incompatible schemas fail clearly.

---

## 5. Workstream C — Hybrid Dataset Assembly

Each row should include:

```python
row_id
symbol
model_scope
primary_interval
context_intervals
refinement_intervals
state_timestamp_utc
feature_schema_version
label_interpretation_version
simulation_profile_version
cost_model_version
slippage_model_version
horizon_family
simulation_run_id
replay_run_id
monte_carlo_run_id  # when configured
dataset_family_version
```

Target fields:

```python
classification_target = best_action_label
classification_target_validity
expected_r_target_long
expected_r_target_short
expected_r_target_long_validity
expected_r_target_short_validity
adverse_r_target_long       # optional if enabled
adverse_r_target_short      # optional if enabled
cost_adjusted_r_target_long # optional if enabled
cost_adjusted_r_target_short# optional if enabled
sample_weight
symbol_weight
```

### Target completeness rule

A row can be valid for classification but invalid for one regression target. Training export must preserve per-target validity rather than silently dropping or filling values.

### Scope rule

Do not mix `model_scope`, primary clock, or label horizon inside one supervised dataset family unless a documented multi-scope training mode explicitly exists. First phase assumes scope-compatible datasets (one dataset per mode).

### Mode field

Each dataset row includes `mode` (SWING | SCALP | AGGRESSIVE_SCALP) as a first-class field. This ensures traceability even when datasets are stored independently.

### Acceptance Criteria

- [ ] dataset rows carry classification and regression targets (mode-specific).
- [ ] mode field is populated correctly.
- [ ] target validity is per-target and explicit.
- [ ] lineage is preserved.

---

## 6. Workstream D — Splits and Symbol Balancing

Default walk-forward settings:

- `fold_count = 6`
- `min_train_window = 12m`
- `validation_window = 2m`
- `holdout_window = 1m`

Balancing default:

- inverse-frequency sample weights by symbol
- cap max relative symbol weight ratio at `5.0`
- use hard row caps only if weighting fails to prevent pathological dominance

### Acceptance Criteria

- [ ] folds are reproducible.
- [ ] no random temporal leakage.
- [ ] symbol weighting is reproducible.

---

## 7. Workstream E — Test Coverage

Minimum tests:

- no future leakage
- HTF/refinement fallback + missing flags
- symbol encoding stability
- training-only normalization fit
- per-fold normalization separation
- schema mismatch failure
- walk-forward split integrity
- unresolved row exclusion
- per-target validity handling
- symbol-weight reproducibility

---

## 8. Pre-Run Audit

Before Phase 5:

- [ ] features use canonical state only
- [ ] dataset rows preserve simulation adapter lineage
- [ ] regression targets are not fake-filled
- [ ] target validity masks are present
- [ ] no single symbol dominates rows or weights silently
- [ ] dataset assembly has no live execution side effects

---

## 9. Definition of Done

- [ ] feature builder exists.
- [ ] normalization is training-only and per-fold.
- [ ] hybrid dataset rows exist.
- [ ] target validity is explicit.
- [ ] walk-forward folds exist.
- [ ] tests pass.

---

## 10. What Phase 5 Inherits

Phase 5 inherits training-ready rows with feature matrices, class targets, expected-R regression targets, validity masks, and sample weights.
