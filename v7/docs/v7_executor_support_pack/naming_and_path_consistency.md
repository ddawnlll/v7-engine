# V7 Naming & Path Consistency

## Purpose

This document is a final consistency note for naming, path usage, and reference hygiene across the V7 docs and implementation-plan set.

It answers:

> When writing code, tests, references, or prompts, what exact paths and naming conventions should be treated as canonical?

---

## Canonical Docs Tree

```text
docs/
├── README.md
├── ai_summary.md
├── architecture.md
├── contracts/
│   ├── README.md
│   ├── analysis_request.md
│   ├── analysis_result.md
│   ├── decision_event.md
│   └── trade_outcome.md
├── pipeline/
│   ├── calibration.md
│   ├── dataset.md
│   ├── evaluation.md
│   ├── features.md
│   ├── labels.md
│   ├── model.md
│   ├── monitoring.md
│   ├── policy.md
│   ├── portfolio.md
│   ├── risk.md
│   └── simulation.md
├── roadmap.md
├── runtime/
│   ├── deployment_safety.md
│   ├── fallback_policy.md
│   └── runtime_integration.md
├── v7_doc_writing_guide.md
├── v7_llm_rules.md
└── vision.md
```

Use these paths exactly.

---

## Canonical Implementation Plan Tree

```text
implementation/
├── master_plan.md
├── phase_0_repo_alignment_and_foundations.md
├── phase_1_contracts_and_validation.md
├── phase_2_simulation_truth_layer.md
├── phase_3_labels_and_outcome_semantics.md
├── phase_4_features_and_dataset.md
├── phase_5_model_baseline.md
├── phase_6_calibration_and_policy.md
├── phase_7_portfolio_risk_and_runtime_integration.md
├── phase_8_evaluation_and_monitoring.md
└── phase_9_deployment_safety_and_release.md
```

If the repo uses a nested docs path such as `docs/implementation/`, keep filenames unchanged and report the path mapping explicitly.

---

## Canonical Object Names

Use these object/type names consistently:

- `AnalysisRequest`
- `AnalysisResult`
- `DecisionEvent`
- `TradeOutcome`

Do not create alternate spellings or aliases unless required by legacy compatibility.

Examples to avoid:
- `RequestPayload`
- `DecisionRecord`
- `TradeLabelOutcome`
- `InferenceResultV7` as a replacement for `AnalysisResult`

Legacy compatibility wrappers are allowed only if clearly isolated.

---

## Canonical Stage Names

Use these stage names consistently:

- `simulation`
- `labels`
- `features`
- `dataset`
- `model`
- `calibration`
- `policy`
- `portfolio`
- `risk`
- `runtime`
- `evaluation`
- `monitoring`

Do not create duplicate stage names such as:
- `scoring` when the doc uses `policy`
- `guards` when the doc uses `risk`
- `allocator` when the doc uses `portfolio`
unless a narrow internal helper truly needs a subordinate name.

---

## Naming Rules

### File names
- keep exact filenames stable once referenced by implementation plans
- do not create duplicate “final”, “v2”, “new”, “fixed” document names inside the main repo tree

### Python modules
Recommended first-phase style:
- snake_case module names
- PascalCase classes
- explicit suffixes only when meaningfully useful:
  - `_validator`
  - `_builder`
  - `_config`
  - `_types`

Examples:
- `analysis_request.py`
- `analysis_result_validator.py`
- `trade_outcome_types.py`

### Test modules
Recommended style:
- `test_<module_or_behavior>.py`

Examples:
- `test_analysis_request_validation.py`
- `test_simulation_cost_model.py`
- `test_runtime_event_materialization.py`

---

## Path Reference Rules

### In docs
Prefer repo-relative paths:

- `contracts/analysis_request.md`
- `runtime/runtime_integration.md`
- `pipeline/simulation.md`

Avoid mixing:
- raw filenames with no folder
- partially shortened paths
- outdated guessed paths

### In code comments and prompts
Prefer the same repo-relative wording used in docs.

Example:
- “Authority: `runtime/runtime_integration.md`”
not
- “Authority: runtime integration doc”

---

## Version Naming Rules

### In docs
Keep V7 versioning in document names only where it already exists:
- contract docs
- runtime integration
- support docs like `v7_llm_rules.md`

Do not introduce fresh `v7_` prefixes into pipeline docs or root summary docs.

### In code
Prefer version fields in data, not version prefixes in every module name.

Good:
- `contract_version`
- `response_schema_version`
- `simulation_family_version`

Avoid:
- `v7_analysis_request_validator.py` unless there is a real need to keep v6 and v7 code active side by side in the same package.

---

## Reference Hygiene Rules

Before finalizing any implementation or prompt:
- verify the referenced doc path exists
- verify the filename matches the real tree
- verify the authority path is the most specific relevant one
- verify there is no stale path from an earlier draft

---

## Known High-Risk Drift Points

Watch these closely:

- `runtime/runtime_integration.md`
- `contracts/README.md`
- `implementation/phase_7_portfolio_risk_and_runtime_integration.md`

These are the most likely places for path shorthand or naming drift because they are referenced often.

---

## Final Position

Naming consistency is not cosmetic.
It is how humans and LLMs keep authority, implementation, and tests aligned without creating phantom files or stale references.
