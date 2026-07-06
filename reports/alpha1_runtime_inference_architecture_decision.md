# Alpha #1 Runtime Inference Architecture Decision

## 1. Executive Summary

This is a **design-only** task.

The target is **not**:

- `runtime/` importing the whole `alphaforge/` research tree
- reusing `runtime/services/incremental_indicators.py` as the live Alpha #1 feature engine
- allowing the live path to swap between OHLCV proxies and real orderbook semantics feature-by-feature

The target **is**:

- `alphaforge/` remains the alpha discovery authority
- a **frozen, side-effect-free Alpha #1 inference package** is promoted into `lib/`
- `runtime/` consumes that frozen package as a read-only dependency
- model loading is file-based and hash-pinned against a canonical registry entry
- live feature computation matches the batch research formulas exactly on closed candles before shadow mode starts

## 2. Capability Map

## 2.1 What exists today

| Capability | Current location | Status | Problem |
|---|---|---|---|
| Alpha discovery / training | `alphaforge/src/alphaforge/` | DONE | research-only surface |
| Locked Alpha #1 handoff metadata | `alphaforge/docs/discovered_alphas/SCALP_bb_position_mean_reversion_v1.json` | DONE | no runtime serving path |
| Batch feature computation | `alphaforge/src/alphaforge/features/pipeline.py`, `orderbook.py`, `candle_pattern.py`, `regime.py` | DONE | not packaged for runtime inference |
| Runtime analyzer indicators | `runtime/services/incremental_indicators.py` | EXISTS | mathematically different from Alpha #1 batch formulas in warmup, ATR, RSI, Bollinger, and proxy microstructure |
| Runtime model loader for Alpha #1 | none | MISSING | no frozen artifact contract/guard at runtime |
| Runtime inference contract | none | MISSING | no canonical AlphaRunner input/output object |

## 2.2 Authority conclusion

The correct boundary is:

- **AlphaForge owns** feature definitions, model artifact lineage, and the meaning of the Alpha #1 signal.
- **lib owns** the frozen, side-effect-free inference primitives reused by AlphaForge export and runtime consumption.
- **runtime owns** scheduling, candle intake, shadow logging, artifact verification at load time, and operator-facing lifecycle behavior.

This keeps the dependency direction valid:

- `lib/` imports nothing from `alphaforge/`, `simulation/`, or `v7/`
- `alphaforge/` may export into `lib/` at freeze time
- `runtime/` consumes `lib/` without depending on the AlphaForge research tree directly

## 3. Option Analysis

## 3.1 Option A — runtime imports a frozen package directly from `alphaforge/`

### Pros

- less immediate code movement
- batch and live formulas stay physically close to research code

### Cons

- runtime would depend on the AlphaForge research tree, not just a frozen serving surface
- AlphaForge docs explicitly treat `runtime/` as downstream lifecycle, not as a consumer of research internals
- the runtime import surface would be too wide: training helpers, experiment code, and serving code would live under one namespace
- future refactors in AlphaForge could silently break runtime inference

### Verdict

Reject.

## 3.2 Option B — promote a frozen inference package into `lib/`

### Pros

- dependency direction stays clean
- serving code becomes explicitly side-effect-free and stable
- runtime consumes only the minimal serving surface
- parity harness can compare `alphaforge` batch formulas vs `lib` frozen inference formulas directly
- later paper/live paths reuse the same package without importing research scaffolding

### Cons

- requires one-time extraction/freeze work
- AlphaForge batch code and frozen serving code must stay version-linked through a manifest

### Verdict

Recommend **Option B**.

## 3.3 Recommended package shape

Proposed frozen package under `lib/alpha1_inference/`:

```text
lib/alpha1_inference/
  feature_spec.py           # locked 16-feature names and order
  feature_engine.py         # pure closed-candle incremental state machine
  artifact_loader.py        # file-based + hash-verified loader helper
  model_bundle.py           # typed metadata wrapper
```

Rules:

- no training code
- no experiment helpers
- no runtime DB / API code
- no simulation imports
- deterministic closed-candle inputs only

## 4. Loader Contract

Recommended loader signature:

```python
class FrozenAlpha1BundleLoader:
    def load(
        self,
        *,
        artifact_path: str,
        expected_model_sha256: str,
        expected_manifest_sha256: str,
        expected_threshold: float,
    ) -> FrozenAlpha1Bundle:
        ...
```

`FrozenAlpha1Bundle` should contain:

- `model`: loaded XGBoost booster/classifier
- `model_sha256`: exact binary hash
- `feature_manifest`: ordered 16-feature manifest
- `feature_manifest_sha256`: manifest hash
- `confidence_threshold`: locked `0.550`
- `model_artifact_id`
- `training_run_id`
- `feature_set_id`
- `label_dataset_id`
- `source_commit`

Load-time rules:

- fail closed on any hash mismatch
- fail closed if ordered feature names differ
- fail closed if threshold differs from the frozen contract
- do not auto-discover the newest artifact

## 5. AlphaRunner Contract Surface

The missing runtime-facing contract is not the existing AlphaForge `ModelArtifact` metadata object. `ModelArtifact` describes lineage; AlphaRunner also needs an **inference request/result** boundary.

Recommended new registry entries:

### A. `AlphaInferenceRequest`

- **owner_domain:** `alphaforge`
- **producer:** `runtime`
- **consumer:** `runtime`, `alphaforge`

Required fields:

- `symbol`
- `decision_timestamp`
- `mode`
- `primary_interval`
- `feature_vector`: object keyed by the locked 16 feature names
- `feature_order`: ordered list of the 16 feature names
- `feature_schema_version`
- `feature_manifest_sha256`
- `market_data_lineage`
- `adapter_kind`: `SHADOW` for this milestone path

### B. `AlphaInferenceResult`

- **owner_domain:** `alphaforge`
- **producer:** `runtime`
- **consumer:** `runtime`, later `v7`

Required fields:

- `symbol`
- `decision_timestamp`
- `mode`
- `recommended_action`: `LONG_NOW | SHORT_NOW | NO_TRADE`
- `confidence`
- `class_probabilities`
- `confidence_threshold_applied`
- `model_artifact_id`
- `model_sha256`
- `feature_manifest_sha256`
- `feature_schema_version`
- `adapter_kind`
- `lineage`: `training_run_id`, `feature_set_id`, `label_dataset_id`, `source_commit`

Boundary rule:

- this is **signal evidence**, not execution permission
- no order payloads, no broker permissions, no kill-switch overrides

## 6. 16-Feature Incremental-vs-Batch Mapping

The live path must compute features from the same **closed 1h candles** used by research. For Alpha #1, "more real-time" is **not** automatically better if it changes semantics.

| Locked feature | Batch source | Required live/incremental equivalent | Parity status | Current runtime status |
|---|---|---|---|---|
| `bb_position` | `pipeline.compute_bb_position()` | rolling SMA(20) + rolling std(ddof=1, 20) on closed 1h bars, then `(close-lower)/(upper-lower)` | EXACT required | current runtime Bollinger path uses `min_periods=1`; not identical |
| `ofi_N` | `orderbook.compute_ofi()` | same OHLCV-derived up/down volume proxy and same windowed normalization | EXACT required | no exact runtime equivalent |
| `atr_expansion_N` | `pipeline.compute_atr_expansion()` | ATR from simple rolling mean of true range, then `ATR / SMA(ATR, window)` | EXACT required | runtime uses EWM ATR + 5-bar avg flag; not identical |
| `return_zscore_N` | `pipeline.compute_return_zscore()` | same 1-bar log returns, rolling mean/var(ddof=1), same zero-std fallback | EXACT required | runtime has return zscore-ish fields only indirectly; not exact |
| `vwap_mid_deviation_N` | `orderbook.compute_vwap_to_mid_deviation()` | same rolling VWAP vs midpoint proxy on closed candles | EXACT required | runtime `vwap` / `price_vs_vwap` differ semantically |
| `trade_count_N` | `orderbook.compute_trade_count()` | same trade-count proxy formula and window | EXACT required | runtime `trade_intensity` differs semantically |
| `multi_level_obi_N` | `orderbook.compute_multi_level_obi()` | same synthetic multi-level OBI proxy from OHLCV + volume | EXACT required | no runtime equivalent |
| `microprice_N` | `orderbook.compute_microprice()` | same OHLCV proxy microprice, not real L1 microprice | EXACT required | no exact runtime equivalent |
| `log_return_1` | `pipeline.compute_log_return_1()` | same 1-bar log return from closed bars | EXACT required | runtime computes compatible raw log return |
| `garman_klass_vol_N` | `pipeline.compute_garman_klass_vol()` | same rolling estimator on open/high/low/close with same window | EXACT required | no runtime equivalent |
| `doji_N` | `candle_pattern.compute_candle_pattern_group()` | same rolling fraction of doji candles with same threshold and window | EXACT required | no runtime equivalent |
| `hammer_N` | `candle_pattern.compute_candle_pattern_group()` | same rolling fraction of hammer/shooting-star candles with same window | EXACT required | no runtime equivalent |
| `volume_trend_N` | `pipeline.compute_volume_trend()` | same rolling linear-regression slope over volume | EXACT required | runtime `vol_slope` is ratio slope, not same formula |
| `cusum_positive` | `regime.OnlineRegimeFeatures.update()` | same stateful positive CUSUM accumulator and reset semantics | EXACT required | no runtime equivalent |
| `rsi_N` | `pipeline.compute_rsi()` | same Wilder RSI with same warmup | EXACT required | runtime RSI warmup/fill semantics differ |
| `parkinson_vol_N` | `pipeline.compute_parkinson_vol()` | same rolling high/low estimator with same window | EXACT required | no runtime equivalent |

## 6.1 Highest-risk mismatches

1. `bb_position`
- Dominates 97.3% of model reliance.
- Current runtime Bollinger computation is not mathematically identical because it starts early (`min_periods=1`) and uses a different rolling implementation path.

2. OHLCV-proxy microstructure features
- `ofi_N`, `multi_level_obi_N`, `microprice_N`, `vwap_mid_deviation_N`, `trade_count_N` were trained as **OHLCV-derived proxies**, not real orderbook/tick features.
- Replacing them with "better" live market microstructure would break parity with the trained artifact.

3. `atr_expansion_N` and `rsi_N`
- Runtime currently computes ATR/RSI differently for analyzer purposes.
- Those analyzer fields must not be reused for Alpha #1 inference.

## 6.2 Warmup rules

The frozen inference engine must expose warmup readiness explicitly.

- Before a feature's required lookback is satisfied, the engine returns `not_ready`
- AlphaRunner emits no inference result until all 16 features are ready
- Warmup semantics must match the batch path exactly, not be NaN-filled differently at runtime

## 7. Recommended Implementation Order

1. Freeze the exact Alpha #1 artifact + ordered feature manifest + threshold into a hash-pinned bundle
2. Extract the 16-feature serving formulas into `lib/alpha1_inference/`
3. Build the batch-vs-lib parity harness
4. Only after parity passes: wire AlphaRunner shadow mode to the frozen lib bundle

## 8. Final Decision

**Recommended decision:** promote a frozen Alpha #1 serving package into `lib/`, not a direct `runtime -> alphaforge` import.

This satisfies the repo boundary rules and prevents the most likely failure mode in this milestone: live feature drift caused by runtime reinterpreting research formulas through its existing analyzer indicator stack.
