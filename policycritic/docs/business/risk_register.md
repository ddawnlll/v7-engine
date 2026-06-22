# Risk Register — V7 Policy Critic

## Risk Ranking

| ID | Risk | Probability | Impact | Severity | Phase | Mitigation |
|----|------|-----------|--------|----------|-------|-----------|
| R1 | **OOD overestimation** — IQL's in-sample guarantee fails on financial data | Low | Critical | High | 3-5 | CQL cross-check; OOD distance monitoring; auto-degrade |
| R2 | **Conservative collapse** — τ too high → critic recommends NO_TRADE on everything | Medium | High | High | 3-5 | τ sensitivity analysis; veto rate bounded away from 1 |
| R3 | **Backtest overfitting** — Critic improvement is noise, not signal | Medium | Critical | Critical | 3-6 | DSR p<0.05 + PBO<0.10; walk-forward ≥4/5; shadow burn-in |
| R4 | **Regime shift invalidates training** — Market changes, critic degrades | High | High | Critical | 4-6 | Multi-regime training; per-regime monitoring; auto-degrade |
| R5 | **Replay buffer data quality** — Temporal leakage, look-ahead, survivorship bias | Medium | Critical | Critical | 2-3 | Purge+embargo; leakage detection tests; delisted asset inclusion |
| R6 | **Reward hacking** — Critic maximizes reward in unintended way | Medium | High | High | 3-5 | Decomposable reward; hard shields outside RL; multi-regime eval |
| R7 | **Conformal coverage failure** — Exchangeability violated, coverage << nominal | High | Medium | Medium | 3-5 | Time-aware CP variant; accept approximate coverage; monitor drift |
| R8 | **Human over-trust** — Operators trust critic blindly, disable gates | Medium | Critical | Critical | 5-6 | Gates are non-bypassable; human approval required; audit trail |
| R9 | **Live authority creep** — Critic gains de facto veto without formal approval | Low | Critical | Critical | 5-6 | Config-gated; code review; runtime_interpretation visibility |
| R10 | **Simulation-reality gap** — /simulation costs ≠ live costs | Medium | High | High | 4-6 | Live shadow OPE vs realized comparison; recalibrate if diverging |
| R11 | **Funding cost implementation** — When funding lands, spot-trained critic invalid for perps | Medium | Medium | Medium | Future | Retrain with funding-inclusive reward; perp blocked at G3 |
| R12 | **Two simulation path divergence** — Runtime historical engine ≠ /simulation engine | High | Medium | Medium | 2-3 | Route replay buffer through /simulation engine only |
| R13 | **Critic inference latency** — Slows scan loop beyond acceptable threshold | Low | Medium | Low | 4-5 | XGBoost CPU inference <10ms; timeout with safe degrade |
| R14 | **Model staleness** — Critic not retrained, becomes stale as market evolves | Medium | Medium | Medium | 4-6 | Periodic retraining schedule; staleness monitoring |
| R15 | **SCALP/AGGRESSIVE pressure** — Business pressure to enable critic on fast modes prematurely | Medium | High | High | 5-6 | Permanent HOLD without independent evidence; governance firewall |

## Severity Matrix

| | Critical Impact | High Impact | Medium Impact | Low Impact |
|---|---|---|---|---|
| **High Prob** | R4 (regime shift) | R12 (sim path divergence), R7 (conformal failure) | | |
| **Medium Prob** | R3 (overfitting), R5 (data quality), R8 (over-trust) | R2 (conservative collapse), R6 (reward hacking), R10 (sim-reality gap) | R11 (funding), R14 (staleness), R15 (SCALP pressure) | |
| **Low Prob** | R9 (authority creep) | R1 (OOD overestimation) | | R13 (latency) |

## Mitigation Effectiveness

| Risk | Primary Mitigation | Residual Risk | Acceptable? |
|------|-------------------|---------------|-------------|
| R1 | IQL + CQL | Low | Yes |
| R2 | τ tuning + bounded veto rate | Low-Medium | Yes (with monitoring) |
| R3 | DSR + PBO + WF | Low-Medium | Yes (with evidence) |
| R4 | Multi-regime + monitoring | Medium | Accept only with auto-degrade |
| R5 | Purge + embargo + tests | Low | Must be zero |
| R6 | Decomposable reward + shields | Low | Yes |
| R7 | Time-aware CP | Medium | Accept approximate coverage |
| R8 | Non-bypassable gates + audit | Low | Yes |
| R9 | Config gate + code review | Low | Yes |
| R10 | Live shadow comparison | Medium | Monitor continuously |
| R12 | Route through /simulation | Low | Must be enforced |

## Review Cadence

| Phase | Review Frequency | Reviewer |
|-------|-----------------|----------|
| 0-1 (docs/schema) | Once | Partner |
| 2-3 (buffer/training) | Per milestone | ML Engineer + Quant |
| 4 (shadow runtime) | Weekly | Engineering Lead |
| 5 (guarded influence) | Daily (first 2 weeks), then weekly | Engineering Lead + Risk Manager |
| 6 (business validation) | Weekly | All stakeholders |
