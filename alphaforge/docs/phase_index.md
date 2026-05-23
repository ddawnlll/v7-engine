# V7 AlphaForge Phase Index
Generated: 2026-05-23
Model name: V7 AlphaForge XGB

## Phases
- [P0 — Repo Alignment & Alpha Foundations](phase_plans/P0__repo_alignment_and_alpha_foundations.md)
- [P1 — Contracts & Alpha Data Contract](phase_plans/P1__contracts_and_alpha_data_contract.md)
- [P2 — Runtime Simulation Adapter & R-Label Engine](phase_plans/P2__runtime_simulation_adapter_and_r-label_engine.md)
- [P3 — Multi-Timeframe Feature Engine & Unsupervised Context](phase_plans/P3__multi-timeframe_feature_engine_and_unsupervised_context.md)
- [P4 — Dataset Assembly, Walk-Forward Splits & Label QA](phase_plans/P4__dataset_assembly,_walk-forward_splits_and_label_qa.md)
- [P5 — XGBoost Hybrid Model Training](phase_plans/P5__xgboost_hybrid_model_training.md)
- [P6 — Calibration, Reliability & Alpha Score Builder](phase_plans/P6__calibration,_reliability_and_alpha_score_builder.md)
- [P7 — V7 Policy, Portfolio & Risk Integration](phase_plans/P7__v7_policy,_portfolio_and_risk_integration.md)
- [P8 — Evaluation, Backtest, Paper & Shadow Validation](phase_plans/P8__evaluation,_backtest,_paper_and_shadow_validation.md)
- [P9 — Deployment, Monitoring, Drift, Promotion & Rollback](phase_plans/P9__deployment,_monitoring,_drift,_promotion_and_rollback.md)


## Hardening mapping

| Hardening item | Primary phase | Secondary phases |
|---|---|---|
| Fold-scoped anomaly fitting | P3 | P4, P8, P9 |
| Anomaly lineage compatibility checks | P4 | P3, P8 |
| Regime/deterministic override visibility | P7 | P1, P8, P9 |
| Symbol encoding future-proofing | P3/P5 | P0, P4 |
| SCALP interval authority | P0/P2 | P3, P4, P5, P8 |
