# V7 Simulation Integration — Pointer to /simulation Authority

**Intended path:** `docs/v7/pipeline/simulation.md`

## ⚠️ This document has been migrated.

Simulation truth semantics now live in the top-level **`/simulation`** authority.

Please read:

- **[`/simulation/README.md`](/simulation/README.md)** — authority overview
- **[`/simulation/docs/vision.md`](/simulation/docs/vision.md)** — what simulation is and why it exists
- **[`/simulation/docs/architecture.md`](/simulation/docs/architecture.md)** — component design and data flow
- **[`/simulation/docs/contracts.md`](/simulation/docs/contracts.md)** — SimulationInput, SimulationOutput, ActionOutcome contracts
- **[`/simulation/docs/profiles.md`](/simulation/docs/profiles.md)** — mode-specific profiles (SWING/SCALP/AGGRESSIVE_SCALP)
- **[`/simulation/docs/cost_model.md`](/simulation/docs/cost_model.md)** — fee, slippage, net R semantics
- **[`/simulation/docs/exits_and_horizons.md`](/simulation/docs/exits_and_horizons.md)** — stop, target, time exit, unresolved, invalidated
- **[`/simulation/docs/no_trade_quality.md`](/simulation/docs/no_trade_quality.md)** — no-trade classification
- **[`/simulation/docs/lineage_and_versioning.md`](/simulation/docs/lineage_and_versioning.md)** — version surfaces
- **[`/simulation/docs/replay_paper_and_runtime_hosting.md`](/simulation/docs/replay_paper_and_runtime_hosting.md)** — V7 hosting, adapters
- **[`/simulation/docs/monte_carlo.md`](/simulation/docs/monte_carlo.md)** — diagnostic Monte Carlo
- **[`/simulation/docs/validation.md`](/simulation/docs/validation.md)** — test gates
- **[`/simulation/docs/migration_from_v7.md`](/simulation/docs/migration_from_v7.md)** — migration notes
- **[`/simulation/docs/ai_summary.md`](/simulation/docs/ai_summary.md)** — machine-readable synthesis

## Key Change

**Old:** V7 owns the simulation truth layer.
**New:** `/simulation` owns economic truth semantics and contracts. V7 runtime hosts/executes simulation operationally through stable contracts.

Do not add new simulation truth semantics here. Update `/simulation/docs` instead.
