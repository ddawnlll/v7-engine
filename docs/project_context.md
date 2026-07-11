# V7 Engine — Project Context

> **Status:** ACTIVE_DEVELOPMENT
> **Last updated:** 2026-07-11
> **Source of truth:** This file is maintained alongside the codebase. When code and docs conflict, code wins but docs must be updated.

## What Is This?

V7 Engine is a **quantitative trading research and production monorepo**. It covers the full pipeline:

1. **Market data ingestion** — Binance OHLCV, funding rates via `lib/`
2. **Feature engineering** — Indicators, microstructure features, regime detection
3. **Simulation** — Economic truth layer with fee/slippage/horizon semantics
4. **Alpha discovery** — XGBoost-based alpha models via AlphaForge
5. **Policy-driven execution** — V7 pipeline with mode-specific policies
6. **Runtime** — Python backend (FastAPI), scan loop, analyzer, learning layer
7. **Interface** — React + TypeScript operator UI

**Test count:** 847+ passing tests (Python 3.12+)

## Repository Structure

```
v7-engine/
├── lib/              ← Shared primitives (Binance client, indicators, costs, time)
├── simulation/       ← Economic simulation truth authority
├── alphaforge/       ← Alpha discovery: labels, features, XGBoost, calibration
├── v7/               ← V7 pipeline: ModelRegistry, inference, AnalysisResult
├── policycritic/     ← Policy Critic: IQL-based advisory offline-RL
├── runtime/          ← Python backend (FastAPI, scan loop, analyzer, learning, DB)
├── interface/        ← React + TypeScript + Vite operator UI
├── contracts/        ← Cross-domain schemas, registry, field mappings
├── integration/      ← Adapter stubs, cross-domain tests, boundary enforcement
├── v6/               ← Legacy V6 config compatibility stub
├── data/             ← Raw data, processed data, cache, results, models
├── configs/          ← Training configs, profiles, gates
├── docs/             ← Cross-domain governance, architecture, runbook
├── .agent/           ← Agent handoff and context layer (this system)
└── scripts/          ← Operational and build scripts
```

## Domain Boundaries (STRICT)

| Domain | Owns | Must NOT Import |
|--------|------|-----------------|
| `lib/` | Market data, indicators, costs, time primitives | simulation, alphaforge, v7 |
| `simulation/` | Economic truth, costs, exits, path metrics | alphaforge, v7 |
| `alphaforge/` | Alpha discovery, labels, features, model training | simulation, v7 |
| `v7/` | Policy acceptance, runtime orchestration | simulation (lazy importlib only) |
| `runtime/` | Backend lifecycle, API, safety gates | alphaforge (via services) |
| `integration/` | Adapter stubs, boundary tests | simulation, alphaforge, v7 |
| `contracts/` | Schemas, registry, mappings | Any Python code |

**Truth hierarchy:** `simulation > realized > contract > runtime > model`

## Phase Status

| Phase | Scope | Status |
|-------|-------|--------|
| P0–P6 | Foundation, contracts, simulation | ✅ COMPLETE |
| P7 | Simulation truth authority | ✅ LOCKED |
| P8 | AlphaForge discovery authority | ✅ LOCKED |
| P9 | AlphaForge implementation | ✅ COMPLETE |
| P10 | Policy Critic RL research | 🔶 IN PROGRESS |
| P11 | Performance optimization | 📋 PLANNED |

## Mode Priority

| Mode | Priority | Status |
|------|----------|--------|
| SCALP | PRIMARY | `LOCKED_INITIAL_BASELINE` |
| AGGRESSIVE_SCALP | PRIMARY | `HOLD` |
| SWING | SECONDARY_BASELINE | `LOCKED_INITIAL_BASELINE` |

SWING is implemented first as a control baseline to validate the architecture — NOT because it is the primary product.

## Design Lock Semantics

| Status | Meaning |
|--------|---------|
| `LOCKED` | Authoritative, do not change without contradiction evidence |
| `LOCKED_INITIAL_BASELINE` | Implementation-ready baseline; recalibrate after first evidence |
| `LOCKABLE_WITH_HOLDS` | Architecture locked; specific holds scoped and explicit |
| `HOLD` | Cannot lock — requires empirical evidence, owner review |
| `DEFERRED` | Explicitly postponed with documented formula and blocking rule |
| `LOCK_CANDIDATE` | Conservative default requiring owner review before lock |

## Current Verified Performance

| Metric | Value | Condition |
|--------|-------|-----------|
| Test suite | 847 tests, 95.5% pass | Real data pipeline |
| Training duration | 0.61s (10 sym × 2000 bars) | SCALP, XGBoost |
| IC | 0.2387 | Positive signal detection |
| RankIC | 0.2254 | Monotonic ranking |
| ECE | 0.0922 | Reasonable calibration |
| MCE | 0.4733 | |
| WFV avg accuracy | 0.4480 | 6-fold simulation |

## Key Files

| File | Purpose |
|------|---------|
| `AGENTS.md` | Working instructions for AI agents |
| `ai_summary.md` | Repo-level meta-hub |
| `contracts/registry.json` | Canonical cross-domain contract list |
| `contracts/compatibility.json` | Version compatibility rules |
| `train_pipeline.py` | End-to-end AlphaForge training |
| `v7/docs/roadmap.md` | Implementation phases, lock status, holds |
| `.github/workflows/ci.yml` | CI pipeline |
| `Makefile` | `make test-all`, `make check-contracts`, `make check-boundaries` |

## Governance

See `docs/architecture/governance.md` for full domain ownership and conflict resolution rules.

> **For AI agents:** Always read `.agent/CONTEXT_INDEX.md` first for the correct reading order and worker protocol.
