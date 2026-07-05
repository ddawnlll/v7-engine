# Training-Ready Quant Pipeline PlanSpec Bundle

Generated from the V7 Engine Reality Gap Audit (24.5% readiness).
This bundle contains all implementation plans needed to move from
deterministic scaffold to training-ready quant research pipeline.

## Bundle Overview

| Plan | Domain | Title |
|------|--------|-------|
| 00 | audit | Reality Gap Baseline Verification |
| 01 | lib | Market Data Backfill + Storage |
| 02 | simulation | Market Data Adapter + Batch + Persistence |
| 03 | ops | Pipeline CLI + Makefile + Runbook |
| 04 | lib+sim | Funding Pagination + Rate Limit |
| 05 | alphaforge | XGBoost Training Runner (GATED) |
| 06 | alphaforge | Empirical WFV with Real Metrics (GATED) |
| 07 | v7 | Policy Acceptance Implementation (GATED) |
| 08 | audit | Final Training Readiness Audit |

## Dependency Order

```
00_baseline
    │
01_backfill ──────┬──── 03_cli_ops
    │             │
02_sim_adapter    │
    │             │
04_funding_rate   │
    │             │
    └─────┬───────┘
          │
    05_training (GATED: 01-04 must PASS)
          │
    06_wfv      (GATED: 05 must PASS)
          │
    07_v7       (GATED: 05+06 must PASS)
          │
    08_final_audit
```

Plans 01 and 03 may execute in parallel (disjoint file sets).
Plan 02 depends on data contract from 01.
Plans 05-07 are HARD-GATED behind prerequisite plans.

## Current Baseline

- Scaffold completion: **92%**
- Training readiness: **0%**
- Overall pipeline readiness: **24.5%**
- Source: `reports/accp/v7_engine_reality_gap_audit.accp.yaml`

## Expected After Execution

- After 01-04: **45–55%** readiness (data + simulation + ops)
- After 05-08: Training-ready only if empirical evidence passes

## Safety

- No live trading authorized
- No profitability claims authorized
- Training gated behind real data + simulation prerequisites
- Funding model may remain HOLD
- SCALP/AGGRESSIVE_SCALP remain HOLD until empirical evidence
- All plans use template.yaml PlanSpec v0.1.0 schema

## Schema

All `.plan.yaml` files validate against `template.yaml` at repo root.
Schema version: `planSpecVersion: "0.1.0"`, `kind: ImplementationPlan`, `profile: praxis-v0.1`.

## Execution

```bash
# Review all plans before execution
cat plans/training_ready/README.md

# Validate schema
python3 -c "
import yaml, pathlib
from jsonschema import Draft202012Validator
schema = yaml.safe_load(pathlib.Path('template.yaml').read_text())
v = Draft202012Validator(schema)
for p in sorted(pathlib.Path('plans/training_ready').glob('*.plan.yaml')):
    errors = list(v.iter_errors(yaml.safe_load(p.read_text())))
    print(f'{'PASS' if not errors else 'FAIL'} {p.name}')
"

# Execute (only after review)
# Plans must be run in dependency order.
# Master plan orchestrates execution: plans/training_ready/master.plan.yaml
```

## Files

- `master.plan.yaml` — Orchestration plan
- `00_reality_gap_baseline.plan.yaml` — Baseline verification
- `01_market_data_backfill_storage.plan.yaml` — Backfill + storage
- `02_simulation_market_data_adapter.plan.yaml` — Simulation adapter
- `03_pipeline_cli_makefile_runbook.plan.yaml` — CLI + ops
- `04_funding_pagination_rate_limit.plan.yaml` — Funding + rate limit
- `05_training_runner_xgboost_gate.plan.yaml` — Training (gated)
- `06_empirical_wfv_metrics.plan.yaml` — Empirical WFV (gated)
- `07_v7_policy_acceptance_impl.plan.yaml` — V7 policy (gated)
- `08_final_training_readiness_audit.plan.yaml` — Final audit
- `README.md` — This file
- `manifest.json` — Machine-readable bundle manifest
