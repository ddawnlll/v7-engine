# Reviewer Guide — V7 Policy Critic PR

> **Goal**: Help partners and reviewers assess this PR quickly and confidently.

## Recommended Reading Order

### Quick Review (~10 minutes)
1. `executive_one_pager.md` — 3-minute summary
2. `diagrams.md` — Visual architecture (5 Mermaid diagrams)
3. `problem_statement.md` — What problem, why now, what's out of scope
4. `quality/self_scorecard.md` — How we rate ourselves (8.7/10)

### Medium Review (~30 minutes)
Add:
5. `decision_records.md` — 8 ADRs explaining key choices
6. `implementation_file_map.md` — What files exist now, what's planned
7. `business/profitability_calculation.md` — Scenario-based value estimate
8. `quality/partner_feedback_traceability.md` — How we addressed partner concerns

### Deep Review (~90 minutes)
Add:
9. `phase_plans/README.md` + one sample phase (e.g., `phase_3_offline_training_and_evaluation.md`)
10. `research/README.md` + one sample research doc (e.g., `implicit_q_learning_iql.md`)
11. `business/business_plan.md` — Full business case
12. `business/risk_register.md` — 25 risks
13. `quality/acceptance_rubric.md` — 62-item checklist

## What to Check First

### 1. Authority Boundary (CRITICAL)
Verify the critic never claims final authority. Check:
- `executive_one_pager.md` §4: Shield architecture diagram
- `decision_records.md` ADR-001: "Policy Critic Is Advisory Only"
- `diagrams.md` §1: Red boxes (gates) above blue box (critic)
- `policy_critic_design.md` §5-8: Advisory-only design, no execution authority

### 2. Profitability Honesty (CRITICAL)
Verify no profit guarantees. Check:
- `business/profitability_calculation.md` §14: "Why This Is Not a Profit Guarantee"
- `executive_one_pager.md` §6: "Why Profitability Is Not Guaranteed"
- All scenario tables labeled "illustrative" or "DO NOT BUDGET AGAINST THIS"

### 3. Docs-Only Verification
Run these commands to confirm no code was changed:

```bash
# Show only docs and report changes
git diff --name-only main...pr/v7-policycritic-docs

# Show change statistics
git diff --stat main...pr/v7-policycritic-docs

# Confirm no runtime/engine/frontend/backend files
git diff --name-only main...pr/v7-policycritic-docs | grep -E "^(runtime|engine|simulation|contracts|tests|interface)/|\.py$|\.ts$|\.tsx$|\.rs$"
# Should return empty (no matches)
```

## What Changed

| Area | What Was Added |
|------|---------------|
| **Core docs** | README, ai_summary, folder_tree, implementation_file_map, problem_statement |
| **Design** | Architecture, authority boundaries, pipeline, replay buffer spec, rollout plan |
| **Phase plans** | 7 files (P0-P6) with entry/exit criteria, PR sequence, rollback |
| **Research** | 15 deep-dive docs covering all major RL topics |
| **Business** | Business plan, profitability calc, unit economics, risk register (25 risks), GTM |
| **Quality** | Self-scorecard, AI review packet, acceptance rubric (62 items), partner traceability |
| **Reviewer tools** | Executive one-pager, Mermaid diagrams, ADRs (8), this reviewer guide |
| **Entry points** | README.md, ai_summary.md, v7/docs/policy_critic/ai_summary.md (links added) |

## What Did NOT Change

- ❌ Zero Python files
- ❌ Zero TypeScript/React files
- ❌ Zero contract/schema files
- ❌ Zero config files
- ❌ Zero test files
- ❌ Zero database migrations
- ❌ Zero new dependencies
- ❌ Zero .claude/ files committed

## How to Verify Authority Boundary

The Policy Critic must never appear above gates in any diagram or description.

Checklist:
- [ ] `diagrams.md` §1: Red gates above blue critic
- [ ] `policy_critic_design.md`: "What the Policy Critic CANNOT Do" table present
- [ ] `authority_and_boundaries.md`: Veto chain clearly shows critic at Level 4 (advisory)
- [ ] `decision_records.md` ADR-001: Advisory-only rationale documented
- [ ] `implementation_file_map.md` §7: "Why the Critic Cannot Become Final Authority"

## How to Verify Business/Profitability Honesty

Checklist:
- [ ] `profitability_calculation.md` §14 has explicit "no profit guarantee" statement
- [ ] All scenario tables labeled "illustrative" or have "DO NOT BUDGET" warning
- [ ] Failure scenario included (critic degrades performance)
- [ ] Sensitivity matrix acknowledges uncertainty
- [ ] Business invalidation conditions documented
- [ ] Data requirements before real claims are explicit

## How to Verify Implementation Readiness

Checklist:
- [ ] `implementation_file_map.md` §4: 12-PR sequence with granular specs
- [ ] `implementation_file_map.md` §5: 48-item checklist
- [ ] `implementation_file_map.md` §6: Definition of implementation-ready
- [ ] Phase plans have specific quantitative exit criteria (DSR p<0.05, PBO<0.10, etc.)
- [ ] Rollback plan exists for each phase

## Known Limitations

| Limitation | Honest Assessment |
|-----------|------------------|
| Financial applicability of IQL/CQL | Unproven — all published results on D4RL game tasks |
| Profitability numbers | Illustrative only — no shadow data exists |
| Conformal coverage on financial time series | Exchangeability violated — approximate coverage accepted |
| Replay buffer minimum sizes | Heuristic estimates — need power analysis with real data |
| v7/src greenfield | No V7-native code exists — docs/design only |
| Independent AI review | Pending — must be performed by external AI |

## Merge Checklist

- [ ] Authority boundary verified (critic never above gates)
- [ ] Profitability claims verified as honest (no guarantees, all caveats present)
- [ ] `git diff --name-only main...pr/v7-policycritic-docs` shows only allowed paths
- [ ] No forbidden paths (runtime/, engine/, simulation/, contracts/, tests/, interface/, .py, .ts, .tsx, .rs)
- [ ] Independent AI review submitted and score ≥ 8.0/10 received
- [ ] Partner approval obtained

## Quick Commands for Reviewers

```bash
# Verify branch and status
git branch --show-current        # Should be: pr/v7-policycritic-docs
git status --short               # Should be clean or only policycritic/docs/ changes

# Verify no code changes
git diff --name-only main...pr/v7-policycritic-docs | grep -c "\.py$\|\.ts$\|\.tsx$\|\.rs$"
# Should output: 0

# Count files changed
git diff --stat main...pr/v7-policycritic-docs | tail -1

# List all policycritic docs
find policycritic/docs -type f | sort
```
