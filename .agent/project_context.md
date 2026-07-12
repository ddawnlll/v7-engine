# V7 Engine — Agent Project Context

> **Purpose:** This file provides a dense, AI-readable summary of the V7 Engine project.
> Every AI agent entering this repository reads this file before touching any code.
>
> **Source of truth:** This file is maintained alongside the codebase. When code and docs
> conflict, code wins but docs must be updated.

## What Is This?

V7 Engine is a **quantitative trading research and production monorepo**. It covers:
1. **Market data ingestion** — Binance OHLCV, funding rates via `lib/`
2. **Feature engineering** — Indicators, microstructure features, regime detection
3. **Simulation** — Economic truth layer with fee/slippage/horizon semantics
4. **Alpha discovery** — XGBoost-based alpha models via AlphaForge
5. **Policy-driven execution** — V7 pipeline with mode-specific policies
6. **Runtime** — Python backend (FastAPI), scan loop, analyzer, learning layer
7. **Interface** — React + TypeScript operator UI

## Centralized Training Entrypoint (ISSUE #319)

All production training MUST route through one of these entrypoints:
- **Primary:** `alphaforge.train.main()` — called via `PYTHONPATH=alphaforge/src:. python3 -m alphaforge.train`
- **Legacy (deprecated):** `cli.real_training.main()` — transitional, will be removed

**Config loader:** `lib.config_training.load_training_config(mode)` provides the single
source of truth for training parameters, merging:
- `simulation.profile_registry.registry.get_profile(mode)` — canonical stop/target/horizon
- `configs/training.yaml` — training scope, feature groups, hyperparameters

**Rule:** Any module importing `xgboost` / calling `.fit()` / writing to `data/models/`
OUTSIDE the `alphaforge/src/alphaforge/` domain violates the centralized entrypoint rule.

## Quick Reference

| Command | What it does |
|---------|-------------|
| `make research MODE=SCALP` | Research build via centralized alphaforge.train |
| `make full MODE=SCALP` | Full build via centralized alphaforge.train |
| `make test-training` | Test training + verify + passport check |
| `make train` | Wired to alphaforge.train (was no-op) |
| `python3 -m pytest alphaforge/tests/test_training_entrypoint.py` | Import-boundary check |

## More Info

See `docs/project_context.md` for the full project context.
See `.agent/CONTEXT_INDEX.md` for the complete reading order.
