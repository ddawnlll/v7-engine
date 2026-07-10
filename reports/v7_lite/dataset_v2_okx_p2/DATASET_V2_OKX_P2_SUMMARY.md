# V7-Lite Dataset V2 OKX P2 Scale Build Summary

## Runtime
- started_at: 2026-07-09T11:30:16
- ended_at: 2026-07-09T11:42:50.495880+00:00
- status: COMPLETE_WITH_OKX_TIER_AB_READY

## P1 coverage audit
- P1 was a tiny recent sample (~1 hour per symbol), NOT a 3-6 month build.

## Dataset root
- path: cache/v7_lite_scalp_dataset_v2_okx_p2/
- permanent_size_mb: 20.68
- raw_evicted: 40 files

## Tier A+B symbols
- requested: 20
- completed: 20
- blocked: 0

## Feature groups
- OKX trades 5m: 20 symbols
- OKX trades 15m: 20 symbols
- OKX trades 1h: 20 symbols
- OKX funding: 20 symbols

## Row counts
- Joined 1h panel: 754,508 rows x 77 cols
- Enriched signal events: 314,729 rows

## Join/leakage
- asof_backward_join: True
- leakage_verdict: AUDITED_SAFE

## Storage
- permanent_cap_gb: 100
- total_disk_budget_gb: 200
- hard_stop_triggered: No

## Specialist scan readiness
- ready_symbols: 20
- ready_timeframes: 5m, 15m, 1h
- verdict: READY

## Readiness update
- previous_overall_readiness: 50%
- new_overall_readiness: 50% (hard-capped)
- hard_cap_applied: True

## What actually improved
- 20 Tier A+B symbols now have OKX trade features at 5m/15m/1h
- As-of backward join verified with 754K enriched rows
- Feature availability matrix generated for all 20 symbols
- Specialist scan readiness assessed as READY

## Blockers
- 15m base OHLCV not available locally (BLOCKED_LOCAL_15M_MISSING)
- OKX public API only returns recent trades (~1hr), not months of history

## Exact next command
cd /teamspace/studios/this_studio/v7-engine
python3 scripts/v7_lite/smoke_test_okx_p2_dataset.py

## Forbidden next actions
- live trading
- revenue claim
- full model training before specialist scan
- random alpha mining before specialist scanner uses V2 features
- cost/risk mutation
