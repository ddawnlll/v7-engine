# V7 Simulation Integration — Pointer to /simulation Authority

**Intended path:** `docs/v7/runtime/simulation_engine.md`

## ⚠️ This document has been migrated.

Simulation truth semantics now live in the top-level **`/simulation`** authority.

V7 runtime remains responsible for **operational hosting** of the simulation engine: loading it, providing the execution environment, routing inputs/outputs, materializing TradeOutcome records, and managing lifecycle. V7 runtime does **not** own simulation truth semantics.

Please read:

- **[`/simulation/README.md`](/simulation/README.md)** — authority overview, ownership, relationship map
- **[`/simulation/docs/replay_paper_and_runtime_hosting.md`](/simulation/docs/replay_paper_and_runtime_hosting.md)** — V7 hosting contract, adapters, side-effect isolation
- **[`/simulation/docs/architecture.md`](/simulation/docs/architecture.md)** — component design and data flow
- **[`/simulation/docs/contracts.md`](/simulation/docs/contracts.md)** — SimulationInput, SimulationOutput, ActionOutcome
- **[`/simulation/docs/ai_summary.md`](/simulation/docs/ai_summary.md)** — machine-readable synthesis

## Key Change

**Old:** "Runtime owns simulation execution."
**New:** "`/simulation` owns economic truth semantics and contracts. V7 runtime hosts/executes simulation operationally through stable contracts."

Hosting does not imply semantic ownership.
