# Changelog: v1.1_review_hardened → v1.2_shared_lib_authority

## Summary

Added a focused `lib/` shared library for primitives with nearly identical usage between v7 and alphaforge. No dumping ground — only Binance data fetching, pure math indicators, basic cost formulas, and time utilities.

## Added

- **New phase: P0.5 — Shared Lib Foundation** — creates `lib/` with `market_data/`, `indicators/`, `costs/`, `time/`
- **New docs:** `lib/README.md`, `lib/market_data.md`
- **New schema:** `schemas/market_data_result_schema_v1.json`
- **New execution contract:** `execution_contracts/P0_5__contract.json`
- **New phase plan:** `phase_plans/P0_5__shared_lib_foundation.md`

## Changed

- **phase_index.md:** Added P0.5, updated dependency graph, reduced lib dependency map
- **manifest.json:** package_version → v1.2, phase_count → 11, added P0.5, added `lib_scope` section
- **hardening_review_fixes.md:** Added H5 with focused scope definition
- **ai_summary:** Section 4A rewritten with focused lib/ scope and clear inclusions/exclusions
- **configs/v7_alpha_defaults.json:** Added `shared_lib` config with focused scope
- **execution_checklist.md:** Added focused lib boundary checklist items
- **architecture diagram:** Cleaned up to show only what's truly shared
- **README.md:** Updated with focused lib/ description
- **phase_plans_combined.md:** Rebuilt with P0.5 included

## Hard Stops (3)

- `direct_binance_call_outside_lib` — Binance API call from v7/ or alphaforge/
- `lib_import_boundary_violation` — lib/ imports v7 or alphaforge
- `shared_everything_mistake` — putting regime, risk, IO, serialization, cache, or adapters in lib/

## What's NOT in lib/ (explicit)

- Regime enums/detectors — V7 uses for policy; alphaforge uses for features. Different semantics.
- R-multiple — V7 = ATR+mode truth; research = fixed%. Different things.
- IO utilities — each system writes output differently.
- Generic serialization — premature abstraction.
- Cache abstractions — each system caches differently.
- Adapters — owned by v7 and alphaforge respectively.

## v1.1 Hardening Preserved

- Fold-scoped anomaly fitting (H1)
- Deterministic/regime override visibility (H2)
- Symbol encoding future-proofing (H3)
- SCALP interval authority (H4)
