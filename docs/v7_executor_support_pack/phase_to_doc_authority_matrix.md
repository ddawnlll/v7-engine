# V7 Phase-to-Doc Authority Matrix

## Purpose

This document maps each implementation phase to the primary authority docs it must follow.

It answers:

> For any phase, which docs are authoritative, which docs are secondary, and which docs should only be consulted for context?

Use the most specific relevant authority first.

---

## Priority Order Rule

For any implementation task inside a phase, use this order:

1. the phase plan itself
2. the most specific matching V7 authority doc
3. the related contract doc if lifecycle objects are involved
4. runtime or pipeline docs for integration behavior
5. root docs for high-level direction only

Root docs do not override specific contract or phase semantics.

---

## Phase 0 — Repo Alignment & Foundations

### Primary authority
- `implementation/phase_0_repo_alignment_and_foundations.md`
- `v7_llm_rules.md`
- `v7_doc_writing_guide.md`

### Secondary authority
- `README.md`
- `architecture.md`

### Context only
- pipeline docs
- contract docs

### Notes
Phase 0 may inspect all docs, but it should not invent new semantics for contracts or pipeline behavior.

---

## Phase 1 — Contracts & Validation

### Primary authority
- `implementation/phase_1_contracts_and_validation.md`
- `contracts/README.md`
- `contracts/analysis_request.md`
- `contracts/analysis_result.md`
- `contracts/decision_event.md`
- `contracts/trade_outcome.md`

### Secondary authority
- `runtime/runtime_integration.md`

### Context only
- pipeline docs

### Notes
When request/result/event/outcome fields disagree with a generic runtime assumption, contracts win.

---

## Phase 2 — Simulation Truth Layer

### Primary authority
- `implementation/phase_2_simulation_truth_layer.md`
- `pipeline/simulation.md`

### Secondary authority
- `contracts/trade_outcome.md`
- `pipeline/labels.md`
- `pipeline/evaluation.md`

### Context only
- `runtime/runtime_integration.md`

### Notes
This phase defines economic truth.
Runtime behavior must not silently replace simulation truth.

---

## Phase 3 — Labels & Outcome Semantics

### Primary authority
- `implementation/phase_3_labels_and_outcome_semantics.md`
- `pipeline/labels.md`
- `contracts/trade_outcome.md`

### Secondary authority
- `pipeline/simulation.md`
- `pipeline/evaluation.md`

### Context only
- model and runtime docs

### Notes
If label logic conflicts with later training convenience, label truth wins.

---

## Phase 4 — Features & Dataset

### Primary authority
- `implementation/phase_4_features_and_dataset.md`
- `pipeline/features.md`
- `pipeline/dataset.md`

### Secondary authority
- `contracts/analysis_request.md`
- `pipeline/labels.md`

### Context only
- model and runtime docs

### Notes
Feature/dataset correctness is upstream of model convenience.

---

## Phase 5 — Model Baseline

### Primary authority
- `implementation/phase_5_model_baseline.md`
- `pipeline/model.md`

### Secondary authority
- `pipeline/dataset.md`
- `pipeline/features.md`

### Context only
- runtime docs

### Notes
Phase 5 creates candidates only.
It does not grant promotion or live authority.

---

## Phase 6 — Calibration & Policy

### Primary authority
- `implementation/phase_6_calibration_and_policy.md`
- `pipeline/calibration.md`
- `pipeline/policy.md`
- `contracts/analysis_result.md`

### Secondary authority
- `pipeline/evaluation.md`
- `pipeline/monitoring.md`

### Context only
- runtime docs except where result shape matters

### Notes
If policy shape conflicts with raw model convenience, policy/result contract wins.

---

## Phase 7 — Portfolio, Risk & Runtime Integration

### Primary authority
- `implementation/phase_7_portfolio_risk_and_runtime_integration.md`
- `runtime/runtime_integration.md`
- `pipeline/portfolio.md`
- `pipeline/risk.md`

### Secondary authority
- `runtime/fallback_policy.md`
- `contracts/decision_event.md`
- `contracts/trade_outcome.md`

### Context only
- root summary docs

### Notes
This is the highest-risk phase for authority drift.
Always prefer runtime integration + phase plan over memory or shorthand.

---

## Phase 8 — Evaluation & Monitoring

### Primary authority
- `implementation/phase_8_evaluation_and_monitoring.md`
- `pipeline/evaluation.md`
- `pipeline/monitoring.md`

### Secondary authority
- `pipeline/calibration.md`
- `pipeline/policy.md`
- `contracts/trade_outcome.md`

### Context only
- release docs

### Notes
Evaluation owns candidate-vs-baseline evidence.
It does not by itself grant live authority.

---

## Phase 9 — Deployment Safety & Release Readiness

### Primary authority
- `implementation/phase_9_deployment_safety_and_release.md`
- `runtime/deployment_safety.md`
- `runtime/fallback_policy.md`

### Secondary authority
- `pipeline/monitoring.md`
- `pipeline/evaluation.md`
- `runtime/runtime_integration.md`

### Context only
- root summary docs

### Notes
Release authority and rollout safety live here.
Do not let Phase 5 or Phase 8 silently absorb Phase 9 ownership.

---

## Cross-Cutting Authority Map

### Config decisions
Primary:
- current repo config implementation
- phase plan config sections
- relevant stage doc

### Naming/path decisions
Primary:
- `README.md`
- `v7_doc_writing_guide.md`
- `implementation/master_plan.md`
- `implementation/naming_and_path_consistency.md` if present

### LLM execution behavior
Primary:
- `v7_llm_rules.md`

---

## Final Position

The phase plan tells you what to build now.
The most specific V7 authority doc tells you what it must mean.
That separation should stay intact.
