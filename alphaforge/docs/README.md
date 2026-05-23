# V7 AlphaForge XGB Package

This package contains the requested AI summary and executable phase plan set for the V7-compatible alpha generation model.

**Package version:** v1.2_shared_lib_authority

## Main files

- `ai_summary__v7_alphaforge_xgb.md` — dense AI summary, V7-style.
- `phase_index.md` — phase overview (11 phases: P0–P9 + P0.5).
- `model_name_recommendation.md` — recommended model name and artifact slugs.
- `shared_lib.md` — shared `lib/` architecture definition.
- `changelog_v1_1_to_v1_2.md` — changes from v1.1 to v1.2.
- `lib/` — documentation for the shared lib architecture.
- `phase_plans/` — 11 v2.5.1-style phase plans with Part 1-4 structure.
- `execution_contracts/` — extracted Part 3 JSON contracts per phase.
- `schemas/` — feature, label, prediction, regime context, and market data schemas.
- `configs/` — default mode/model config proposal.
- `diagrams/` — Mermaid diagrams.
- `checklists/` — execution and lib boundary checklists.

## Phase count

11 phases: P0 through P9 plus P0.5 (Shared Lib Foundation).

## Architecture

```
repo/
  lib/          → shared primitives (only where usage is nearly identical)
  v7/           → V7 semantic authority
  alphaforge/   → AlphaForge training/research authority
```

**lib/ scope (focused):**
- `lib/market_data/` — Binance client, klines/funding, standard schema
- `lib/indicators/` — ATR, returns, volatility (pure math)
- `lib/costs/` — Fee %, slippage estimation (basic formulas)
- `lib/time/` — Interval conversion, fold generation

**Not in lib/:** regime, R-multiple, IO, serialization, cache, adapters — these are owned by v7/ or alphaforge/.

## Recommended model name

**V7 AlphaForge XGB** (`v7_alphaforge_xgb`)

## Review Hardening v1.2

This package adds P0.5 (Shared Lib Foundation) with a focused scope.
Read `hardening_review_fixes.md` before executing any phase.
