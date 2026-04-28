# V7 LLM Rules

## Purpose

This document defines how V7 documentation, Python code, tests, and repo structure should be written so that:

- LLM code agents can read and modify the system safely
- humans can review changes quickly
- implementation remains testable and measurable
- the repository stays compact rather than becoming doc or code sprawl

This is not a style document for prose elegance.
It is a control document for AI-assisted engineering quality.

---

## Core Position

V7 should be optimized for:

1. local changes
2. explicit boundaries
3. small analyzable files
4. deterministic behavior
5. easy test execution
6. measurable quality at every layer

The main rule is simple:

**A code agent should be able to understand one concern by reading one primary doc, one primary module, one config surface, and one test surface.**

This matches the current V7 direction:
- centralized architecture
- one runtime-hosted simulation engine / simulated-truth layer
- one central config loader
- low repetition docs
- AI-first readability
- one concern, one primary module
- local changes instead of broad rewrites

---

## What `llm_rules.md` Is For

`llm_rules.md` should answer:

- how LLMs should read the repo
- how LLMs should decide what is authoritative
- how LLMs should classify files before editing
- how LLMs should make changes
- how LLMs should test changes
- how LLMs should stop when behavior is ambiguous
- how docs and code should be shaped so LLMs succeed

It should not become:
- a second architecture doc
- a giant coding tutorial
- a duplicate of every contract
- a vague best-practices page with no enforcement value

---

## LLM Working Rules

### 1. Read authority first

Before changing anything, the agent must read:

1. task-specific authority doc
2. relevant contract docs
3. relevant runtime or policy doc
4. existing config surface
5. existing implementation files
6. existing tests

The agent must not start by writing code.

### 2. Inspect before editing

Before editing any area, the agent must classify relevant files as:

- `KEEP`
- `COMPLETE`
- `FINISH`
- `FIX`
- `REPLACE`
- `REMOVE`
- `INSPECT_FURTHER`

### 3. Preserve valid work

Default policy:
- keep working code
- finish partial code
- fix incorrect code
- replace only when the current design clearly conflicts with authority

### 4. Do not invent semantics

If behavior is not defined by:
- authority docs
- contracts
- runtime policy
- config defaults
- existing implementation patterns

the agent must stop and report the ambiguity.

### 5. One concern, one primary edit path

For most tasks, a correct change should touch:
- one primary module
- one config surface
- one test surface

### 6. Config is the only control surface

Any new threshold, toggle, constant, ratio, window, or runtime setting must go through the central config system.

### 7. Hidden fallbacks are forbidden

If the system degrades, skips, or falls back:
- it must be explicit
- it must be observable
- it must be testable

### 8. Every non-trivial change must be tested

At minimum, update or add:
- unit tests for local logic
- integration tests for boundary behavior
- regression tests where relevant

### 9. Highest-risk test first

Write or update the highest-risk test first.

### 10. Prefer simple Python over framework cleverness

Prefer:
- explicit functions
- small classes
- direct data flow
- typed structures

Avoid:
- decorator-heavy hidden behavior
- runtime monkey patching
- side-effectful global module initialization
- implicit registry mutation spread across the repo

---

## Recommended Repository Shape

```text
src/
  v7/
    cli/
    config/
    contracts/
    state/
    simulation/
    features/
    labels/
    dataset/
    model/
    calibration/
    policy/
    portfolio/
    risk/
    runtime/
    evaluation/
    monitoring/
tests/
  unit/
  integration/
  regression/
configs/
docs/v7/
```

Each top-level concern should have:
- one primary doc
- one primary module family
- one primary config surface
- one primary test area

---

## Maximum File Size Guidance

### Documentation files
- ideal: **600 to 1,500 words**
- soft limit: **2,000 words**
- hard limit: **2,500 words**

### Python files
- ideal: **150 to 350 lines**
- soft limit: **500 lines**
- hard limit: **700 lines**

### Test files
- ideal: **120 to 300 lines**
- soft limit: **400 lines**
- hard limit: **550 lines**

If files exceed the hard limit, they should usually be split.

---

## Python Writing Rules

### 1. Prefer explicit modules

Each module should have one job.

### 2. Prefer pure functions where possible

Good candidates:
- feature transforms
- label logic
- threshold logic
- cost calculations
- outcome normalization
- state validation

### 3. Keep orchestration thin

Orchestration modules should wire components together.
They should not contain large chunks of business logic.

### 4. Use type hints everywhere practical

Minimum expectation:
- public function signatures typed
- dataclass fields typed
- return values typed
- optional values explicit

### 5. Use typed structures for contracts

Contracts, config objects, state records, and normalized results should use explicit typed structures.

### 6. Avoid deep inheritance

Prefer composition over inheritance.

### 7. Avoid hidden mutable global state

Use explicit objects passed through functions or service layers.

### 8. Keep function size small

- ideal: **10 to 35 lines**
- soft limit: **50 lines**
- hard limit: **80 lines**

### 9. Keep parameter lists small

- ideal: **3 to 6 parameters**
- soft limit: **8 parameters**
- beyond that, use a typed context object

### 10. Prefer stable naming

Use names that map directly to docs, such as:
- `AnalysisRequest`
- `AnalysisResult`
- `DecisionEvent`
- `TradeOutcome`
- `CanonicalState`
- `CalibrationResult`

---

## Formatting and Tooling Rules

Required tools:
- `ruff`
- `black`
- `pytest`
- `mypy` or `pyright` for core typed surfaces

Style baseline:
- line length: **100**
- imports grouped and sorted automatically
- docstrings only where they add value
- comments should explain why, not repeat what

Logging rules:
- structured logging preferred
- no noisy debug spam in core loops
- logs should expose degradation, fallback, and important state transitions

---

## Error Handling Rules

### 1. Fail early on invalid config
Invalid config should raise immediately.

### 2. Use explicit domain errors where useful
For core subsystems, define a small number of meaningful exception classes.

### 3. Do not silently swallow errors
If behavior degrades, return structured degradation or fallback info where appropriate.

### 4. Separate invalid input from expected no-action behavior
Examples:
- invalid state is not the same as no trade
- degraded request is not the same as successful normal path

---

## Test Strategy

### Unit tests
Test isolated pure logic:
- cost calculations
- stop or target resolution
- threshold gating
- label comparison
- feature transforms
- config validation

### Integration tests
Test boundaries between modules:
- request to state to features
- model output to calibration to policy
- decision event to outcome linkage
- config loader to resolved config object

### Regression tests
When a bug is fixed, preserve it with a focused regression test.

### Contract tests
Every core contract should test:
- required fields
- forbidden fields
- optionality
- versioning behavior
- serialization round-trip where relevant

### Golden-path simulation tests
Define a small number of authoritative scenario tests:
- stop hit first
- target hit first
- timeout exit
- fee or slippage effect
- long vs short vs no-trade comparative outcome

---

## Quality Measurement Rules

Quality should be measured at multiple levels.

### A. Code quality
Measure:
- lint pass
- format pass
- type-check pass
- test pass
- function or file size rule compliance
- import cycle absence

### B. Contract quality
Measure:
- stable field definitions
- no hidden required fields
- explicit optionality
- clear versioning
- schema or serialization tests

### C. Simulation quality
Measure:
- deterministic same-input results
- cost-model correctness
- outcome path correctness
- counterfactual consistency
- parity between labeling and evaluation semantics

### D. Model pipeline quality
Measure:
- feature schema stability
- training or inference schema parity
- calibration metrics
- no-trade quality
- symbol or regime breakdowns
- forward evaluation metrics

### E. Documentation quality
Measure:
- file size within limits
- low repetition
- explicit ownership boundaries
- explicit out-of-scope sections
- stable terminology reuse

---

## Recommended Test Commands

```bash
ruff check .
black --check .
mypy src
pytest -q
pytest tests/unit -q
pytest tests/integration -q
pytest tests/regression -q
```

Also support narrow commands:

```bash
pytest tests/unit/simulation -q
pytest tests/integration/test_analysis_flow.py -q
pytest -k "calibration and not slow" -q
```

---

## Slow vs Fast Tests

Mark tests clearly.

### Fast tests
- default local run
- should finish quickly
- run on every change

### Slow tests
- larger simulation slices
- training smoke tests
- heavier end-to-end flows

Use marks such as:
- `@pytest.mark.slow`
- `@pytest.mark.integration`
- `@pytest.mark.regression`

---

## Fixture Rules

Preferred fixtures:
- synthetic candle windows
- synthetic state objects
- tiny model stubs
- tiny config fixtures
- tiny outcome scenarios

Avoid:
- giant historical datasets in unit tests
- hidden shared fixtures that do too much
- flaky time-dependent fixtures
- live network calls

---

## Environment Design Rules

Recommended baseline:
- Python **3.11** or **3.12**
- `uv` or `poetry` or a very small `requirements` setup
- `pytest`
- `ruff`
- `black`
- `mypy`
- optional `pre-commit`

Pick **one** environment and packaging workflow and stay consistent.

Do not mix:
- poetry
- pipenv
- conda
- ad hoc shell installs
- multiple overlapping task runners

A small, boring environment is best for LLM reliability.

---

## Dependency Rules

### 1. Keep dependencies minimal
Every dependency increases analysis burden.

### 2. Prefer proven libraries
Use libraries with clear, boring APIs.

### 3. Avoid framework stacking
Do not build the system on top of many overlapping abstraction layers.

### 4. Separate core from optional extras
Keep training, runtime, and tooling dependencies understandable.

---

## Documentation Writing Rules

Each technical doc should usually have these sections:

```text
Purpose
In Scope
Out of Scope
Authority
Inputs
Outputs
Invariants
Rules
Failure / Fallback
Config Surface
Interfaces / Integration Points
Test Requirements
Non-Goals
Links
```

Documentation rules:
- one document = one concern
- do not repeat semantic definitions across many docs
- link rather than restate
- keep examples short
- state forbidden changes explicitly
- state ownership explicitly

---

## Recommended `llm_rules.md` Sections

The final `llm_rules.md` should contain:

1. Purpose
2. Core working rules
3. Authority order
4. Repo reading order
5. File classification rules
6. Config rules
7. Python writing rules
8. Testing rules
9. Ambiguity stop rule
10. Final response or reporting rules
11. File size limits
12. Documentation writing rules

---

## Suggested Final Response Rules For Agents

For implementation tasks, require agents to report:

1. current task
2. authority docs used
3. authority path resolution
4. design summary
5. current repo status
6. files changed
7. config changes
8. tests run
9. test results
10. remaining ambiguity or risk
11. next safe step

---

## Practical Bottom Line

For V7, the best LLM environment is not the most advanced.
It is the most analyzable.

That means:
- small docs
- small Python files
- typed contracts
- explicit config
- explicit tests
- thin orchestration
- low magic
- deterministic simulation logic
- one concern per module
- one concern per test surface
- one concern per doc

If V7 follows those rules, LLMs will be able to:
- inspect the repo quickly
- make smaller safer edits
- test changes reliably
- explain decisions clearly
- avoid unnecessary rewrites
