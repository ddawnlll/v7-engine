# V7 Engine — Monorepo

[![CI](https://github.com/ddawnlll/v7-engine/actions/workflows/ci.yml/badge.svg)](https://github.com/ddawnlll/v7-engine/actions/workflows/ci.yml)

A monorepo for quantitative trading research and production: market data infrastructure,
feature engineering, regime detection, simulation, XGBoost-based alpha modeling,
and V7 policy-driven execution.

**847 tests passing.** Python 3.12+.

## Structure

```
v7-engine/
├── lib/              ← shared primitives (Binance client, indicators, costs, time)
├── simulation/       ← economic simulation truth authority (engine, Monte Carlo, contracts)
├── alphaforge/       ← AlphaForge research: labels, features, XGBoost, calibration, policy
├── v7/               ← V7 pipeline: ModelRegistry, inference, AnalysisResult builder
├── policycritic/     ← Policy Critic: IQL-based advisory offline-RL component
├── runtime/          ← Python backend (FastAPI, scan loop, analyzer, learning, DB)
├── interface/        ← React + TypeScript + Vite operator UI
├── contracts/        ← cross-domain schemas, registry, field mappings
├── integration/      ← adapter stubs, cross-domain tests, boundary enforcement
├── v6/               ← stub for legacy V6 config compatibility
├── train_pipeline.py ← end-to-end AlphaForge training pipeline
├── Dockerfile        ← containerized test environment
├── compose.yaml      ← Docker Compose for development
├── pyproject.toml    ← pip install -e . support
└── requirements.txt  ← pinned dependencies
```

## Quick Start

```bash
# Install
pip install -e .

# Run all tests (847)
make test-all

# Or manually
PYTHONPATH=alphaforge/src:v7/src python -m pytest lib/tests/ simulation/tests/ \
  integration/tests/ runtime/tests/ alphaforge/tests/ v7/tests/ policycritic/tests/ -q

# Docker
docker compose up --build
```

## Test Suite

| Suite | Count |
|---|---|
| `lib/tests/` | 182 |
| `simulation/tests/` | 73 |
| `integration/tests/` | 96 |
| `runtime/tests/` | 374 |
| `alphaforge/tests/` | 112 |
| `v7/tests/` | 6 |
| `policycritic/tests/` | 7 |
| **Total** | **847** |

## Domain Boundaries

| Domain | Imports | Forbidden Imports |
|---|---|---|
| `lib/` | nothing | v7, alphaforge, simulation |
| `simulation/` | lib | v7, alphaforge |
| `alphaforge/` | lib | simulation, v7 |
| `v7/` | lib | simulation (lazy importlib only) |
| `runtime/` | lib, v6 | alphaforge (via services) |
| `integration/` | nothing | simulation, alphaforge, v7 |

## Pipeline Status

AlphaForge P1–P9 complete (label builder → evaluation/monitoring).
End-to-end training: `python train_pipeline.py`.
