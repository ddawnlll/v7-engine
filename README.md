# V7 Engine — Monorepo

[![CI](https://github.com/ddawnlll/v7-engine/actions/workflows/ci.yml/badge.svg)](https://github.com/ddawnlll/v7-engine/actions/workflows/ci.yml)

A monorepo for quantitative trading research and production: market data infrastructure,
feature engineering, regime detection, simulation, XGBoost-based alpha modeling,
and V7 policy-driven execution.

## Structure

```
v7-engine/
├── lib/              ← shared primitives (identical usage across systems)
│   ├── market_data/  ← Binance client, klines/funding, quality
│   ├── indicators/   ← ATR, returns, volatility, rolling (pure math)
│   ├── costs/        ← fee %, slippage estimation (basic formulas)
│   ├── time/         ← interval conversion, walk-forward folds
│   ├── tests/        ← 117+ tests, import-boundary enforcement
│   └── docs/         ← lib specifications and phase plans
├── simulation/       ← economic simulation truth authority
│   └── docs/         ← vision, architecture, contracts, profiles, phases
├── alphaforge/       ← anomaly discovery / alpha research authority
│   ├── src/          ← AlphaForge source code (not yet implemented)
│   └── docs/         ← authority docs, contracts, phase plans (ai_summary.md hub)
├── v7/               ← V7 semantic/runtime/policy authority
│   └── docs/         ← V7 specifications, contracts, architecture, policy_critic/ RL research
├── policycritic/     ← V7 Policy Critic research & business plan (docs/design only)
│   └── docs/         ← design, research, phase plans, business case, quality scoring
├── runtime/          ← Python backend (imported from v4, migrated to v7)
│   ├── api/          ← FastAPI route groups
│   ├── db/           ← operational schema
│   ├── services/     ← scan loop, analyzer, learning layer
│   └── docs/         ← runtime ai_summary, runbook, architecture
├── interface/        ← React + TypeScript + Vite operator UI (imported from v4, migrated to v7)
│   ├── src/          ← React components and pages
│   └── docs/         ← interface ai_summary, architecture, migration plan
├── contracts/        ← passive root contract authority
│   ├── registry.json       ← master contract list
│   ├── compatibility.json  ← version compatibility rules
│   ├── schemas/            ← JSON Schema definitions
│   ├── mappings/           ← cross-domain field mappings
│   └── fixtures/           ← minimal valid contract examples
├── integration/      ← cross-domain adapter stubs & system tests
│   ├── adapters/           ← interface stubs (simulation, alphaforge, v7)
│   └── tests/              ← contract, boundary, schema, smoke tests
├── data/             ← canonical data root (all systems read/write here)
│   ├── raw/          ← Binance klines, funding rates
│   ├── processed/    ← cleaned/normalized data
│   ├── cache/        ← ephemeral cache
│   ├── results/      ← evaluation/backtest outputs
│   └── models/       ← trained model artifacts
├── docs/architecture/← root governance and workflow docs
│   ├── governance.md       ← conflict resolution, domain ownership
│   └── feature_workflow.md ← contract-first feature workflow
├── scripts/          ← operational/utility scripts
├── reports/          ← generated reports (e.g. evaluation outputs)
└── .gitignore        ← properly scoped per-directory gitignore
```

## Key Rules

| Rule | Enforcement |
|---|---|
| **`lib/` does NOT import `v7/`, `alphaforge/`, or `simulation/`** | Hard-stop test in `lib/tests/test_import_boundary.py` |
| **`runtime/` and `interface/` promoted from v4 → v7** | Runtime is the Python backend; Interface is the React/TypeScript UI. Both retain their internal docs structure. |
| **`/simulation` owns economic truth contracts and semantics** | docs + import-boundary tests |
| **V7 runtime hosts simulation but does not duplicate semantics** | Contract integration |
| **AlphaForge consumes simulation outputs only (side-effect-free adapters)** | Adapter parity tests |
| **No label-only/backtest-only simulator** | Search audit + CI gates |
| **Binance API only through `lib/market_data/binance/`** | No direct Binance calls from v7 or alphaforge |
| **No "shared everything"** | Regime, R-multiple, IO, serialization, cache, adapters stay in owning packages |
| **All data under `data/`** | Every system reads/writes through the canonical data root |
| **Phase plans drive execution** | See `alphaforge/docs/` and `simulation/docs/phases/` for phase indices |
| **`contracts/` is root passive contract authority** | `make check-contracts` validates registry, schemas, mappings, fixtures |
| **`integration/` is cross-domain adapter/test skeleton** | `make check-boundaries` and `make test-system` enforce gates |
| **`docs/architecture/governance.md` is root cross-domain governance** | Defines conflict resolution, domain ownership, import discipline |
| **New cross-domain features must follow contract-first workflow** | `contracts/` schemas before implementation; schema parity tests enforce |

## Phases

| Phase | Title | Status |
|---|---|---|
| P0 | Repo Alignment & Alpha Foundations | Done |
| **P0.5** | **Shared Lib Foundation** | **Done** — lib/ created with 117 passing tests |
| P1 | Contracts & Alpha Data Contract | Planned |
| P2 | Runtime Simulation Adapter & R-Label Engine | Planned |
| P3 | Multi-Timeframe Feature Engine & Unsupervised Context | Planned |
| P4 | Dataset Assembly, Walk-Forward Splits & Label QA | Planned |
| P5 | XGBoost Hybrid Model Training | Planned |
| P6 | Calibration, Reliability & Alpha Score Builder | Planned |
| P7 | V7 Policy, Portfolio & Risk Integration | Planned |
| P8 | Evaluation, Backtest, Paper & Shadow Validation | Planned |
| P9 | Deployment, Monitoring, Drift, Promotion & Rollback | Planned |

See `alphaforge/docs/phase_index.md` for dependency chain and full details.

## Quick Start

```bash
# Install dependencies
make install

# Run all lib/ tests
make test

# Run specific test
make test file=lib/tests/test_time.py

# Check all import boundaries (lib + cross-domain)
make check-boundaries

# Validate contract registry, schemas, and field mappings
make check-contracts

# Run all system-level tests (contracts + boundaries + smoke)
make test-system

# Run all tests (lib + system)
make test-all

# Clean caches and artifacts
make clean

# Show this help
make help
```
