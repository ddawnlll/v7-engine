# Factor Signal Events Generation Report

**Generated:** 2026-07-08T09:23:39Z

## Summary

- Total events: 40099
- Factors: 12
- Symbols: 4
- Elapsed: 55.4s

## Events per Factor

- breakdown_n_low: 7503
- ret_1h_rank: 5655
- ret_4h_rank: 4526
- volume_zscore: 3692
- trend_pullback_ema: 3495
- ret_12h_rank: 2994
- reversal_1h_zscore: 2708
- spread_contraction_signal: 2572
- ret_24h_rank: 2523
- reversal_4h_zscore: 1756
- range_zscore: 1409
- compression_breakout_regime: 1266

## Events per Symbol

- BNBUSDT: 10168
- SOLUSDT: 10135
- ETHUSDT: 10131
- BTCUSDT: 9665

## Direction Breakdown

- LONG: 32596
- SHORT: 7503

## Usage

Feed this CSV into the central simulation bridge:

```bash
PYTHONPATH=simulation/src:alphaforge/src:v7/src:. python3 experiments/v7_lite/central_sim_bridge_p0.py \
    --events /teamspace/studios/this_studio/v7-engine/reports/v7_lite/p0_primitives/factor_events/FACTOR_SIGNAL_EVENTS.csv \
    --panel-cache cache/factor_sprint/ \
    --output reports/v7_lite/p0_primitives/central_bridge/central_sim_bridge_results.csv
```
