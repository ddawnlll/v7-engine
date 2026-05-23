# V7 AlphaForge Phase Index
Generated: 2026-05-23
Model name: V7 AlphaForge XGB
Package version: v1.2_shared_lib_authority

## Phases
- [P0 — Repo Alignment & Alpha Foundations](phase_plans/P0__repo_alignment_and_alpha_foundations.md)
- [P0.5 — Shared Lib Foundation](phase_plans/P0_5__shared_lib_foundation.md)
- [P1 — Contracts & Alpha Data Contract](phase_plans/P1__contracts_and_alpha_data_contract.md)
- [P2 — Runtime Simulation Adapter & R-Label Engine](phase_plans/P2__runtime_simulation_adapter_and_r-label_engine.md)
- [P3 — Multi-Timeframe Feature Engine & Unsupervised Context](phase_plans/P3__multi-timeframe_feature_engine_and_unsupervised_context.md)
- [P4 — Dataset Assembly, Walk-Forward Splits & Label QA](phase_plans/P4__dataset_assembly,_walk-forward_splits_and_label_qa.md)
- [P5 — XGBoost Hybrid Model Training](phase_plans/P5__xgboost_hybrid_model_training.md)
- [P6 — Calibration, Reliability & Alpha Score Builder](phase_plans/P6__calibration,_reliability_and_alpha_score_builder.md)
- [P7 — V7 Policy, Portfolio & Risk Integration](phase_plans/P7__v7_policy,_portfolio_and_risk_integration.md)
- [P8 — Evaluation, Backtest, Paper & Shadow Validation](phase_plans/P8__evaluation,_backtest,_paper_and_shadow_validation.md)
- [P9 — Deployment, Monitoring, Drift, Promotion & Rollback](phase_plans/P9__deployment,_monitoring,_drift,_promotion_and_rollback.md)


## Phase Dependencies

```
P0 ──► P0.5 ──► P1 ──► P2 ───┐
                   │           ├──► P4 ──► P5 ──► P6 ──► P7 ──► P8 ──► P9
                   └──► P3 ────┘
```

| Phase | Depends On | Required By |
|---|---|---|
| P0 | — | P0.5 |
| P0.5 | P0 | P1, P2, P3, P4, P7 |
| P1 | P0.5 | P2, P3 |
| P2 | P1, P0.5 | P4 |
| P3 | P1, P0.5 | P4 |
| P4 | P2, P3, P0.5 | P5 |
| P5 | P4 | P6, P8 |
| P6 | P5 | P7, P8 |
| P7 | P6, P0.5 | P8 |
| P8 | P5, P6, P7 | P9 |
| P9 | P8 | NONE |

## Lib Dependency Map

| Phase | lib Dependency | Reason |
|---|---|---|
| P0.5 | Creates lib/ | Foundation phase |
| P1 | lib.market_data | Data contracts reference market data schema |
| P2 | lib.indicators.atr, lib.costs | ATR for stop/target, costs for labels |
| P3 | lib.indicators.* | Feature generation uses indicators |
| P4 | lib.time.folds | Fold generation |
| P5 | (none directly) | XGBoost training uses alphaforge dataset |
| P6 | (none directly) | Calibration uses alphaforge outputs |
| P7 | (none directly) | V7 regime is own authority, not shared |
| P8 | (none directly) | Evaluation uses alphaforge metrics |
| P9 | (none directly) | Monitoring uses alphaforge outputs |

## Hardening mapping

| Hardening item | Primary phase | Secondary phases |
|---|---|---|
| Shared lib authority | P0.5 | All subsequent |
| Fold-scoped anomaly fitting | P3 | P4, P8, P9 |
| Anomaly lineage compatibility checks | P4 | P3, P8 |
| Regime/deterministic override visibility | P7 | P1, P8, P9 |
| Symbol encoding future-proofing | P3/P5 | P0, P4 |
| SCALP interval authority | P0/P0.5/P2 | P3, P4, P5, P8 |
| Import boundary enforcement | P0.5 | All subsequent |
| Market data service commonization | P0.5 | P1, P2, P3 |
