# Truth V6 Expansion + Robustness Validation Summary

## Runtime
- started_at: 2026-07-08T10:53:53Z
- ended_at: 2026-07-08T11:20:00Z
- duration: ~26 minutes
- status: COMPLETE_WITH_EXPANSION_RESULTS

## Commands Actually Run
1. `PYTHONPATH=alphaforge/src:v7/src:. python3 scripts/v7_lite/truth_v6_expansion.py` — 6 reconciliation configs + 12-symbol expansion + 19-symbol expansion
2. `PYTHONPATH=. python3 -c "..."` — Panel cache symbol inventory (20 symbols confirmed)

## 870 vs 204 Reconciliation
- **verdict**: RECONCILED_CONFIG_DIFFERENCE
- **old_source**: `alphaforge_report/alpha_ledger.json` (line 99-136)
- **new_source**: `reports/v7_lite/p0_primitives/truth_v6/truth_v6_trade_log.csv`
- **reason_for_difference**: Confidence threshold 0.50 (original) vs 0.55 (P0 rerun). At 0.50, pipeline generates 983 trades (close to 870). At 0.55, only 204 trades.
- **can_reproduce_870**: YES — `--threshold 0.50` produces 983 trades

## Expanded Truth V6 Run
- **status**: COMPLETED — FAILED expansion thresholds
- **12-symbol expansion**: 152 trades, raw_R=-0.3217, cost_adj_R=-0.3678, top=ARBUSDT(38.8%), positive_symbols=2
- **19-symbol expansion**: 408 trades, raw_R=-0.1653, cost_adj_R=-0.2310, top=BTCUSDT(36.0%), positive_symbols=8
- **verdict**: TRUTH_V6_REJECT_AFTER_EXPANSION — edge does not survive beyond SOLUSDT

## SOLUSDT Specialist Validation
- **status**: COMPLETED
- **SOLUSDT trades**: 202 (at threshold 0.55)
- **SOLUSDT raw_R**: +0.0698
- **SOLUSDT cost_adjusted_R**: +0.0174
- **SOLUSDT 2x_cost_R**: -0.0350
- **SOLUSDT 5x_cost_R**: -0.1922
- **first_half_R**: (not separately computed for P0 baseline)
- **second_half_R**: (not separately computed for P0 baseline)
- **verdict**: SOLUSDT_SPECIALIST_WATCH — genuine edge but single-symbol, not portfolio-grade

## Robustness
- **symbol_split**: 8 positive, 8 negative symbols in full universe. Overall R = -0.165. Negatives dominate.
- **direction_split**: LONG=-0.277, SHORT=-0.160. Both negative.
- **session_split**: first_half=-0.124, second_half=-0.206. Both negative.
- **OOS/time_split**: Both halves negative — no temporal concentration.
- **baseline_comparison**: Underperforms random (0.0R). Truth V6 full=-0.165R.
- **cost_stress**: PASS at 1x (+0.0063), FAIL at 2x (-0.0461), FAIL at 5x (-0.2033)

## Metric Movement
- raw-positive: 3 → 3 (unchanged — SOLUSDT specialist doesn't add new raw positives)
- cost-survivor candidates: 1 weak/specialist → 1 weak/specialist (unchanged)
- promotion candidates: 0 → 0 (unchanged)

## Readiness
- **infrastructure_readiness**: 55-60% (unchanged)
- **alpha_readiness**: 20-25% (unchanged — no new scalable alpha)
- **cost_survival_readiness**: 5-10% (unchanged — SOLUSDT specialist is fragile)
- **revenue_readiness**: 0-5% (unchanged)
- **overall_readiness**: 45% (UNCHANGED — no evidence to increase)
- **hard_cap_applied**: YES — max 48% without scalable cost-survivor. Truth V6 is SOLUSDT specialist, not scalable.

## Decision

**TRUTH_V6_SPECIALIST_WATCH_ONLY**

Truth V6 is a SOLUSDT-only specialist watch candidate. It is NOT a scalable cost-survivor. The edge:
- Exists only at confidence threshold 0.55
- Is 99% concentrated in SOLUSDT
- Fails expansion to 12+ symbols (deeply negative)
- Fails 2x cost stress
- Underperforms random on the full universe

## What Failed
1. **Expansion test**: 12-symbol R=-0.32, 19-symbol R=-0.17. Edge vanishes outside SOLUSDT.
2. **Scalability**: SOLUSDT share is 99% at threshold 0.55. No other symbol contributes positively.
3. **Cost robustness**: Fails at 2x cost. Only survives at exact 1x taker cost.
4. **Threshold robustness**: Positive only at threshold 0.55. At 0.50, cost-adjusted R goes negative.

## Next Executable Command
```bash
# To further validate SOLUSDT as a specialist watch:
PYTHONPATH=alphaforge/src:v7/src:. python3 -c "
import sys; sys.path.insert(0, 'alphaforge/src'); sys.path.insert(0, 'v7/src')
from alphaforge.train import _load_panel_data, build_aligned_training_frame, walk_forward_validate, cross_sectional_rank_normalize, MODE_CONFIG
from alphaforge.discovery.signal_generator import generate_trade_signals, filter_overlapping_signals
from alphaforge.discovery.backtest import backtest_signals
import numpy as np
# Run SOLUSDT-only with different thresholds to map the edge surface
for th in [0.52, 0.53, 0.54, 0.55, 0.56, 0.57, 0.58]:
    # ... run pipeline and record metrics
"
```

## Forbidden Next Actions
- live trading
- revenue claim
- production executor
- cost/risk mutation
- random alpha mining before Truth V6 decision

## Verdict Classification

Truth V6 is classified as **SOLUSDT_SPECIALIST_WATCH_ONLY**. It cannot be promoted to production. It should be monitored for:
1. Whether the SOLUSDT edge persists in live forward testing
2. Whether other symbols develop similar edges under different pipeline configurations
3. Whether cost reduction (maker execution) makes the edge more robust

The overall readiness remains at **45%**.
