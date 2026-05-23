# Runtime Simulation Engine

**Intended path:** `docs/v7/runtime/simulation_engine.md`

## Purpose

Defines simulation ownership for V7.

It answers:

> Where does simulation run, who owns simulation execution, and how do training, labels, evaluation, replay, paper trading, outcomes, and Monte Carlo consume simulated truth safely?

---

## Core Decision

Simulation runs in runtime.

Runtime hosts the **runtime simulation engine** and owns simulation execution. The V7 model does not own simulation, and the pipeline must not reimplement a separate simulation engine.

Training, labels, evaluation, paper trading, replay, outcomes, and Monte Carlo robustness testing consume the runtime-hosted simulation engine through deterministic, side-effect-free adapters or drivers.

---

## Ownership Rules

### Runtime owns
- runtime simulation engine hosting
- simulation execution orchestration
- paper forward simulation
- historical replay driver orchestration
- simulation profile selection
- simulation run lineage
- separation between simulated truth and live execution truth

### Model does not own
- simulation loops
- stop/target/time-exit execution
- replay execution
- Monte Carlo robustness execution
- TradeOutcome resolution

The model produces scoring and guidance such as `LONG_NOW`, `SHORT_NOW`, `NO_TRADE`, expected-R surfaces, and entry/stop/take-profit guidance inside the selected `model_scope`.

### Pipeline consumes
- normalized simulation outputs
- labels derived from simulation outputs
- replay/evaluation outputs
- Monte Carlo robustness summaries when configured

Pipeline code may define consumption semantics, validation, lineage, and dataset assembly. It must not create a second label-only or backtest-only simulator.

---

## Operating Modes

The runtime simulation engine supports these modes through versioned profiles and side-effect-free adapters where appropriate:

1. **Paper forward simulation**
   - runtime-owned forward simulation used for paper trading and paper outcomes
   - may materialize `DecisionEvent` / `TradeOutcome` records without live execution

2. **Historical replay driver**
   - runtime-owned replay orchestration over historical data
   - uses the same runtime simulation engine with replay-safe inputs
   - must not call live exchange, broker, or mutable account-state paths

3. **Training/replay adapter**
   - deterministic, side-effect-free adapter used by labels and dataset generation
   - builds simulation inputs from canonical historical state and future windows
   - emits versioned simulation outputs for label and dataset lineage

4. **Evaluation replay adapter**
   - deterministic adapter used by walk-forward and candidate/baseline evaluation
   - preserves replay run IDs and simulation profile/version lineage

5. **Monte Carlo robustness mode**
   - robustness/testing mode running on top of the runtime simulation engine
   - produces distributional evidence such as expected-R distribution, downside risk, target-before-stop probability, stop-before-target probability, tail risk, and confidence stability
   - does not replace paper forward simulation, historical replay, or live execution truth

---

## Profiles And Adapters

The runtime simulation engine must support versioned profiles/adapters, including:

- `V6 simulation profile`
- `V7 simulation profile`
- `model_scope` / `trade_mode` profiles for `SWING`, `SCALP`, and `AGGRESSIVE_SCALP`
- cost, fee, slippage, stop, target, and horizon profile families

Profile selection and adapter behavior must be config-driven through the unified config system. Defaults are first-phase defaults, not hardcoded permanent behavior.

---

## Execution Truth vs Simulated Truth

Runtime must distinguish:

- **execution truth**: what actually happened through live or paper execution lifecycle paths
- **simulated truth**: projected/counterfactual outcomes from the runtime simulation engine

Both can be useful, but they are not identical.

Rules:
- live execution side effects must not occur during training, replay, evaluation, or Monte Carlo robustness mode
- replay and training adapters must be side-effect-free
- simulated outcomes must preserve simulation run/profile lineage
- live execution outcomes must preserve execution lineage
- Monte Carlo evidence is diagnostic/distributional and must not masquerade as actual realized outcome

---

## Required Output Semantics

Runtime simulation outputs should preserve:

- long / short / no-trade comparative outcomes
- stop / target / time-exit / horizon-end semantics
- fee and slippage application
- realized R and net economic quality
- MFE / MAE and path metrics
- unresolved / invalidated status
- simulation profile/version lineage
- replay / evaluation / Monte Carlo run identity where used

---

## Interfaces

Upstream:
- `contracts/analysis_request.md`
- runtime state/snapshot builders
- historical replay inputs
- paper runtime decision flow

Downstream:
- `pipeline/simulation.md`
- `pipeline/labels.md`
- `pipeline/dataset.md`
- `pipeline/evaluation.md`
- `pipeline/monitoring.md`
- `contracts/trade_outcome.md`

---

## Test Requirements

Minimum tests:
- paper forward simulation and historical replay driver use the same runtime simulation engine semantics
- training/replay adapter has no live execution side effects
- V6 and V7 simulation profiles are selectable and versioned
- scope-specific horizon/cost/slippage profiles are selected through config
- unresolved and invalidated states remain distinguishable
- Monte Carlo robustness mode produces distributional outputs without replacing actual outcome truth
- execution truth and simulated truth remain distinguishable in lineage

---

## Final Position

Runtime owns simulation execution.
The model does not own simulation.
The pipeline consumes simulation output.
Monte Carlo is a robustness mode on top of the runtime simulation engine, not a replacement for runtime simulation ownership.
