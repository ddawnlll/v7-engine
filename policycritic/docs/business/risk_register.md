# Risk Register — V7 Policy Critic

## Risk Ranking (25 Risks)

| ID | Risk | Category | Probability | Impact | Severity | Phase | Detection | Mitigation | Owner | Kill Condition |
|----|------|---------|-----------|--------|----------|-------|----------|-----------|-------|---------------|
| R1 | **OOD overestimation** — IQL in-sample guarantee fails on financial data | Technical | Low | Critical | High | 3-5 | OOD distance metric per-inference | CQL cross-check; OOD distance monitoring; auto-degrade | ML Engineer | OOD rate > 20% of inferences |
| R2 | **Conservative collapse** — τ too high, critic always NO_TRADE | Technical | Medium | High | High | 3-5 | Veto rate dashboard daily | τ sensitivity analysis; veto rate bounded away from 1 | ML Engineer | Veto rate > 90% for 7 consecutive days |
| R3 | **Backtest overfitting** — Critic improvement is noise not signal | Technical | Medium | Critical | Critical | 3-6 | DSR/PBO per-evaluation monthly | DSR p<0.05 + PBO<0.10; walk-forward ≥4/5; shadow burn-in | ML Engineer | PBO > 0.20 |
| R4 | **Regime shift** — Market changes, critic degrades | Market | High | High | Critical | 4-6 | Per-regime dashboard weekly | Multi-regime training; per-regime monitoring; auto-degrade | Quant | Any single-regime degradation > 20% |
| R5 | **Replay buffer data quality** — Temporal leakage, look-ahead, survivorship | Data | Medium | Critical | Critical | 2-3 | Leakage tests per-PR (CI) | Purge+embargo; leakage detection tests; delisted asset inclusion | ML Engineer | Any leakage test failure |
| R6 | **Reward hacking** — Critic maximizes reward in unintended way | Technical | Medium | High | High | 3-5 | Reward component decomposition per-training | Decomposable reward; hard shields outside RL; multi-regime eval | ML Engineer | Any reward component > 3σ from baseline |
| R7 | **Conformal coverage failure** — Exchangeability violated | Technical | High | Medium | Medium | 3-5 | Coverage vs nominal per-calibration | Time-aware CP variant; accept approximate coverage; monitor drift | ML Engineer | Coverage < 60% of nominal |
| R8 | **Human over-trust** — Operators trust critic blindly | Operational | Medium | Critical | Critical | 5-6 | Gate bypass attempt audit log real-time | Gates non-bypassable; human approval required; audit trail | Risk Manager | Any gate disabled without approval |
| R9 | **Live authority creep** — Critic gains de facto veto | Governance | Low | Critical | Critical | 5-6 | Config change audit log real-time | Config-gated; code review; runtime_interpretation visibility | Risk Manager | Any unapproved config change enabling live veto |
| R10 | **Simulation-reality gap** — /simulation costs ≠ live costs | Technical | Medium | High | High | 4-6 | Live OPE vs offline monthly | Live shadow OPE vs realized comparison; recalibrate | ML Engineer | Gap > 0.1R sustained |
| R11 | **Funding cost implementation** — Spot-trained critic invalid for perps | Technical | Medium | Medium | Medium | Future | Perp trading metrics | Retrain with funding-inclusive reward; perp blocked at G3 | Quant | Perp enabled before funding implemented |
| R12 | **Two simulation path divergence** — Runtime engine ≠ /simulation | Technical | High | Medium | Medium | 2-3 | Cost comparison tests CI | Route replay buffer through /simulation engine only | ML Engineer | Runtime engine used for training data |
| R13 | **Critic inference latency** — Slows scan loop | Technical | Low | Medium | Low | 4-5 | Latency monitoring per-inference | XGBoost CPU <10ms; timeout with safe degrade | Backend Engineer | p99 latency > 50ms |
| R14 | **Model staleness** — Critic not retrained | Technical | Medium | Medium | Medium | 4-6 | Staleness monitoring | Periodic retraining schedule | ML Engineer | > 90 days since last retrain |
| R15 | **SCALP/AGGRESSIVE pressure** — Business pressure for premature fast-mode enablement | Governance | Medium | High | High | 5-6 | Policy enforcement | Permanent HOLD without independent evidence; governance firewall | Risk Manager | SCALP/AGGRESSIVE enabled without independent evidence |
| R16 | **Data sparsity** — Insufficient samples for rare regime/action | Data | Medium | High | High | 3-5 | Per-regime-action sample count per-training | Minimum samples per regime-action; fall back to global model | ML Engineer | Any regime-action < 50 samples |
| R17 | **Insufficient losing trade samples** — Too few bad outcomes | Data | Medium | Medium | Medium | 2-3 | Class balance monitoring per-training | Synthetic augmentation; oversample minority outcomes | ML Engineer | Losing trades < 20% of buffer |
| R18 | **Paper/live mismatch** — Paper costs ≠ live costs | Operational | Medium | High | High | 5-6 | Live vs paper cost comparison | Live shadow comparison; cost model recalibration | Backend Engineer | Sustained gap > 20% |
| R19 | **Overfitting to shadow data** — Tuned against shadow period | Technical | Medium | High | High | 5-6 | Walk-forward re-validation quarterly | Hold-out final test period; re-validation | ML Engineer | WF consistency drops below 3/5 |
| R20 | **Engineering cost overrun** — Development longer/costlier than planned | Business | Medium | Medium | Medium | 2-6 | Budget vs actual tracking monthly | Phased funding; go/no-go at each phase gate | Partner | > 50% over budget with no DSR evidence |
| R21 | **Stakeholder misuse** — Non-technical stakeholders treat verdicts as signals | Operational | Low | High | High | 4-6 | User behavior analytics | Dashboard labels; documentation; training | Risk Manager | Verdicts used as primary trading signal |
| R22 | **Compliance/regulatory uncertainty** — Future ML trading advisor regulations | External | Low | High | Medium | 5-6 | Regulatory monitoring | Legal review before live influence; audit trail | Risk Manager | Adverse regulatory guidance received |
| R23 | **Feature/schema drift** — AlphaForge features change | Technical | Medium | Medium | Medium | 4-6 | Schema validation CI | Schema versioning; input validation; staleness detection | ML Engineer | Schema mismatch undetected > 24h |
| R24 | **Adversarial exploitation** — External actors trigger critic behavior | Security | Low | Critical | Medium | 5-6 | Input anomaly detection per-inference | Rate limiting; input monitoring; anomaly detection | Security | Any detected adversarial pattern |
| R25 | **Dependency on V6 sibling repo** — V6 changes break critic | Integration | Medium | Medium | Medium | 4-5 | Integration tests CI | Contract-based adapter; integration tests | Backend Engineer | Integration test failure |

## Severity Matrix

| | Critical Impact | High Impact | Medium Impact | Low Impact |
|---|---|---|---|---|
| **High Prob** | R4 (regime shift) | R12 (sim path), R7 (conformal failure) | | |
| **Medium Prob** | R3 (overfitting), R5 (data quality), R8 (over-trust) | R2 (collapse), R6 (hacking), R10 (sim-reality), R16 (sparsity), R18 (paper/live), R19 (shadow overfit) | R11 (funding), R14 (staleness), R15 (SCALP pressure), R17 (bad samples), R20 (cost), R23 (drift), R25 (V6 dep) | |
| **Low Prob** | R9 (authority creep), R24 (adversarial) | R1 (OOD), R21 (misuse), R22 (compliance) | | R13 (latency) |

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
| R11 | Retrain with funding; perp blocked | Medium | G3 gate until implemented |
| R12 | Route through /simulation | Low | Must be enforced |
| R13 | Timeout + safe degrade | Low | Yes |
| R14 | Periodic retraining schedule | Medium | Monitor staleness |
| R15 | Governance firewall; HOLD | Medium | Accept HOLD as permanent |
| R16 | Minimum sample gate; fallback | Medium | Accept fallback |
| R17 | Oversample; synthetic augment | Medium | Monitor class balance |
| R18 | Live shadow comparison | Medium | Monitor continuously |
| R19 | Hold-out period; re-validation | Medium | Accept as evidence requirement |
| R20 | Phased funding; kill conditions | Low | Accept with go/no-go gates |
| R21 | Documentation; dashboard labels | Low | Training + labeling |
| R22 | Legal review; audit trail | Medium | Accept as compliance cost |
| R23 | Schema versioning; validation | Low | Standard ML ops |
| R24 | Rate limiting; input monitoring | Low | Accept as monitoring cost |
| R25 | Contract-based adapter; tests | Low | Standard integration |

## Review Cadence

| Phase | Review Frequency | Reviewer |
|-------|-----------------|----------|
| 0-1 (docs/schema) | Once | Partner |
| 2-3 (buffer/training) | Per milestone | ML Engineer + Quant |
| 4 (shadow runtime) | Weekly | Engineering Lead |
| 5 (guarded influence) | Daily (first 2 weeks), then weekly | Engineering Lead + Risk Manager |
| 6 (business validation) | Weekly | All stakeholders |
