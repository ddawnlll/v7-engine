# V7 Engine — Locked Decisions

> **Status:** ACTIVE
> **Purpose:** This file records all locked design decisions and their rationale.
> New workers must treat these as prior knowledge. Do not silently override.
>
> **Format:** Each decision has an ID (DEC-NNN), status, rationale, evidence, and scope.

---

## DEC-001 — Domain Isolation with Strict Import Boundaries

**Status:** `LOCKED`
**Date:** 2026-06-15
**Scope:** All Python modules

**Decision:** Each domain (`lib/`, `simulation/`, `alphaforge/`, `v7/`, `runtime/`) must enforce strict one-way import rules as defined in `governance.md`. Cross-domain communication must go through `contracts/` schemas and `integration/` adapters.

**Rationale:**
- Prevents circular dependencies between research and production code.
- Simulation must remain independent of alpha discovery to maintain economic truth authority.
- AlphaForge must not depend on V7 runtime decisions to avoid overfitting to current policy.
- Enforced by CI (`make check-boundaries`).

**Evidence:**
- `integration/tests/test_cross_domain_boundaries.py` — 96 passing tests
- `lib/tests/test_import_boundary.py` — enforces lib isolation
- Multiple pre-existing violations caught and fixed during P0–P6

---

## DEC-002 — Truth Hierarchy: Simulation > Realized > Contract > Runtime > Model

**Status:** `LOCKED`
**Date:** 2026-06-15
**Scope:** All domains

**Decision:** In any conflict between components:
1. **Simulation** output is the economic truth authority (with correct cost model)
2. **Realized** P&L from live/replay is secondary evidence
3. **Contract** schemas define canonical field shapes
4. **Runtime** behavior must not override simulation truth
5. **Model** confidence must never override risk gates

**Rationale:**
- Prevents overfitting to model confidence.
- Simulation is the only place where full counterfactual evaluation is possible.
- Runtime decisions must be conservative relative to simulation-derived policy.

---

## DEC-003 — Mode Priority: SCALP Primary, SWING as Control Baseline

**Status:** `LOCKED_INITIAL_BASELINE`
**Date:** 2026-06-20
**Scope:** v7 pipeline, simulation profiles, training config

**Decision:**
- **SCALP** is PRIMARY business and research priority
- **SWING** is SECONDARY_BASELINE — implemented first as architectural validation
- **AGGRESSIVE_SCALP** is PRIMARY but `HOLD` until SCALP empirical validation
- Mode-specific thresholds must not be locked without empirical evidence

**Rationale:**
- SWING is simpler (lower frequency, fewer edge cases) → faster architectural validation
- SCALP requires all the same pipeline machinery but with stricter latency/risk requirements
- Starting with SWING catches architectural flaws before SCALP complexity is added

**Holds:**
- SWING simulation profile parameters (stop/target multipliers) need real-data validation
- SCALP threshold locking requires empirical benchmarking

---

## DEC-004 — Contracts as Passive Authority

**Status:** `LOCKED`
**Date:** 2026-06-15
**Scope:** `contracts/`

**Decision:** `contracts/` contains NO Python code. It is a passive schema authority:
- `registry.json` is the canonical contract list
- `schemas/*.schema.json` define field shapes
- `mappings/` define cross-domain field transformations
- `compatibility.json` defines version compatibility rules
- Schema changes require MINOR/MAJOR version bumps per policy

**Rationale:**
- Passive schemas can be read by any tool/language without import dependencies.
- Version compatibility is explicitly documented, not implicit in code.
- CI enforces schema parity and registry consistency.

**Evidence:**
- `contracts/registry.json` currently lists all contracts
- `make check-contracts` passes
- Schema-parity tests catch field drift between domains

---

## DEC-005 — Simulation Cost Model: Fee + Slippage + Funding

**Status:** `LOCKED`
**Date:** 2026-06-18
**Scope:** `simulation/`

**Decision:** Simulation must include:
- **Exchange fees**: tiered maker/taker (0.02%/0.05% baseline)
- **Slippage**: volume-based partial fill model
- **Funding rate**: 8h interval perpetual swap funding
- **No implicit win/loss adjustment**: R-multiples are computed from raw simulation, not adjusted post-hoc

**Rationale:**
- Funding costs are material for SCALP (8h funding periods vs 1h bars)
- Without slippage, simulation overestimates performance systematically
- Post-hoc adjustments hide real simulation behavior

**Evidence:**
- `simulation/docs/cost_model.md` — full specification
- `integration/tests/test_funding_costs.py` — 14 passing tests
- Verified in Wave 0 acceptance tests

---

## DEC-006 — Preprocessing Bottleneck Audit Findings

**Status:** `LOCKED`
**Date:** 2026-07-06
**Scope:** `alphaforge/data/preprocessing.py`, training pipeline

**Decision:** Dataset preprocessing is single-thread CPU bound and must be optimized before scaling training beyond 10 symbols. Do NOT port entire pipeline to CUDA — instead:
1. Separate decode, parsing, feature transforms, batching, and host-to-device transfer
2. Benchmark each stage independently
3. Test multiprocessing/DataLoader workers first
4. Identify transforms suitable for torch/CUDA

**Rationale:** `F-017` finding confirmed that 68% of total training pipeline duration is spent before training begins, with CPU utilization at 96% on one core and GPU below 4%.

**Evidence:**
- `profiling/*.json` — stage-level duration data (from training pipeline profile)
- `alphaforge/data/preprocessing.py:118-201` — single-threaded loop
- CPU 96% / GPU < 4% utilization

---

## DEC-007 — Real Data Over Synthetic Verification

**Status:** `LOCKED`
**Date:** 2026-07-11
**Scope:** All research and training tasks

**Decision:** All performance claims must be verified against real Binance market data (OHLCV, funding rates). Synthetic data or mocked/stub results are insufficient for claiming completion.

**Rationale:**
- Synthetic data does not reflect market microstructure noise, gaps, or anomalies
- Real data catches edge cases (missing rows, duplicate timestamps, delisted symbols) that synthetic data misses
- Current evidence: BTCUSDT had duplicate rows + 59-day gap not caught in synthetic testing

---

## DEC-008 — BTCUSDT Data Quality Alert

**Status:** `LOCKABLE_WITH_HOLDS`
**Date:** 2026-07-06
**Scope:** `data/raw/BTCUSDT/`

**Decision:**
- BTCUSDT raw data has 4 duplicate rows (identical OHLCV at 2 timestamps)
- BTCUSDT has a 59-day data gap (2024-01-02 to 2024-03-01, ~1438 missing hours)
- ETH/BNB/SOL are clean: 29,928 rows, 0 NaN, 0 gaps, 0 duplicates

**Holds:**
- Run `df.drop_duplicates(subset=['timestamp'])` on BTCUSDT_1h_full.parquet
- Backfill BTC data for Q1 2024 or document acceptable gap for training splits

**Evidence:**
- BTCUSDT raw: 28,492 rows vs 29,928 expected
- Duplicate timestamps: 1704067200000 (x2), 1704153600000 (x2)
- Gap: 2024-01-02 to 2024-03-01 (59 days)

---

## DEC-009 — Cache Panel NaN Management

**Status:** `LOCKABLE_WITH_HOLDS`
**Date:** 2026-07-06
**Scope:** Cache factor panels in `cache/factor_sprint/`

**Decision:** 5 cache factor panels have 43,989 NaN values (7.35% of cells) across 7 symbols. XGBoost handles NaN natively (learns split direction), but explicit masking/documentation is needed:
- MATICUSDT 50.33% NaN (delisted symbol)
- BTCUSDT 21.81% NaN (correlated with raw data gap)
- BNB/ETH/SOL ~19.5% NaN (early data before symbol launch)
- SUI 9.84%, ARB 6.55%

**Holds:**
- Document NaN handling strategy — confirm XGBoost missing-value handling is appropriate
- Fix BTCUSDT raw data gap to reduce cache NaN

---

## DEC-010 — ACCP-YAML as Task Completion Evidence

**Status:** `LOCKED`
**Date:** 2026-07-06
**Scope:** Reporting

**Decision:** Every task must produce an ACCP-YAML report in `reports/` with:
- `result`, `scope_confirmation`, `files_changed`, `decisions_locked`
- `remaining_holds`, `safe_next_step`, `commands_run`, `evidence`

**Rationale:** ACCP-YAML files make progress machine-auditable. A new worker can read the latest report and immediately understand what was done, what was found, and what remains.

**Evidence:**
- `reports/alphaforge-audit-2026-07-06.yaml` — example of report format
- 40+ ACCP-YAML reports in `reports/` directory

---

## Undecided / Open for Decision

| Question | Status | Blocked By |
|----------|--------|------------|
| CUDA transform pipeline architecture | `HOLD` | Need stage-level benchmarks (F-017) |
| BTC gap backfill strategy | `HOLD` | Need decision on acceptable data range |
| Policy Critic integration point | `HOLD` | RL research in progress (P10) |
| AGGRESSIVE_SCALP thresholds | `HOLD` | SCALP empirical validation first |
