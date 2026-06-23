# Acceptance Rubric — V7 Policy Critic Docs

## Partner Acceptance Checklist (18 items)

| # | Criterion | Threshold | Status |
|---|----------|-----------|--------|
| P1 | Docs linked from main entry points | `README.md`, `ai_summary.md`, `v7/docs/policy_critic/ai_summary.md` | ✅ |
| P2 | Folder tree present | `folder_tree.md` with current + future layout | ✅ |
| P3 | Implementation file map present | `implementation_file_map.md` with 15 sections | ✅ |
| P4 | Problem statement present | `problem_statement.md` answering all required questions | ✅ |
| P5 | Phase plans complete (7 files) | Each with goal, non-goals, entry/exit criteria, files, risks, rollback, checkpoints | ✅ |
| P6 | Research docs complete (15 files) | Each ≥ 100 lines with abstract, application, failure modes, citations, decision | ✅ |
| P7 | Business plan present | `business_plan.md` with strategic thesis, milestones, kill conditions | ✅ |
| P8 | Profitability calculation present | `profitability_calculation.md` with 15 sections, formulas, scenarios, sensitivity | ✅ |
| P9 | Unit economics present | Per-signal, per-trade, per-verdict, per-model-run economics | ✅ |
| P10 | Risk register present | ≥ 25 risks ranked by probability × impact with detection, owner, kill condition | ✅ |
| P11 | Go-to-market strategy present | Internal rollout, stakeholder map, operational readiness | ✅ |
| P12 | Self-scorecard present | Tables A-C, red-team critique, score before/after | ✅ |
| P13 | Independent review packet present | Written for external AI, with rubric, output format, pass threshold | ✅ |
| P14 | Partner feedback traceability present | All 12 items mapped to files with before/after scores | ✅ |
| P15 | No runtime/engine/frontend/backend/test files modified | `git diff --name-only` verified | Pending |
| P16 | Tavily MCP used exclusively for research | 13 searches logged, no fallback | ✅ |
| P17 | old_repo_context_unverified claims marked | Missing files explicitly noted | ✅ |
| P18 | ACCP report updated | Reflects hardening pass | Pending |

## Technical Acceptance Checklist (10 items)

| # | Criterion | Threshold | Status |
|---|----------|-----------|--------|
| T1 | RL concepts correctly explained | Bellman, MDP, Q-learning, policy gradient, offline RL | ✅ |
| T2 | IQL architecture correctly described | Expectile regression, in-sample only, AWR extraction | ✅ |
| T3 | CQL correctly described | Conservative penalty, lower bound, α sensitivity | ✅ |
| T4 | Safe RL shielding correctly applied | Alshiekh et al. 2018 cited, shield architecture validated | ✅ |
| T5 | Backtest overfitting methods correct | DSR formula, PBO via CSCV, walk-forward with purge+embargo | ✅ |
| T6 | Conformal prediction limitations acknowledged | Exchangeability violation, time-aware variants | ✅ |
| T7 | Distributional RL correctly described | QR-DQN quantile regression, IQN implicit quantiles | ✅ |
| T8 | OPE/FQE correctly described | FQE algorithm, importance sampling limitations | ✅ |
| T9 | XGBoost applicability correctly justified | Grinsztajn et al. 2022, tree advantages on tabular data | ✅ |
| T10 | Repo-specific claims verified | All file paths verified against v7-engine | ✅ |

## Business Acceptance Checklist (10 items)

| # | Criterion | Threshold | Status |
|---|----------|-----------|--------|
| B1 | Strategic rationale clear | Why build, why advisory, why not autonomous | ✅ |
| B2 | Milestone investment plan exists | Table with cost, evidence, decision, funding, kill condition | ✅ |
| B3 | ROI scenarios realistic | Conservative/base/aggressive/failure with explicit assumptions | ✅ |
| B4 | Break-even analysis present | Engineering cost breakeven, false veto tolerance | ✅ |
| B5 | Sensitivity matrix present | 13 variables with direction, risk, measurement, mitigation | ✅ |
| B6 | Kill conditions defined | 7 specific conditions that would terminate the project | ✅ |
| B7 | No profit guarantee claimed | Explicit disclaimer in profitability_calculation.md §14 | ✅ |
| B8 | Data requirements specified | Shadow period, DSR significance, PBO, regime coverage | ✅ |
| B9 | Stakeholder map complete | 6 stakeholder roles with decision authority | ✅ |
| B10 | Unit economics operational | Per-signal, per-verdict costs and value mechanisms | ✅ |

## Research Acceptance Checklist (8 items)

| # | Criterion | Threshold | Status |
|---|----------|-----------|--------|
| R1 | ≥ 15 research topics covered | Each with dedicated deep-dive doc | ✅ |
| R2 | Each doc has ≥ 2 credible sources | Primary papers preferred | ✅ |
| R3 | Each doc has "how it fails" section | Honest limitations | ✅ |
| R4 | Each doc has business implication | Not just technical | ✅ |
| R5 | Each doc has implementation implication | V7-specific | ✅ |
| R6 | Each doc has explicit decision | Use now / use later / reject | ✅ |
| R7 | Source inventory includes Tavily log | 13 searches documented | ✅ |
| R8 | Trust ratings explained | Highest / High / Medium criteria | ✅ |

## Implementation Readiness Checklist (10 items)

| # | Criterion | Threshold | Status |
|---|----------|-----------|--------|
| I1 | 12-PR sequence defined | Each with scope, files, allowed/forbidden, acceptance, rollback | ✅ |
| I2 | 48-item readiness checklist | Schema, data, training, runtime, business, authority categories | ✅ |
| I3 | Contract boundary sketch | Critic verdict → runtime_interpretation mapping | ✅ |
| I4 | Data flow map | AlphaForge → V7 gates → critic → portfolio → risk → execution | ✅ |
| I5 | Storage map | Replay buffer schema, retention policy | ✅ |
| I6 | Test map | 5 test files listed with purpose | ✅ |
| I7 | Rollback map | Per-PR rollback procedure | ✅ |
| I8 | Authority boundary map | Files that must not be touched per phase | ✅ |
| I9 | Telemetry fields defined | 11 minimum fields required per phase | ✅ |
| I10 | Definition of implementation-ready | 6 conditions | ✅ |

## PR Readiness Checklist (6 items)

| # | Criterion | Threshold | Status |
|---|----------|-----------|--------|
| PR1 | Branch clean | Only allowed paths modified | Pending |
| PR2 | No forbidden paths | Zero runtime/engine/frontend/backend/test changes | Pending |
| PR3 | PR title descriptive | Follows conventional commits | ✅ |
| PR4 | PR body complete | Summary, scope, partner feedback addressed, files, scorecard | ✅ |
| PR5 | Independent review packet ready | Copy-paste ready for external AI | ✅ |
| PR6 | Commit message descriptive | Reflects hardening pass | Pending |

**Total: 62 checklist items**

## Pre-Merge Checklist

- [ ] All 62 items above verified
- [ ] `git diff --name-only` shows only allowed paths
- [ ] No forbidden paths detected
- [ ] Independent AI review packet delivered to external reviewer
- [ ] External AI score ≥ 8.0/10 received
- [ ] Partner approves merge
