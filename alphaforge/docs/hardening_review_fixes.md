# V7 AlphaForge XGB — Review Hardening Addendum

## Purpose

This addendum closes the implementation-discipline gaps identified during architecture review. These are not optional improvements. They are hard invariants for the executable phase plans, schemas, config defaults, and Pi contracts.

## H1 — Fold-Scoped Anomaly Fitting

Every unsupervised component must be fitted strictly inside the active walk-forward fold's training window. This includes Isolation Forest, clustering, regime classifiers, anomaly scalers, PCA/autoencoder-like reducers, and any normalization used only by the anomaly context layer.

Rules:

- Fit anomaly/regime artifacts on `fold.train_start <= timestamp <= fold.train_end` only.
- Transform validation, holdout, replay, paper, and live rows with the fold-compatible fitted artifact.
- Store `anomaly_artifact_id`, `anomaly_fit_window_start`, `anomaly_fit_window_end`, `fold_id`, `dataset_family_version`, and `feature_schema_version` with every anomaly-derived feature row.
- Dataset assembly must reject any row where `row_timestamp <= anomaly_fit_window_end` is false for validation/holdout transforms, or where the anomaly artifact was fitted beyond the fold train boundary.
- A global full-history anomaly fit is forbidden for model training and evaluation.

## H2 — Deterministic / Regime Override Visibility

Regime-aware policy modifiers are allowed only when their influence is explicit in runtime surfaces.

Rules:

- AnalysisResult must expose `deterministic_interaction.regime_state`, `constraint_level`, `regime_policy_action`, and reason codes.
- DecisionEvent must snapshot `regime_gate_reason_codes`, including `regime_gate_forced_no_trade`, `regime_blocked_direction`, `regime_threshold_multiplier_applied`, and `regime_advisory_only`.
- Monitoring must report the fraction of NO_TRADE decisions that were model-preferred versus regime-forced.
- A regime HARD_BLOCK is allowed only if policy config explicitly permits it and lifecycle records make it reviewable.

## H3 — Symbol Encoding Future-Proofing

One-hot symbol encoding is accepted only as the MVP encoding family. It is not a permanent architecture assumption.

Rules:

- Feature schema must include `symbol_encoding_family` and `symbol_universe_version`.
- MVP uses `symbol_one_hot_v1` over the approved 20-symbol universe.
- Adding/removing symbols materially requires a feature schema or encoding-family version bump.
- Future encoding families such as `symbol_target_encoding_v1` or learned embedding-derived features must swap at the feature layer without changing simulation, label, request/result, or lifecycle contracts.

## H4 — SCALP Interval Authority

SCALP interval authority is config-driven and must not be hardcoded.

Authoritative defaults:

```text
SWING: primary=4h, context=1d, refinement=1h
SCALP: primary=1h, context=4h, refinement=15m
AGGRESSIVE_SCALP: primary=15m, context=1h, refinement=5m
```

Rules:

- Any mention of SCALP primary interval as `15m` is incorrect unless it explicitly refers to `AGGRESSIVE_SCALP` or SCALP refinement.
- Simulation profile, label horizon family, dataset assembly, feature builder, and inference router must resolve intervals from central config only.
- Hardcoded interval literals in code are forbidden outside tests and config fixtures.

## H5 — Shared Lib Foundation (Focused)

A minimal `lib/` directory exists for primitives that are **nearly identical usage** between `v7/` and `alphaforge/`. 

### Scope

**In lib/:**
- `lib/market_data/binance/` — Binance HTTP client, klines/funding service, standard schema
- `lib/indicators/` — ATR, returns, volatility, rolling window (pure math)
- `lib/costs/` — Fee %, slippage estimation (basic formulas)
- `lib/time/` — Interval conversion, fold generation (temporal logic)

**Not in lib/:**
- Regime enums/detectors — V7 uses for policy, alphaforge uses for features. Different semantics.
- R-multiple — V7 = ATR+mode truth; research = fixed%. Different things.
- IO utilities, generic serialization, cache abstractions — each system differs.
- Adapters — owned by v7/ and alphaforge/ respectively.

### Rules

- `lib/` is NOT V7 and NOT AlphaForge. Only shared primitives.
- Moving a primitive to `lib/` does NOT move V7 semantic authority to `lib/`.
- `lib/` must NOT import `v7.*` or `alphaforge.*`.
- Direct Binance API calls from `v7/` or `alphaforge/` are FORBIDDEN.
- No V7 simulation truth, policy logic, or alphaforge fold-fitting in `lib/`.
- V7 regime influence must be visible in `AnalysisResult.deterministic_interaction`.
- Semantic changes to shared primitives affecting labels/evaluation must bump version lineage.

## Implementation Status

These fixes are incorporated into:

- `ai_summary__v7_alphaforge_xgb.md`
- `lib/docs/README.md`
- `lib/docs/market_data.md`
- `configs/v7_alpha_defaults.json`
- `lib/docs/schemas/market_data_result_schema_v1.json`
- `phase_plans/P0_5__shared_lib_foundation.md`
- `execution_contracts/P0_5__contract.json`
- `checklists/execution_checklist.md`
- `manifest.json`
