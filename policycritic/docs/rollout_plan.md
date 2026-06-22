# Rollout Plan

> Status: Docs/Design Only — No implementation exists
> Created: 2026-06-23 (adapted from old repo source material)

## 1. Current Position

**Today (2026-06-23):** Docs/Design only. The Policy Critic exists only as:

- Design documentation in `v7/docs/policy_critic/` and `policycritic/docs/`
- Shadow persistence infrastructure (`runtime/db/repos/shadow_policy_repo.py`)
- Policy dataset persistence (`runtime/db/repos/policy_dataset_repo.py`)
- Simulation engine (`simulation/engine/engine.py`) producing the authoritative reward surface
- AlphaForge contract schemas defining the alpha evidence flow (spec only)

**The live decision path** runs through the V6 inference engine (sibling repo), imported via `runtime/services/analyzer_engine_adapter.py`.

**v7/src/** is greenfield (only `.gitkeep`). AlphaForge P5/P6/P9 phases are planned but not started.

---

## 2. Staged Rollout

### Stage 0: Docs & Design ← WE ARE HERE

| Aspect | Detail |
|---|---|
| **Status** | IN PROGRESS |
| **Deliverables** | `policycritic/docs/*` (9 files), ACCP completion report |
| **Duration** | This ACCP task |
| **Exit criteria** | Docs reviewed, ACCP completion report generated |
| **Risk** | None — no code written |

### Stage 1: PolicyCriticReview Contract

| Aspect | Detail |
|---|---|
| **Status** | NOT STARTED |
| **Prerequisite** | Stage 0 complete |
| **Deliverable** | `contracts/schemas/policy_critic_review.schema.json` + registry entry + compatibility entry + fixture |
| **Duration** | 2–3 days |
| **Exit criteria** | Contract registered per `contracts/README.md` 6-step procedure; schema parity test passes |
| **Risk** | Low — follows existing contract patterns |
| **Live authority** | None |

### Stage 2: Replay Buffer Emitter

| Aspect | Detail |
|---|---|
| **Status** | NOT STARTED |
| **Prerequisite** | Stage 1 complete (PolicyCriticReview contract) |
| **Deliverable** | Tuple assembler pairing canonical state + SimulationOutput; storage schema |
| **Duration** | 3–4 weeks |
| **Exit criteria** | ≥ 1000 resolved tuples stored; data split validated; NO_TRADE records included; reward normalization tested |
| **Risk** | Medium — next_state definition must be validated; temporal leakage must be prevented; two-simulation-path divergence must be addressed |
| **Live authority** | **None** — data recording only |

### Stage 3: V1 Shadow Rule-Based Critic

| Aspect | Detail |
|---|---|
| **Status** | NOT STARTED |
| **Prerequisite** | Stage 1 complete (PolicyCriticReview contract) |
| **Deliverable** | Heuristic risk scorer using ShadowPolicyRepository (~200 LoC) |
| **Duration** | 1–2 weeks |
| **Exit criteria** | Shadow critic records PolicyCriticReview for every scan decision; zero live influence; 7 days stable operation |
| **Risk** | Low — heuristic rules only; pass-through design |
| **Live authority** | **None** — shadow mode only |

### Stage 4: V2 Supervised Critic

| Aspect | Detail |
|---|---|
| **Status** | NOT STARTED |
| **Prerequisite** | Stage 2 complete (≥ 1000 tuples), DSR/PBO validation infrastructure |
| **Deliverable** | XGBoost expected-value estimator predicting realized_r from state features |
| **Duration** | 4–6 weeks |
| **Exit criteria** | DSR p < 0.05; PBO < 0.10; walk-forward ≥ 4/5 folds; champion anti-regression pass; 30-day shadow burn-in |
| **Risk** | Medium — supervised model may overfit; requires calibration |
| **Live authority** | **None** — shadow mode only |

### Stage 5: Off-Policy Evaluation Infrastructure

| Aspect | Detail |
|---|---|
| **Status** | NOT STARTED |
| **Prerequisite** | Stage 4 complete (V2 critic producing predictions) |
| **Deliverable** | FQE implementation; DSR/PBO integration |
| **Duration** | 3–4 weeks |
| **Exit criteria** | FQE 95% CI computed; CI overlaps observed performance; OPE protocol documented |
| **Risk** | Medium — FQE implementation must match literature; importance sampling variance may be high |
| **Live authority** | **None** — evaluation only |

### Stage 6: V3 Offline IQL Critic

| Aspect | Detail |
|---|---|
| **Status** | NOT STARTED |
| **Prerequisite** | Stage 5 complete (FQE validated), ≥ 10,000 replay buffer tuples |
| **Deliverable** | IQL-trained distributional Q-function with conformal calibration; CQL cross-check ensemble |
| **Duration** | 8–12 weeks |
| **Exit criteria** | FQE 95% CI overlaps observed performance; PBO < 0.10; DSR p < 0.05; walk-forward ≥ 4/5 folds; champion anti-regression; IQL/CQL disagreement bounded; 30-day shadow burn-in; human approval |
| **Risk** | High — IQL untested on financial data; expectile τ requires tuning; Q-function stability unknown |
| **Live authority** | **None** — shadow mode only until all gates pass + human approval |

### Stage 7: V4 Constrained Policy Optimizer

| Aspect | Detail |
|---|---|
| **Status** | NOT STARTED |
| **Prerequisite** | Stage 6 complete (V3 stable ≥ 60 days), formal shield verification |
| **Deliverable** | Sizing/exit proposals within shield limits |
| **Duration** | 12–16 weeks |
| **Exit criteria** | Formal shield compliance verified; multi-regime validation; adversarial simulation; stress testing; human approval |
| **Risk** | Critical — sizing proposals even within shield limits carry real financial risk |
| **Live authority** | **Proposals only** within shield bounds; gates retain hard veto |

---

## 3. PR Sequencing

### 3.1 Recommended PR Order

```
PR-1:  policycritic/docs/* + ACCP completion report          ← THIS TASK
PR-2:  PolicyCriticReview contract (schema + registry + fixture)
PR-3:  Replay buffer emitter + storage schema
PR-4:  V1 shadow rule-based critic (~200 LoC, shadow-only)
PR-5:  V2 supervised critic (XGBoost expected-value predictor)
PR-6:  OPE infrastructure (FQE, DSR, PBO integration)
PR-7:  V3 IQL critic (distributional offline RL Q-function + CQL cross-check)
PR-8:  V4 constrained optimizer (sizing/exit proposals)
```

### 3.2 Branching Strategy

Each PR from a feature branch off `main`:
```
main
  ├── pr/v7-policycritic-docs          (PR-1: this task)
  ├── feature/v7-policy-critic-contract  (PR-2: contract)
  ├── feature/v7-policy-critic-replay    (PR-3: replay buffer)
  └── ...
```

### 3.3 Review Requirements Per PR

| PR | Reviewers | Tests Required |
|---|---|---|
| PR-1 (docs) | 1 reviewer | No code tests (docs only) |
| PR-2 (contract) | 1 reviewer | Schema parity test, fixture roundtrip |
| PR-3 (replay buffer) | 2 reviewers | Unit tests, data integrity tests, leakage tests |
| PR-4 (V1 critic) | 2 reviewers | Unit tests, shadow mode integration test |
| PR-5 (V2 critic) | 2 reviewers + architecture | Training tests, calibration tests, DSR/PBO |
| PR-6 (OPE) | 2 reviewers + architecture | FQE validation tests, CI computation tests |
| PR-7 (V3 critic) | 2 reviewers + architecture + security | Full evaluation suite, adversarial tests |
| PR-8 (V4 optimizer) | 3 reviewers + architecture + security | Full evaluation + shield compliance + stress tests |

---

## 4. Live Authority Restrictions

### 4.1 When Live Authority Could Be Considered

| Condition | Required Before |
|---|---|
| Replay buffer ≥ 10,000 tuples | Any live influence |
| PBO < 0.10 | Any live influence |
| DSR p < 0.05 | Any live influence |
| FQE 95% CI overlaps observed performance | Any live influence |
| ≥ 90 days stable shadow operation | Any live influence |
| Multi-regime validation pass | Any live influence |
| Walk-forward ≥ 4/5 folds maintained across 3+ retrains | Any live influence |
| Human approval | Any live influence |

### 4.2 What Live Authority Would Look Like (Hypothetical)

Even if all conditions are met, live authority would remain constrained:
- **V1-V3 critics**: Advisory only — NO live veto, ever
- **V4 critic**: Advisory sizing proposals within shield limits — gates retain hard veto
- **Any version**: Confidence downweight can influence position sizing through existing gate mechanisms
- **Never**: Direct trade execution, gate bypass, or autonomous decision-making

### 4.3 SWING Mode First Candidate

SWING is `LOCKED_INITIAL_BASELINE` as the first live veto candidate per the canonical design. SCALP and AGGRESSIVE_SCALP thresholds are HOLD.

---

## 5. Success Metrics Per Stage

| Stage | Primary Metric | Secondary Metric |
|---|---|---|
| Replay Buffer | Data integrity (no temporal leakage) | Tuple completion rate (> 95%) |
| V1 Critic | Zero false-positive rate (no incorrect NO_TRADE recs) | Signal-to-noise ratio of risk scores |
| V2 Critic | Expected value calibration (realized vs predicted r² > 0.1) | PBO < 0.10, DSR p < 0.05 |
| OPE | FQE 95% CI width < 1.0R | Importance sampling effective sample size |
| V3 Critic | Q-function stability (Bellman error not diverging) | FQE CI overlap maintained |
| V4 Optimizer | Shield compliance 100% (zero violations) | Size proposal acceptance rate by gates |

---

## 6. Rollback Conditions

| Trigger | Action |
|---|---|
| Any safety metric degradation | Rollback critic to previous version |
| PBO exceeds 0.20 | Rollback + investigate root cause |
| Q-function divergence (V3+) | Immediate rollback + architecture review |
| Shield compliance violation (V4) | Immediate rollback + safety incident review |
| Data integrity failure in replay buffer | Pause all critic versions + data audit |
| FQE CI no longer overlaps | Suspend live influence consideration + recalibrate |

---

## 7. Timeline (Not Committed)

This is a **design estimate only**, not a committed timeline:

| Milestone | Earliest Possible | Dependencies |
|---|---|---|
| Docs complete | 2026-06-23 | None (this task) |
| PolicyCriticReview contract | 2026-07 | Docs approved |
| Replay buffer emitter | 2026-08 | Contract defined |
| V1 shadow critic | 2026-08 | Contract defined |
| V2 supervised critic | 2026-10 | Replay buffer ≥ 1000 tuples |
| OPE infrastructure | 2026-11 | V2 critic predictions |
| V3 IQL critic | 2027-Q1 | Replay buffer ≥ 10000 tuples, FQE validated |
| V4 optimizer | 2027-Q2–Q3 | V3 stable ≥ 60 days, formal verification |

**All timelines are conditional on prerequisite gates passing. No dates are committed.**

---

## 8. Related Documents

- [[pipeline.md]] — Detailed pipeline with release gates and HOLD conditions
- [[authority_and_boundaries.md]] — Complete authority hierarchy
- [[replay_buffer_design.md]] — Replay buffer technical specification
- [[policy_critic_design.md]] — Architecture and data flow
- [[ai_summary.md]] — Current repo state and blockers
- `v7/docs/policy_critic/design.md` — Canonical design with staged rollout table
