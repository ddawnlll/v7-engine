# V7-Lite Dataset V2 P0 Smoke Build Summary

## Runtime
- started_at: 2026-07-09T10:21:22.797549+00:00
- ended_at: 2026-07-09T10:21:35.512855+00:00
- status: PARTIAL_WITH_OKX_READY

## Provider reachability
- OKX: True
- Bybit: False
- Binance REST: DISABLED (HTTP 451 risk)
- Binance local cache: PASS

## Dataset root
- path: /teamspace/studios/this_studio/v7-engine/cache/v7_lite_scalp_dataset_v2_p0_smoke
- permanent_size_mb: 1.46
- staging_peak_mb: 0.26

## Feature groups
- Binance local OHLCV: PASS
- OKX trades features: 0 symbols
- OKX funding: AVAILABLE
- Bybit OI: UNAVAILABLE
- Bybit funding: UNAVAILABLE

## Join/leakage
- asof_backward_join: True
- enriched_sample_rows: 168

## Readiness update
- previous_overall_readiness: 49%
- new_overall_readiness: 49.5%
- hard_cap_applied: True (no scalable cost survivor)

## Exact next executable command
```
cd /teamspace/studios/this_studio/v7-engine
python3 scripts/v7_lite/smoke_test_dataset_v2.py
```

## Forbidden next actions
- live trading
- revenue claim
- full dataset build before P0 smoke passes
- model training before feature store validation
- random alpha mining before V2 join smoke test
- cost/risk mutation
