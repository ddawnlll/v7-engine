# V7-Lite AlphaForge Validation Accelerator Reports

**Generated:** 2026-07-08
**Run type:** Autonomous 2-hour readiness push
**Mission:** Move V7-Lite AlphaForge readiness as far as possible toward 60+%

## Directory Structure

```
reports/v7_lite/
  README.md                                          ← this file
  V7_LITE_COMPLETION_GATE_v0_2.md                    ← updated gate report
  V7_LITE_COMPLETION_GATE_v0_2.yaml                   ← gate data

  truth_v6/
    TRUTH_V6_DISSECTION_REPORT.md                    ← PARTIAL (trade data missing)
    truth_v6_trade_distribution.csv                   ← EMPTY (data not available)
    TRUTH_V6_COST_RESCUE_REPORT.md                    ← WATCH verdict
    truth_v6_cost_survivability.json                  ← cost scenarios
    BASELINE_DOMINANCE_REPORT.md                      ← PARTIAL (no trade data)
    truth_v6_split_report.csv                          ← EMPTY (data not available)

  outcome_cache/
    CPU_OUTCOME_CACHE_SCHEMA.md                       ← schema designed
    OUTCOME_CACHE_P0_PLAN.md                          ← implementation plan
    SIMULATION_PARITY_BENCHMARK_PLAN.md                ← parity targets defined

  ledger/
    experiments.jsonl                                  ← run log
    run_summary.md                                     ← run summary

  cuda/
    CUDA_FEASIBILITY_REPORT.md                        ← CUDA already tested, slower
    CUDA_P0_KERNEL_DESIGN.md                          ← kernel design
    CUDA_VS_CPU_BENCHMARK_PLAN.md                     ← benchmark plan
```

## Scope

This run focuses on:

1. Truth V6 trade distribution dissection — **BLOCKED by missing trade-level data**
2. Cost survivability analysis — **PARTIAL (used estimated costs)**
3. Regime/symbol/session split reports — **BLOCKED by missing trade-level data**
4. Baseline dominance report — **PARTIAL (aggregate metrics only)**
5. CPU outcome cache schema + plan — **COMPLETE**
6. Simulation parity benchmark plan — **COMPLETE**
7. V7-Lite Completion Gate v0.2 update — **COMPLETE**
8. CUDA feasibility report — **COMPLETE (CUDA already exists, 2-3x slower than CPU)**

## Key Findings

| Area | Status | Verdict |
|------|--------|---------|
| Truth V6 trade data | BLOCKED | No individual trade records exist in repo |
| Cost survivability | PARTIAL | Best estimate: cost-adjusted R = -0.01R |
| Outcome cache schema | COMPLETE | Schema defined, ready for P0 build |
| Simulation parity plan | COMPLETE | 6 parity targets defined |
| CUDA feasibility | NOT_NEEDED | CUDA exists and is 2-3x slower than CPU |
| Completion gate | UPDATED | 37% → TBD new score |

## Data Availability

The `run-alpha-truth-v6-20260707` run artifact is **not persisted** in this repo.
Only aggregated metrics exist in `alphaforge_report/alpha_ledger.json` and `reports/ALPHA_INVENTORY_FULL.csv`.
Individual trade-level R values, symbol-level breakdowns, and regime-level splits are unavailable.

See `TRUTH_V6_DISSECTION_REPORT.md` for the BLOCKED/required-data specification.

## Source Files Referenced

| File | Description |
|------|-------------|
| `reports/ALPHA_INVENTORY_FULL.csv` | 170-row alpha inventory |
| `reports/ALPHA_INVENTORY_REPORT.md` | Previous synthesis report |
| `alphaforge_report/alpha_ledger.json` | Alpha ledger with aggregated metrics |
| `scripts/backfill_alpha_ledger.py` | Ledger backfill script with Truth V6 specs |
| `simulation/docs/ai_summary.md` | Simulation authority |
| `simulation/docs/cost_model.md` | Cost model specification |
| `simulation/docs/cuda_migration_plan.md` | GPU/CUDA benchmark results |
| `reports/V7_LITE_COMPLETION_GATE_v0.2.md` | Prior gate report |
