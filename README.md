# V7 Engine — Monorepo

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
├── alphaforge/       ← training/research authority
│   ├── src/          ← AlphaForge source code
│   └── docs/         ← master documentation, phase plans, contracts
├── v7/               ← V7 semantic authority
│   └── docs/         ← V7 specifications, contracts, architecture
├── data/             ← canonical data root (all systems read/write here)
│   ├── raw/          ← Binance klines, funding rates
│   ├── processed/    ← cleaned/normalized data
│   ├── cache/        ← ephemeral cache
│   ├── results/      ← evaluation/backtest outputs
│   └── models/       ← trained model artifacts
└── .gitignore        ← properly scoped per-directory gitignore
```

## Key Rules

| Rule | Enforcement |
|---|---|
| **`lib/` does NOT import `v7/` or `alphaforge/`** | Hard-stop test in `lib/tests/test_import_boundary.py` |
| **Binance API only through `lib/market_data/binance/`** | No direct Binance calls from v7 or alphaforge |
| **No "shared everything"** | Regime, R-multiple, IO, serialization, cache, adapters stay in owning packages |
| **All data under `data/`** | Every system reads/writes through the canonical data root |
| **Phase plans drive execution** | See `alphaforge/docs/` for the full phase index and execution contracts |

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

# Check import boundaries
make check-boundaries

# Clean caches and artifacts
make clean

# Show this help
make help
```
