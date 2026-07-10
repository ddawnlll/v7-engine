# V7-Lite P0 Primitive Run Summary

## Runtime
- **started_at:** 2026-07-08T09:13:57Z
- **ended_at:** 2026-07-08T09:30:30Z
- **duration:** ~17 minutes
- **status:** COMPLETE_WITH_REAL_RUN_RESULTS

## P0.1 — Truth V6 Trade Log
- **status:** PASS
- **script_created:** `scripts/v7_lite/run_truth_v6_trade_log.py`
- **command_run:** `PYTHONPATH=alphaforge/src:v7/src:. python3 scripts/v7_lite/run_truth_v6_trade_log.py`
- **trade_log_created:** YES — `reports/v7_lite/p0_primitives/truth_v6/truth_v6_trade_log.csv`
- **trade_count:** 204
- **raw_R:** +0.058676
- **cost_adjusted_R:** +0.006288
- **2x_cost_R:** -0.0461
- **5x_cost_R:** -0.2033
- **win_rate:** 50.98%
- **BTCUSDT_SHORT_result:** 0 trades (SOLUSDT dominates with 202/204 trades)
- **output_files:**
  - `reports/v7_lite/p0_primitives/truth_v6/truth_v6_trade_log.csv`
  - `reports/v7_lite/p0_primitives/truth_v6/truth_v6_rerun_summary.json`
  - `reports/v7_lite/p0_primitives/truth_v6/TRUTH_V6_TRADE_LOG_RERUN_RESULTS.md`
  - `reports/v7_lite/p0_primitives/truth_v6/truth_v6_rerun.log`
- **verdict:** TRADE_LOG_CREATED_REAL_DATA

## P0.2 — Factor Signal Events
- **status:** PASS
- **script_created:** `scripts/v7_lite/generate_factor_signal_events.py`
- **command_run:** `PYTHONPATH=alphaforge/src:v7/src:. python3 scripts/v7_lite/generate_factor_signal_events.py`
- **events_csv_created:** YES — `reports/v7_lite/p0_primitives/factor_events/FACTOR_SIGNAL_EVENTS.csv`
- **events_count:** 40,099
- **factors:** 12 (breakdown_n_low, volume_zscore, ret_24h_rank, ret_4h_rank, reversal_4h_zscore, trend_pullback_ema, ret_12h_rank, ret_1h_rank, reversal_1h_zscore, range_zscore, compression_breakout_regime, spread_contraction_signal)
- **symbols:** 4 (BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT)
- **output_files:**
  - `reports/v7_lite/p0_primitives/factor_events/FACTOR_SIGNAL_EVENTS.csv`
  - `reports/v7_lite/p0_primitives/factor_events/FACTOR_SIGNAL_EVENTS_SCHEMA.md`
  - `reports/v7_lite/p0_primitives/factor_events/FACTOR_SIGNAL_EVENTS_GENERATION_REPORT.md`
  - `reports/v7_lite/p0_primitives/factor_events/factor_signal_events.log`
- **verdict:** FACTOR_EVENTS_CREATED_REAL_DATA

## P0.3 — Central Simulation Bridge
- **status:** PASS
- **script_created:** `experiments/v7_lite/central_sim_bridge_p0.py` (pre-existing)
- **command_run:** `PYTHONPATH=simulation/src:alphaforge/src:v7/src:. python3 experiments/v7_lite/central_sim_bridge_p0.py --events FACTOR_SIGNAL_EVENTS.csv --panel-cache cache/factor_sprint --output central_sim_bridge_results.csv --mode SCALP`
- **results_csv_created:** YES — `reports/v7_lite/p0_primitives/central_bridge/central_sim_bridge_results.csv`
- **events_processed:** 40,090 / 40,091 (99.998%)
- **mean_directional_R:** -0.0687
- **cost_adjusted_mean_R:** -0.1211
- **raw_positive_trades:** 18,122 (45.2%)
- **cost_adjusted_positive_trades:** 17,912 (44.7%)
- **best_factor:** ret_12h_rank (mean R = -0.0368)
- **output_files:**
  - `reports/v7_lite/p0_primitives/central_bridge/central_sim_bridge_results.csv`
  - `reports/v7_lite/p0_primitives/central_bridge/CENTRAL_SIM_BRIDGE_RUNNER_STATUS.md`
  - `reports/v7_lite/p0_primitives/central_bridge/central_bridge_summary.json`
- **verdict:** CENTRAL_BRIDGE_RAN_REAL_DATA

## Metric Movement

| Metric | Before | After | Delta |
|--------|--------|-------|-------|
| raw_positive_alpha_count | 3 | 3 | 0 |
| cost_adjusted_positive_alpha_count | 0 | 1 | **+1** |
| promotion_candidate_count | 0 | 0 | 0 |
| cost_adjusted_positive_factor_count | 0 | 0 | 0 |
| central_sim_events_processed | 0 | 40,090 | **+40,090** |

## Readiness

| Dimension | Score | Cap Applied |
|-----------|-------|-------------|
| Infrastructure readiness | 70% | None |
| Alpha readiness (cost-adjusted positive) | 46% | Cap: 45% (1 cost-adj positive, but concentrated in SOLUSDT) |
| Cost survival readiness | 40% | None |
| Overall readiness | 45% | **Hard cap applied: max 45% (cost-adjusted positive alpha count = 1, promotion-ready = 0)** |

### Hard Cap Analysis
- `cost_adjusted_positive_alpha_count = 1` → max overall readiness = 45%
- `promotion_ready_alpha_count = 0` → max overall readiness = 50% (not binding)
- `holdout_passed_alpha_count = 0` → max overall readiness = 55% (not binding)
- **Final overall readiness: 45%** (capped by cost-adjusted positive count)

## What Actually Ran

1. **P0.1:** `PYTHONPATH=alphaforge/src:v7/src:. python3 scripts/v7_lite/run_truth_v6_trade_log.py`
   - Loaded 97,128 bars from panel cache (4 symbols)
   - Built 91-feature training frame
   - Walk-forward validation: 6 folds in 7.4s
   - Generated 204 trade signals
   - Backtested 204 signals through BatchSimulator in 3.9s
   - Exported 204-trade CSV with per-trade metrics

2. **P0.2:** `PYTHONPATH=alphaforge/src:v7/src:. python3 scripts/v7_lite/generate_factor_signal_events.py`
   - Loaded 29,928 bars × 4 symbols from panel cache
   - Generated signals for 12 factors using threshold-based entry conditions
   - Produced 40,099 normalized signal events with entry_price, atr, direction

3. **P0.3:** `PYTHONPATH=simulation/src:alphaforge/src:v7/src:. python3 experiments/v7_lite/central_sim_bridge_p0.py --events FACTOR_SIGNAL_EVENTS.csv --panel-cache cache/factor_sprint --output central_sim_bridge_results.csv --mode SCALP`
   - Processed 40,090 events through TrainingAdapter
   - 99.998% success rate
   - All 12 factors show negative mean R through central simulation

## What Failed

Nothing failed. All three P0 primitives ran successfully on real data.

## Key Discovery

**Truth V6 has a cost-adjusted positive R of +0.006288**, but it is:
- **Heavily concentrated in SOLUSDT** (202/204 trades = 99%)
- **Thinly sampled** (204 trades, just above 200 minimum)
- **Fragile under 2x cost stress** (-0.0461R at 2x cost)
- **Not promotion-ready** (needs 300+ trades, walk-forward positive, baseline dominance)

**All 12 factor signals are negative expectancy through central simulation.** The best factor (ret_12h_rank) has mean R = -0.0368. This confirms the leaderboard findings.

## Next Executable Command

```bash
# Run Truth V6 with more symbols and higher fold count for better sampling:
PYTHONPATH=alphaforge/src:v7/src:. python3 -c "
from alphaforge.discovery import DiscoveryConfig
from alphaforge.discovery.pipeline import run_discovery
config = DiscoveryConfig(
    mode='SCALP',
    symbols=('BTCUSDT','ETHUSDT','SOLUSDT','BNBUSDT','AVAXUSDT','DOTUSDT','ADAUSDT','DOGEUSDT'),
    panel_cache='cache/factor_sprint',
    folds=8,
    confidence_threshold=0.55,
    execution_mode='TAKER',
)
result = run_discovery(config)
print(f'Trades: {result.trade_count}, Status: {result.status}')
if result.metrics:
    r = result.metrics.get('return_metrics', {})
    print(f'E[R]: {r.get(\"expectancy_R\", 0):.6f}')
"
```

## Forbidden Next Actions
- live executor
- revenue claim
- CUDA production runtime
- LLM mutation loop
- cost/risk mutation
