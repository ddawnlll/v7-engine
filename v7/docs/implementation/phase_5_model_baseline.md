# Phase 5 — XGBoost Hybrid Model Baseline (Planned)

**Status:** Planned  
**Owner:** Model training track  
**Last updated:** 2026-05-23  
**Delivery status:** Not started

---

## 1. Purpose

Train the first V7 hybrid model baseline **per mode scope** and publish candidate artifacts.

This phase proves that V7 can train compact, shared (within mode), scope-compatible, multi-symbol model families that produce both action probabilities and economic-quality estimates — independently for SWING, SCALP, and AGGRESSIVE_SCALP.

---

## 2. Stable Rules

- First-phase model family is XGBoost-first per mode.
- Do not begin with large deep architectures.
- Do not create one model per symbol in first phase.
- Do not train one universal artifact across incompatible `model_scope` values.
- Phase 5 produces candidate artifacts only, not live authority.
- Model training consumes datasets (mode-specific). It does not run simulation.

---

## 3. Workstream A — Mode-Specific Hybrid Baseline Trainer

### First implementation model suite

Use **one artifact bundle per activated `model_scope`**.

```
model_artifact_bundles/
  swing/
    action_classifier.pkl
    expected_r_long_regressor.pkl
    expected_r_short_regressor.pkl
    metadata.json
  scalp/
    action_classifier.pkl
    expected_r_long_regressor.pkl
    expected_r_short_regressor.pkl
    metadata.json
  aggressive_scalp/
    action_classifier.pkl
    expected_r_long_regressor.pkl
    expected_r_short_regressor.pkl
    metadata.json
```

Default first baseline inside each scope:

1. **Action classifier**
   - XGBoost multiclass classifier
   - target: `best_action_label` (mode-specific labels)
   - classes: `LONG_NOW`, `SHORT_NOW`, `NO_TRADE`
   - output: `action_probabilities`

2. **Long expected-R regressor**
   - XGBoost regressor
   - target: `expected_r_target_long` (mode-specific horizon)
   - output: `expected_r_long`

3. **Short expected-R regressor**
   - XGBoost regressor
   - target: `expected_r_target_short` (mode-specific horizon)
   - output: `expected_r_short`

Optional first-phase regressors only if target quality is adequate:

- long/short adverse-R regressors
- long/short cost-adjusted-R regressors
- time-to-MFE regressors (SCALP, AGGRESSIVE_SCALP)

### Explicit non-goals

- Do not start with three unrelated binary classifiers.
- Do not make regression the only decision source.
- Do not let expected-R regressors directly bypass policy.
- Do not bundle incompatible scopes in one model.
- Do not train SWING/SCALP/AGGRESSIVE_SCALP together.

### Implementation Tasks

- [ ] Implement hybrid trainer entrypoint (per mode).
- [ ] Train multiclass action classifier (per mode).
- [ ] Train long expected-R regressor (per mode).
- [ ] Train short expected-R regressor (per mode).
- [ ] Support target validity masks.
- [ ] Support sample weights.
- [ ] Emit model-suite metadata and lineage, including `model_scope`.

### Acceptance Criteria

- [ ] action classifier trains successfully (per mode).
- [ ] long/short expected-R regressors train successfully (per mode).
- [ ] artifact bundle loads for inference.
- [ ] metadata preserves dataset, feature, label, simulation lineage, and mode scope.

---

## 4. Workstream B — Reproducibility & Early Stopping

Default early stopping metrics:

- classifier: `mlogloss`
- expected-R regressors: `rmse`

Required hyperparameter surfaces:

- `max_depth`
- `n_estimators`
- `learning_rate`
- `min_child_weight`
- `subsample`
- `colsample_bytree`
- `reg_alpha`
- `reg_lambda`
- `early_stopping_rounds`
- objective/metric by head

### Acceptance Criteria

- [ ] fixed seed behavior is traceable.
- [ ] early stopping works per head.
- [ ] hyperparameters are config-driven.

---

## 5. Workstream C — Candidate Artifact Publishing

Artifact bundle should include:

```python
model_scope
action_classifier_artifact
expected_r_long_regressor_artifact
expected_r_short_regressor_artifact
optional_risk_regressor_artifacts
feature_schema_version
label_interpretation_version
simulation_profile_version
training_dataset_version
head_metrics
training_run_id
status = "candidate"
promotable = False
```

Publishing rule:

- Phase 5 may publish a candidate artifact bundle.
- Phase 8 may mark it evaluation-promotable.
- Phase 9 may mark it live-eligible.

### Acceptance Criteria

- [ ] successful training creates candidate artifacts only.
- [ ] failed training does not publish promotable state.
- [ ] publish vs promote is visible.

---

## 6. Workstream D — Test Coverage

Minimum tests:

- small training run completes
- artifact bundle loads
- inference over sample rows works
- classifier probabilities exist
- long expected-R output exists
- short expected-R output exists
- target validity masks are respected
- early stopping path works
- fixed-seed sanity test
- failed run does not publish promotable state

---

## 7. Pre-Run Audit

Before first real candidate training:

- [ ] dataset family version is recorded
- [ ] unresolved/invalid rows were excluded or masked correctly
- [ ] regression target validity masks are present
- [ ] model training path does not call simulation or live execution
- [ ] required hyperparameter surfaces exist
- [ ] latency targets are recorded

Recommended first implementation latency targets:

- atomic inference p95 <= 50 ms on target serving worker
- 60-symbol scan p95 <= 5 s on target serving worker

---

## 8. Definition of Done

- [ ] hybrid trainer exists.
- [ ] classifier and regressors train.
- [ ] candidate artifact bundle exists.
- [ ] output strategy is explicit.
- [ ] tests pass.

---

## 9. What Phase 6 Inherits

Phase 6 inherits a candidate bundle with raw action probabilities and raw expected-R surfaces that must be calibrated, reliability-reviewed, and policy-wrapped before runtime use.
