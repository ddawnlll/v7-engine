# Pipeline Training

**Intended path:** `docs/v7/pipeline/training.md`

## Purpose

Defines the V7 training strategy after the model-scope decision.

It answers:

> How should V7 train multiple trade-mode model families without duplicating the training platform or collapsing all modes into one universal target?

---

## Core Decision

V7 uses **one shared training platform**, not one universal model.

The shared platform includes:
- raw data store
- canonical state / snapshot builder
- shared runtime-hosted simulation engine
- deterministic training/replay adapter for runtime simulation outputs
- feature and label infrastructure
- training runner
- artifact registry
- evaluation framework
- runtime router
- unified config system

The model families are mode-scoped:
- `SWING`
- `SCALP`
- `AGGRESSIVE_SCALP`

Each `model_scope` owns its own dataset family, `primary_interval`, `context_intervals`, `refinement_intervals`, `label_horizon_family`, cost/slippage profile, feature schema variant where needed, calibration artifact, thresholds / policy settings, evaluation report, and model artifact.

Training does not implement simulation and does not call model-side simulation. Candidate artifacts are trained from datasets whose labels and outcome fields are derived from the runtime simulation engine through deterministic, side-effect-free training/replay adapters.

---

## First-Phase Training Strategy

### `SWING`
- `primary_interval`: `4h`
- `context_intervals`: `1d`
- `refinement_intervals`: `1h`
- `label_horizon_family`: swing horizon
- `trade_mode`: `SWING`
- cost/slippage profile: configured swing profile
- artifact family: `v7_swing_model`

### `SCALP`
- `primary_interval`: `15m`
- `context_intervals`: `1h`
- `refinement_intervals`: `5m`
- `label_horizon_family`: scalp horizon
- `trade_mode`: `SCALP`
- cost/slippage profile: configured scalp profile
- artifact family: `v7_scalp_model`

### `AGGRESSIVE_SCALP`
- `primary_interval`: `1m` or `3m`
- `context_intervals`: `5m` + `15m`
- `refinement_intervals`: `1m/3m` micro context where applicable
- `label_horizon_family`: immediate continuation / very short horizon
- `trade_mode`: `AGGRESSIVE_SCALP`
- cost/slippage profile: configured aggressive-scalp profile
- artifact family: `v7_aggressive_scalp_model`

All scope defaults and profiles must be supplied through the unified config system as first-phase defaults or configured overrides, not hardcoded behavior.

---

## Anti-Patterns

Do not:
- train one universal model across `SWING`, `SCALP`, and `AGGRESSIVE_SCALP` rows
- mix primary clocks across scopes in one supervised target
- mix `label_horizon_family` across scopes
- average independent `SWING`, `SCALP`, and `AGGRESSIVE_SCALP` outputs
- let a `SWING` model emit `SCALP` trades
- let a `SCALP` model emit `AGGRESSIVE_SCALP` trades

Intervals may be used as context views inside a scope. They are not independent mode outputs to average.

Simulation anti-patterns:
- do not implement a separate training simulator
- do not call live exchange, broker, order-placement, or mutable runtime account-state paths from training
- do not let the model run simulation during training or inference
- do not treat Monte Carlo robustness mode as a replacement for runtime simulation ownership

---

## Artifact Lifecycle

Training may produce:
- candidate artifacts
- evaluation-promotable artifacts
- live-eligible artifacts

Default rule:
- training produces candidate artifacts only
- evaluation determines whether a scope artifact becomes evaluation-promotable
- deployment safety determines whether a scope artifact becomes live-eligible

Do not promote one `model_scope` because another scope passed evaluation.

Monte Carlo robustness outputs may enrich evaluation evidence, label confidence, or dataset lineage only when configured through the unified config system. They remain distributional evidence from the runtime simulation engine, not live execution truth.

---

## Interfaces

Upstream:
- `pipeline/dataset.md`
- `pipeline/labels.md`
- `pipeline/features.md`
- `runtime/simulation_engine.md`
- `pipeline/simulation.md`

Downstream:
- `pipeline/model.md`
- `pipeline/calibration.md`
- `pipeline/evaluation.md`
- `runtime/runtime_integration.md`

---

## Final Position

V7 centralizes the training platform and separates the model scopes.
That is the resolved balance: shared infrastructure, separate scope-compatible artifacts.
