# Simulation Vision — Economic Truth Authority

## One-Sentence Definition

**`/simulation` is the single economic truth authority that evaluates `LONG_NOW`, `SHORT_NOW`, and `NO_TRADE` outcomes under one configurable, versioned, mode-specific simulation engine — producing cost-aware realized R, path metrics, and comparative action evidence consumed by V7 runtime and AlphaForge pipelines.**

## Why Simulation Exists

Trading systems must answer one question honestly:

> Given one decision-time state and a future price path, which action produced the best net economic outcome?

Without a single authoritative answer, the system fragments:

- Labels trained on one cost model while evaluation uses another
- Backtest truth disagrees with paper-forward truth
- "No-trade" quality is invisible or inconsistent
- Regime overrides hide missed opportunities
- Rolling out new stop/target semantics silently breaks old datasets

A unified simulation authority solves all of these at once.

## What Problem It Solves

`/simulation` centralizes economic truth so that:

1. Labels, evaluation, paper trading, replay, and outcome normalization share identical cost/exit/horizon semantics.
2. No-trade is measured honestly alongside directional alternatives.
3. Path quality is preserved, not reduced to terminal return.
4. Semantic changes (new stop rule, different fee model) are versioned and auditable.
5. Both `v7/` (runtime host) and `alphaforge/` (research consumer) trust the same simulation output.

## What Simulation Is

- A deterministic, versioned engine parameterized by trading mode
- The authority that computes: realized-R, fees, slippage, exit reason, MFE, MAE, regret, path quality
- Configurable per mode: SWING (4h primary), SCALP (1h primary), AGGRESSIVE_SCALP (15m primary)
- A contract surface consumed through side-effect-free adapters
- The source of truth for: labels, evaluation evidence, replay, paper-forward projections

## What Simulation Is Not

- A model, policy, risk engine, or runtime orchestrator
- A primitive lib helper (it belongs at `/simulation`, not in `lib/`)
- A V7 internal (V7 hosts it operationally but does not own its semantics)
- An AlphaForge subsystem (AlphaForge consumes outputs, never contains a hidden simulator)
- A label generator directly (labels are alphaforge's interpretation of simulation outputs)
- A black-box outcome oracle with hidden rules

## V7 Relationship

```
/simulation owns:         economic truth semantics and contracts
V7 runtime owns:          operational hosting and execution of simulation
V7 runtime owns:          TradeOutcome normalization, paper/live/replay orchestration
V7 policy/risk owns:      interpretation of simulation evidence for decisions
```

V7 does not own the simulation truth implementation. V7 runtime hosts/executes it operationally through stable contracts.

## AlphaForge Relationship

```
/simulation owns:         economic truth that labels consume
AlphaForge owns:          label interpretation of simulation outputs
AlphaForge owns:          dataset assembly, training, calibration, evaluation
AlphaForge must not:      contain a hidden simulation engine for labels or backtests
```

AlphaForge consumes `/simulation` authority outputs through deterministic, side-effect-free adapters. It must not duplicate simulation truth logic.

## lib Relationship

```
lib/ owns:                primitive math, basic indicators, market data client, time utilities
lib/ must not:            import simulation/, v7/, or alphaforge/
simulation may:           import lib/ primitives if needed (indicators, time, costs)
simulation must not:      import v7/ policy/risk/runtime internals or alphaforge/
```

Simulation is NOT a lib helper. It is a top-level authority. Cost primitives in `lib/` are basic formulas; simulation-specific cost model versioning and composite cost logic belongs in `/simulation`.

## Economic Truth Principles

### 1. Market-First Truth

The market path defines outcome truth. Legacy engines, prior model outputs, and deterministic rules do not define ground truth. Simulation evaluates what the market actually produced.

### 2. Comparative Action Truth

`LONG_NOW`, `SHORT_NOW`, and `NO_TRADE` are always evaluated together under identical cost/exit semantics. No-trade is first-class, not the absence of evaluation.

### 3. Cost-Aware Truth

Fees and slippage are mandatory. Net realized R includes costs. Gross R is preserved for diagnostic comparison.

### 4. Path-Aware Truth

Terminal return alone is not enough. MFE, MAE, path quality, time-to-mfe, time-to-mae, saved-loss, and missed-opportunity metrics provide path-aware evidence.

### 5. No-Trade as First-Class Action

`NO_TRADE` has real economic outcomes: it can save loss or miss opportunity. Simulation quantifies both.

### 6. Versioned Semantics

Any change to stop/target/cost/horizon/time-exit/no-trade quality semantics bumps a version. Old labels remain traceable to the simulation family that produced them. No silent semantic drift.

### 7. Side-Effect-Free Adapters

Training and evaluation adapters must have no live execution side effects. Paper and replay must use the same simulation semantics.

### 8. Runtime-Hosted Execution

V7 runtime hosts/executes the simulation engine operationally. `/simulation` defines the truth semantics. Hosting does not imply semantic ownership.

### 9. Unresolved ≠ Invalidated

Unresolved means the future window is incomplete but may still complete. Invalidated means required future data cannot be completed safely. Both are distinct and explicit.

### 10. Monte Carlo is Diagnostic

Monte Carlo produces distributional evidence (expected-R distribution, downside risk, target/stop probabilities). It does not replace realized simulation truth. Monte Carlo outputs carry separate lineage.

## Success Definition

`/simulation` is successful when:

1. All consumers (v7 runtime, alphaforge labels, evaluation, paper, replay) trust identical simulation output semantics.
2. No hidden simulation engine exists anywhere in the codebase.
3. Semantic changes are versioned and auditable.
4. Golden tests catch drift in stop/target/cost/horizon semantics.
5. Import boundaries are enforced: simulation does not import v7/ policy/risk/runtime, and alphaforge does not contain hidden simulation truth.
6. Regime/policy overrides remain visible and do not silently hide simulation evidence.

## Non-Goals

- Replacing V7 runtime orchestration
- Building a new execution/order-management shell
- Creating multiple simulation engines for different consumers
- Expanding action families beyond `LONG_NOW`/`SHORT_NOW`/`NO_TRADE` in the first version
- Adding complex microstructure simulation in the first version
- Replacing `lib/` primitive cost formulas — simulation wraps and versions them, not duplicates

---

## Document Authority

**Canonical hub:** [ai_summary.md](ai_summary.md) — read this first for the full system synthesis and table of contents.

**Related docs for this topic:**

| [architecture.md](architecture.md) | How simulation is built component-wise |
| [contracts.md](contracts.md) | What contracts define simulation boundaries |
| [ai_summary.md](ai_summary.md) | Dense machine-readable synthesis |
    
**Parent:** [../README.md](../README.md) — authority overview and ownership diagram.

**For implementation:** See [phases/](phases/) for v4.1.1 phase plans S0–S6.

**For validation:** See [validation.md](validation.md) for required test gates.

