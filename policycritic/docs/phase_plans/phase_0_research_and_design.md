# Phase 0 — Research and Design

> Status: **IN PROGRESS** (current phase)
> Duration: 2-3 weeks estimated

## Goal

Complete all research documentation and design specification for the V7 Policy Critic. Produce a partner-grade docs package that an independent AI can score at 8/10 or higher. Establish design lock on the advisory architecture, authority boundaries, and staged rollout plan.

## Entry Criteria

- [x] Branch `pr/v7-policycritic-docs` exists in v7-engine
- [x] Old source material reviewed from `trading-bot-pr`
- [x] Repo-specific claims verified against v7-engine
- [x] Tavily MCP authenticated and usable for research
- [ ] (in progress) All research topics covered with separate deep docs
- [ ] (in progress) Business plan and profitability calculation docs

## Deliverables

### Documentation (policycritic/docs/)

| File | Status |
|------|--------|
| `README.md` | ✅ Done |
| `ai_summary.md` | ✅ Done (needs update for new structure) |
| `folder_tree.md` | ✅ Done |
| `implementation_file_map.md` | ✅ Done |
| `problem_statement.md` | ✅ Done |
| `policy_critic_design.md` | ✅ Done |
| `rl_intro_for_v7.md` | ✅ Done |
| `pipeline.md` | ✅ Done |
| `authority_and_boundaries.md` | ✅ Done |
| `replay_buffer_design.md` | ✅ Done |
| `rollout_plan.md` | ✅ Done |
| `source_inventory.md` | ✅ Done (needs update for new sources) |

### Phase Plans

| File | Status |
|------|--------|
| `phase_plans/README.md` | ✅ Done |
| `phase_plans/phase_0_*.md` | ✅ This file |
| `phase_plans/phase_1_*.md` through `phase_6_*.md` | 🔧 Creating |

### Research Deep-Dives

| File | Status |
|------|--------|
| `research/README.md` | 🔧 Creating |
| `research/rl_basics.md` through `trading_rl_failure_modes.md` (15 files) | 🔧 Creating |

### Business Plan

| File | Status |
|------|--------|
| `business/README.md` through `go_to_market_internal_strategy.md` (6 files) | 🔧 Creating |

### Quality

| File | Status |
|------|--------|
| `quality/README.md` through `acceptance_rubric.md` (4 files) | 🔧 Creating |

## Exit Criteria

- [ ] All 35+ docs created with substantive content
- [ ] Every major RL topic has a dedicated research doc with citations
- [ ] Business plan includes scenario-based profitability calculation
- [ ] Quality self-scorecard completed with all 10 dimensions scored
- [ ] Independent AI review packet written
- [ ] Main entry points (README.md, ai_summary.md root and v7/docs/policy_critic/) link to new docs
- [ ] ACCP completion report updated
- [ ] PR opened with complete body
- [ ] Docs package self-scores ≥ 8/10

## Files Involved

**Created**: ~35 new files under `policycritic/docs/`
**Modified**: `policycritic/docs/README.md`, `policycritic/docs/ai_summary.md`, `policycritic/docs/source_inventory.md`, `reports/accp/accp_v7_policycritic_docs_completion.accp.yaml`, possibly `README.md` root, `ai_summary.md` root, `v7/docs/policy_critic/ai_summary.md`
**Not touched**: All Python source, contracts, configs, tests, runtime files

## Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| Docs may still score < 8/10 | Medium | Schedule delay | Use self-scorecard to identify weak areas; iterate before claiming complete |
| Research docs too shallow | Medium | Rejection by partner | Each research doc must be ≥ 100 lines with abstract, why it matters, how it applies, how it fails, business implication, implementation implication, citations, decision |
| Business plan lacks realism | Low | Credibility loss | Use scenario-based formulas; clearly state what data is needed before real claims |

## What Must NOT Be Implemented in This Phase

- ❌ Any Python code
- ❌ Any contract schema file
- ❌ Any database migration
- ❌ Any runtime behavior change
- ❌ Any test
- ❌ Any config change
- ❌ Any import of new libraries
- ❌ PR creation (docs must be reviewed first)

## Rollback Plan

Trivial: all changes are docs-only under `policycritic/docs/` and `reports/accp/`. Revert by deleting these directories and the commit.
