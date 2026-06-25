# Training-Ready Quant Pipeline PlanSpec Bundle (v1 Repair)

Generated from V7 Engine Reality Gap Audit (24.5% readiness).
Repaired bundle — execution-safe, contradiction-free, schema-valid.

## Bundle Overview

| Plan | Domain | ACs | Title |
|------|--------|-----|-------|
| 00 | audit | 5 | Reality Gap Baseline Verification |
| 01 | lib | 11 | Market Data Backfill + Storage |
| 02 | simulation | 5 | Market Data Adapter + Batch + Persistence |
| 03 | ops | 6 | Pipeline CLI + Makefile + Runbook |
| 04 | lib+sim | 8 | Funding Pagination + Rate Limit |
| 05 | alphaforge | 10 | XGBoost Training Runner (GATED CONTROLLED) |
| 06 | alphaforge | 5 | Empirical WFV with Real Metrics (GATED) |
| 07 | v7 | 10 | V7 Policy Acceptance Implementation (GATED) |
| 08 | audit | 10 | Final Training Readiness Audit |

## Dependency Order

```
00_baseline
    │
01_backfill ────── 03_cli_ops  (disjoint files — safe to parallelize)
    │              
02_sim_adapter    (depends on 01 data contract)
    │              
04_funding_rate   (depends on 02)
    │              
05_training (GATED: 01-04 must PASS)
    │
06_wfv      (GATED: 05 must PASS_TRAINING_EXECUTED)
    │
07_v7       (GATED: 05+06 must PASS)
    │
08_final_audit
```

**Parallelization note:** Plans 01 and 03 touch disjoint file sets.
Plan 01 owns lib/market_data/ — does NOT touch Makefile.
Plan 03 owns Makefile, CLI, .env.example, configs/, docs/.

## Canonical Data Paths

| Directory | Purpose |
|-----------|---------|
| `data/raw/` | Raw market data (unprocessed klines, funding) |
| `data/normalized/` | Normalized market data (KlineRecord, FundingRecord) |
| `data/processed/` | Legacy/compatibility only — not used for market data |
| `data/models/` | Trained model artifacts |
| `data/results/` | Evaluation results, reports data |

## Key Repairs (v1)

1. **R01**: Master hardDeny now scoped — uncontrolled training denied, Plan 05 controlled training allowed
2. **R02**: Plan files treated as read-only inputs in implementation tasks
3. **R03**: Makefile owned solely by Plan 03 — Plan 01 exposes Python module contract only
4. **R04**: Backfill plan has 11 ACs with mock/dry-run command proof
5. **R05**: Canonical data/raw/ + data/normalized/ paths throughout
6. **R06**: Training status: PASS_TRAINING_EXECUTED vs HOLD_NO_XGBOOST — skip never full PASS
7. **R07**: V7 plan expanded to 10 ACs with canonical G0-G10 gates
8. **R08**: Funding plan expanded to 8 ACs with 429/retry/backoff
9. **R09**: Final audit enforces 7 strict truth rules — skip != ready
10. **R10**: All critical plans have >= 8 ACs each

## Training Verdict Policy

Plan 05 uses controlled verdicts:
- `PASS_TRAINING_EXECUTED` — model trained on real data with XGBoost
- `PASS_RUNNER_IMPLEMENTED_BUT_TRAINING_GATED` — runner code exists, training gated
- `HOLD_NO_XGBOOST` — XGBoost not installed, cannot train
- `HOLD_MISSING_REAL_DATASET` — no real dataset available
- `FAIL` — prerequisites not met

Final audit rule: `skip != training-ready`. If no model artifact from real gated training,
training_readiness_percent must not exceed 30.

## Current Baseline

- Scaffold completion: **92%**
- Training readiness: **0%**
- Overall pipeline readiness: **24.5%**
- Source: `reports/accp/v7_engine_reality_gap_audit.accp.yaml`

## Safety

- No live trading authorized
- No profitability claims authorized
- Training gated behind real data + simulation prerequisites
- XGBoost absence = HOLD (never false PASS)
- Funding model may remain HOLD
- SCALP/AGGRESSIVE_SCALP remain HOLD until empirical evidence
- All plans use template.yaml PlanSpec v0.1.0 schema

## Files

- `master.plan.yaml` — Orchestration plan (no plan file modifications)
- `00–08_*.plan.yaml` — Domain-specific implementation plans
- `README.md` — This file
- `manifest.json` — Machine-readable bundle manifest
