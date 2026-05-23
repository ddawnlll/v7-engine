# V7 AlphaForge Execution Checklist

## Preflight

- [ ] Confirm target branch and repository root.
- [ ] Confirm no hidden second simulator exists.
- [ ] Confirm v7 runtime simulation semantics are accessible through side-effect-free adapter.
- [ ] Confirm mode config matches SWING / SCALP / AGGRESSIVE_SCALP table.
- [ ] Confirm 20-symbol universe is liquid and stable.
- [ ] Confirm no random IID split is used for primary evaluation.
- [ ] Confirm Part 3 JSON contracts validate through `pi plan doctor`.

## Shared Lib Boundary (Focused)

- [ ] `lib/` exists with only: market_data/, indicators/, costs/, time/
- [ ] `lib/` does NOT import `v7.*` or `alphaforge.*`
- [ ] Binance client lives in `lib/market_data/binance/` — NOT in v7/ or alphaforge/
- [ ] ATR, returns, volatility live in `lib/indicators/` — pure math only
- [ ] Fee/slippage estimation lives in `lib/costs/` — basic formulas only
- [ ] Interval conversion and fold generation live in `lib/time/`
- [ ] No regime enums, detectors, or risk helpers in lib/
- [ ] No IO, cache, or serialization abstractions in lib/
- [ ] No adapters in lib/ (they belong to v7/ and alphaforge/)
- [ ] Import-boundary test passes: lib/ must not import v7 or alphaforge
- [ ] Hard stop `shared_everything_mistake` catches misplaced modules

## Safety

- [ ] No secrets touched.
- [ ] No `git push`.
- [ ] No raw destructive cleanup.
- [ ] Watch-mode validation forbidden.
- [ ] Worktree state persistence enabled for experimental_6 plans.
- [ ] Integration queue required for >3 workers.

## Model Readiness

- [ ] Feature schema versioned.
- [ ] Label schema versioned.
- [ ] Dataset family versioned.
- [ ] Model artifact versioned.
- [ ] Calibration artifact versioned.
- [ ] Policy artifact versioned.
- [ ] Predictions carry model_scope and mode.

## Evaluation

- [ ] Economic R metrics reported per mode.
- [ ] No-trade quality reported per mode.
- [ ] Calibration reliability reported per mode.
- [ ] Regression reliability reported per mode.
- [ ] Symbol stability reported.
- [ ] Regime stability reported.
- [ ] Baseline comparison included.

## Review hardening checklist

- [ ] No anomaly/regime/cluster model is fit on full history for training or evaluation.
- [ ] Every anomaly feature row carries fold-compatible anomaly artifact lineage.
- [ ] Dataset assembly rejects anomaly fit-window boundary violations.
- [ ] Regime policy influence appears in AnalysisResult.deterministic_interaction.
- [ ] Regime policy influence appears in DecisionEvent reason codes.
- [ ] Monitoring reports model-preferred no-trade vs regime-forced no-trade.
- [ ] Feature schema carries symbol_encoding_family and symbol_universe_version.
- [ ] SCALP resolves from config to primary=1h/context=4h/refinement=15m.
- [ ] No implementation hardcodes SCALP primary=15m.
- [ ] Import-boundary tests pass: lib must not import v7 or alphaforge.
- [ ] Import-boundary tests pass: v7/alphaforge must not call Binance outside lib adapter.
- [ ] Hard stop `direct_binance_call_outside_lib` is enforced.
- [ ] Hard stop `lib_import_boundary_violation` is enforced.
