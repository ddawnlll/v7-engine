# Phase 4f: Alpha #1 Artifact Freeze + Hash-Pin Guard

**Date:** 2026-07-06
**Issue:** #274
**Status:** COMPLETE

## Summary

Frozen Alpha #1 metadata in `contracts/registry.json` as `Alpha1FrozenArtifact` (v1.0.0). The 16 locked features and threshold=0.550 are pinned via a guard test that enforces contract integrity.

## What changed

1. **Registry entry** — Added `Alpha1FrozenArtifact` to `contracts/registry.json`:
   - `owner_domain`: alphaforge
   - `producers`: [alphaforge]
   - `consumers`: [runtime, alphaforge]
   - `schema_file`: null (metadata-only, no schema required)
   - `fixture_file`: null
   - `source_authority`: reports/alpha1_runtime_inference_architecture_decision.md

2. **Guard test** — Created `integration/tests/test_alpha1_artifact_guard.py` verifying:
   - Registry entry exists
   - Required fields present
   - 16-feature list matches exactly
   - Threshold 0.550 recorded and matches expected value

3. **ACCP report** — Created `reports/phase4f_alpha1_artifact_freeze.md` and `reports/phase4f_alpha1_artifact_freeze.accp.yaml`

## Frozen Alpha #1 Parameters

- **Features (16):** bb_position, ofi_N, atr_expansion_N, return_zscore_N, vwap_mid_deviation_N, trade_count_N, multi_level_obi_N, microprice_N, log_return_1, garman_klass_vol_N, doji_N, hammer_N, volume_trend_N, cusum_positive, rsi_N, parkinson_vol_N
- **Threshold:** 0.550
- **net_R:** 0.0043 CI=[0.0037, 0.0050]

## Verification

```bash
PYTHONPATH=. python3 -m pytest integration/tests/test_alpha1_artifact_guard.py -q
# 7 passed in 0.01s
```
