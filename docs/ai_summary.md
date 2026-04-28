# V7 AI Summary

## Purpose

This is the compact authoritative summary of V7 for AI-assisted implementation.

It answers:

> If an LLM reads only one summary before opening the detailed docs, what must it know about V7?

This file is intentionally shorter than the authority docs.
It does not replace them.

---

## V7 In One Page

V7 is a centralized, market-first, simulation-native trading system designed to be:

- economically honest
- multi-symbol aware
- contract-first
- calibration-aware
- explicit about runtime vs engine ownership
- easy for humans and LLMs to edit safely
- driven by one simulation truth layer
- controlled through one unified config surface
- built on one shared training platform with separate `model_scope` artifacts for `SWING`, `SCALP`, and `AGGRESSIVE_SCALP`

V7 is not a greenfield reset.
It is a disciplined consolidation of the strongest V6 ideas.

---

## Authority Map

If you need the main authority docs, read them in this order:

1. `vision.md` — strategy and success definition
2. `architecture.md` — system shape and ownership boundaries
3. `contracts/README.md` — contract family strategy
4. `contracts/analysis_request.md` — runtime-to-engine input
5. `contracts/analysis_result.md` — engine-to-runtime output
6. `contracts/decision_event.md` — normalized lifecycle record
7. `contracts/trade_outcome.md` — normalized consequence record
8. `runtime/runtime_integration.md` — runtime boundary behavior
9. `runtime/fallback_policy.md` — allowed degradation and fallback
10. `runtime/deployment_safety.md` — rollout and live-safety gates
11. `pipeline/training.md` — shared training platform and model-scope strategy
12. `pipeline/simulation.md` — simulation truth layer
13. `pipeline/labels.md` — label semantics
14. `pipeline/features.md` — canonical-state feature semantics
15. `pipeline/dataset.md` — dataset lineage and splits
16. `pipeline/model.md` — first-phase model family
17. `pipeline/calibration.md` — calibrated confidence surfaces
18. `pipeline/policy.md` — decision policy
19. `pipeline/portfolio.md` — cross-symbol portfolio handling
20. `pipeline/risk.md` — hard and soft risk gates
21. `pipeline/evaluation.md` — promotion evidence
22. `pipeline/monitoring.md` — post-deploy health and drift
23. `v7_llm_rules.md` — LLM working rules
24. `v7_doc_writing_guide.md` — doc-writing rules
25. `roadmap.md` — implementation order

---

## Repository Filemap

Current repo shape is docs-first.
There is no production `src/` tree yet in the current repository state.
The implementation plans expect `src/v7/` to be created later in Phase 0.

### Root docs
- `docs/README.md` — main navigation
- `docs/ai_summary.md` — compact summary + filemap
- `docs/vision.md` — strategy and success definition
- `docs/architecture.md` — system shape and ownership boundaries
- `docs/roadmap.md` — phased implementation order
- `docs/v7_llm_rules.md` — LLM working rules
- `docs/v7_doc_writing_guide.md` — doc-writing rules

### Contract docs
- `docs/contracts/README.md` — contract family strategy
- `docs/contracts/analysis_request.md` — runtime-to-engine input
- `docs/contracts/analysis_result.md` — engine-to-runtime output
- `docs/contracts/decision_event.md` — normalized lifecycle record
- `docs/contracts/trade_outcome.md` — normalized consequence record

### Runtime docs
- `docs/runtime/runtime_integration.md` — runtime boundary behavior
- `docs/runtime/fallback_policy.md` — allowed degradation and fallback
- `docs/runtime/deployment_safety.md` — rollout and live-safety gates

### Pipeline docs
- `docs/pipeline/simulation.md` — truth layer
- `docs/pipeline/training.md` — shared training platform and model-scope strategy
- `docs/pipeline/labels.md` — label semantics
- `docs/pipeline/features.md` — canonical-state features
- `docs/pipeline/dataset.md` — dataset lineage and splits
- `docs/pipeline/model.md` — first-phase model family
- `docs/pipeline/calibration.md` — calibrated confidence
- `docs/pipeline/policy.md` — decision policy
- `docs/pipeline/portfolio.md` — cross-symbol portfolio handling
- `docs/pipeline/risk.md` — hard and soft risk gates
- `docs/pipeline/evaluation.md` — promotion evidence
- `docs/pipeline/monitoring.md` — health and drift

### Implementation docs
- `docs/implementation/master_plan.md` — master sequencing authority
- `docs/implementation/phase_0_repo_alignment_and_foundations.md` — repo bootstrap
- `docs/implementation/phase_1_contracts_and_validation.md` — typed contracts
- `docs/implementation/phase_2_simulation_truth_layer.md` — simulation truth
- `docs/implementation/phase_3_labels_and_outcome_semantics.md` — labels and outcomes
- `docs/implementation/phase_4_features_and_dataset.md` — features and dataset
- `docs/implementation/phase_5_model_baseline.md` — baseline model
- `docs/implementation/phase_6_calibration_and_policy.md` — calibration and policy
- `docs/implementation/phase_7_portfolio_risk_and_runtime_integration.md` — portfolio/risk/runtime integration
- `docs/implementation/phase_8_evaluation_and_monitoring.md` — evaluation and monitoring
- `docs/implementation/phase_9_deployment_safety_and_release.md` — deployment safety and release

### Execution support pack
- `docs/v7_executor_support_pack/executor_prompt_pack.md` — short executor prompts
- `docs/v7_executor_support_pack/naming_and_path_consistency.md` — canonical naming and paths
- `docs/v7_executor_support_pack/phase_to_doc_authority_matrix.md` — phase-to-doc authority map

---

## Core System Shape

V7 is built as a layered system:

- raw market data
- canonical state construction
- one simulation truth layer
- label and feature generation per `model_scope`
- dataset assembly per `model_scope`
- model training through shared infrastructure with separate scope artifacts
- calibration
- policy
- portfolio interpretation
- risk gating
- runtime integration
- monitoring and deployment safety

The architecture is intentionally smaller and more centralized than V6.

---

## Contract Family

V7 has one atomic lifecycle contract family:

- `AnalysisRequest`
- `AnalysisResult`
- `DecisionEvent`
- `TradeOutcome`

### Ownership split
- request/result are engine-facing
- event/outcome are system-facing

### Semantic rule
- one symbol
- one `model_scope`
- one `requested_trade_mode`
- one primary interval
- one evaluated market state
- one request
- one result
- one event
- one outcome

### Contract strategy rule
Batch/session grouping may exist above the atomic family, but it must not break atomic auditability.

### What the contracts must preserve
- explicit lineage
- replay/live comparability
- degradation visibility
- versioned meaning
- no hidden deterministic vetoes
- no giant payload duplication in event/outcome objects

---

## First-Phase Defaults

Treat these as the default V7 operating assumptions unless a more specific authority doc says otherwise:

- target universe up to **60 symbols**
- initial rollout may use a smaller approved subset
- one shared training platform, not one universal model
- model scopes: `SWING`, `SCALP`, `AGGRESSIVE_SCALP`
- `SWING`: `primary_interval` **4h**, `context_intervals` **1d**, `refinement_intervals` **1h**
- `SCALP`: `primary_interval` **15m**, `context_intervals` **1h**, `refinement_intervals` **5m**
- `AGGRESSIVE_SCALP`: `primary_interval` **1m** or **3m**, `context_intervals` **5m + 15m**
- shared simulation core reused by runtime and replay with scope-specific profiles
- first-phase model algorithm family: **XGBoost-first** inside scope-specific artifacts
- first-phase calibration: **global within scope**
- timing extension fields:
  - `entry_readiness`
  - `entry_valid_for_bars`
- timing extension is advisory-first in normal operation
- runtime integration is incremental, not rewrite-first

---

## Simulation Truth Layer

`pipeline/simulation.md` is the economic truth layer.

It defines how V7 should compare:

- `LONG_NOW`
- `SHORT_NOW`
- `NO_TRADE`

under the same cost-aware rules.

### Simulation must be able to represent
- stop-hit
- target-hit
- time-exit
- horizon-end
- unresolved
- invalidated

### Simulation must be
- market-first
- cost-aware
- path-aware
- versioned whenever meaning changes

### Important rule
There must not be one truth surface for labels and a different truth surface for evaluation.

---

## Labels and Features

### Labels
`pipeline/labels.md` converts simulation truth into supervised targets.

Key ideas:
- labels are market-first
- labels are comparative
- no-trade is first-class
- unresolved stays unresolved
- ambiguity must be explicit
- path quality matters

### Features
`pipeline/features.md` transforms canonical state into model-ready features.

Key ideas:
- features come from canonical state only
- no future leakage
- missingness is explicit
- first-phase features should stay boring and interpretable
- shared-model bias is preferred over per-symbol feature pipelines

---

## Dataset and Model Flow

### Dataset
`pipeline/dataset.md` builds lineage-preserving rows for training and evaluation.

Key ideas:
- temporal correctness first
- no random leakage across splits
- unresolved or invalid labels stay out by default
- row lineage must remain traceable
- shared multi-symbol datasets are first-phase default

### Model
`pipeline/model.md` defines the first-phase learned family.

Key ideas:
- XGBoost-first
- shared centralized training infrastructure with separate scope-compatible model artifacts
- compact output surface
- candidate artifacts are not automatically promoted
- runtime ownership stays outside the model

---

## Calibration, Policy, Portfolio, Risk

### Calibration
`pipeline/calibration.md`
- calibration is first-class, not cosmetic
- global calibration first
- confidence must be reliable enough for runtime use
- raw model scores are not enough by themselves

### Policy
`pipeline/policy.md`
- converts calibrated scores into `AnalysisResult`
- decides between `LONG_NOW`, `SHORT_NOW`, and `NO_TRADE`
- keeps timing extension advisory-first
- keeps the action family compact

### Portfolio
`pipeline/portfolio.md`
- handles cross-symbol competition and concentration
- may suppress or down-rank candidates
- stays lightweight in first phase
- must not hide vetoes

### Risk
`pipeline/risk.md`
- final hard safety layer before execution eligibility
- handles cooldowns, duplicate protection, exposure limits, and kill switches
- separate from model, calibration, policy, and portfolio

---

## Evaluation and Monitoring

### Evaluation
`pipeline/evaluation.md`
- economic-quality-first evaluation
- walk-forward / forward-realistic review
- no-trade quality matters
- calibration quality matters
- symbol and regime breakdowns are mandatory
- promotion should be evidence-based

### Monitoring
`pipeline/monitoring.md`
- watches both model quality and lifecycle integrity
- tracks degradation, fallback, action mix, outcome lag, and feature drift
- watches timing extension usefulness
- preserves baseline comparisons

Monitoring is not just for dashboards.
It is part of system trust.

---

## Runtime In One View

Runtime owns:

- request assembly
- result validation
- event creation
- execution eligibility
- persistence
- outcome lifecycle
- operational safety

Engine owns:

- market-state interpretation
- score generation
- confidence generation
- expected R
- recommended action
- timing guidance
- uncertainty / degradation visibility

Runtime owns `scope_router` selection before inference. The model produces `LONG_NOW`, `SHORT_NOW`, or `NO_TRADE` only inside the selected `model_scope`; V7 must not average independent `SWING` / `SCALP` / `AGGRESSIVE_SCALP` outputs.

Runtime should not be rewritten first.
It should be integrated incrementally to the V7 contract family.

---

## Fallback and Safety Rules

### Fallback policy
`runtime/fallback_policy.md` says:
- fallback is allowed
- hidden fallback is forbidden
- every fallback must be explicit, observable, and testable
- degraded request/result/calibration/runtime states must remain visible

### Deployment safety
`runtime/deployment_safety.md` says:
- replay-only, paper, shadow, and live-eligible are distinct rollout shapes
- live-eligibility requires contract correctness, evaluation, monitoring, rollback, and kill-switch readiness
- the first live-eligible release family should treat shadow as required unless waived

### Core safety rule
If the system is unsure whether execution is safe, safe non-execution is the default unless explicit policy says otherwise.

---

## Non-Negotiable Rules

These rules recur throughout the docs set:

- no hidden fallback
- no future leakage
- no hidden deterministic veto
- no training on unresolved outcomes
- no config sprawl outside the unified config surface
- no giant docs repeating each other
- no conflating economic actionability with operational execution eligibility

---

## Roadmap In One View

`roadmap.md` sequences implementation like this:

1. repo alignment
2. contract surfaces
3. simulation truth layer
4. labels and features
5. dataset assembly
6. model and calibration
7. policy / portfolio / risk
8. runtime integration
9. deployment safety
10. evaluation and promotion discipline

The roadmap is phased, but implementation is not perfectly linear.
The main loop is:

- train
- calibrate
- evaluate
- adjust
- re-train
- re-evaluate

---

## LLM Working Rules

`v7_llm_rules.md` says to:

- read authority first
- inspect before editing
- preserve valid work
- do not invent semantics
- keep changes local
- route config through the central config system
- make hidden fallbacks impossible
- test non-trivial changes

`v7_doc_writing_guide.md` says docs should be:

- compact
- low repetition
- explicit about authority
- stable in terminology
- easy to chunk for LLMs

---

## What To Read Next

If you are implementing:
- contracts → start at `contracts/README.md`
- runtime behavior → start at `runtime/runtime_integration.md`
- simulation / labels / model → start at `pipeline/simulation.md`
- repo editing behavior → read `v7_llm_rules.md`
- document structure guidance → read `v7_doc_writing_guide.md`

---

## Final Position

V7 should feel boring in structure and strong in semantics.

The goal is not novelty.
The goal is a system that humans and LLMs can understand, change, and test safely.
