# Acceptance Rubric — V7 Policy Critic Docs

## Partner Acceptance Criteria

| # | Criterion | Threshold | Status |
|---|----------|-----------|--------|
| 1 | Docs linked from main entry points | README.md, root ai_summary.md, v7/docs/policy_critic/ai_summary.md all link to policycritic/docs/ | ✅ |
| 2 | Folder tree present | `folder_tree.md` shows planned docs and future implementation layout | ✅ |
| 3 | Implementation file map present | `implementation_file_map.md` maps current files, future files, and untouchable files | ✅ |
| 4 | Problem statement present | `problem_statement.md` answers all required questions | ✅ |
| 5 | Phase plans complete (7 files) | Each with goal, entry/exit criteria, files, risks, rollback | ✅ |
| 6 | Research docs complete (15 files) | Each ≥ 80 lines with abstract, application, failure modes, citations, decision | ✅ |
| 7 | Business plan present | `business_plan.md` with strategic rationale, staged investment, ROI logic | ✅ |
| 8 | Profitability calculation present | `profitability_calculation.md` with formulas, scenarios, break-even, caveats | ✅ |
| 9 | Unit economics present | Per-trade economics, cost structure, margin analysis | ✅ |
| 10 | Risk register present | ≥ 10 risks ranked by probability × impact with mitigations | ✅ (15 risks) |
| 11 | Go-to-market strategy present | Internal rollout, stakeholder map, operational readiness | ✅ |
| 12 | Self-scorecard present | All 10 dimensions scored with evidence | ✅ |
| 13 | Independent review packet present | Written so external AI can review and score | ✅ |
| 14 | Independent AI score ≥ 8/10 | PENDING — external AI review required | ⏳ |
| 15 | No runtime/engine/frontend/backend/test files modified | Verified by `git diff --name-only` | Pending verification |
| 16 | Tavily MCP used exclusively for research | 7 searches logged, no WebSearch/WebFetch fallback | ✅ |
| 17 | All old_repo_context_unverified claims marked | Missing files in v7-engine explicitly noted | ✅ |
| 18 | ACCP completion report updated | Reflects new structure, file count, research coverage | Pending update |

## Pre-Merge Checklist

- [ ] All docs created (35+ files)
- [ ] `git status` clean except new docs
- [ ] Entry points updated with links
- [ ] ACCP report updated
- [ ] PR body includes research summary, file list, design position
- [ ] Independent AI review packet delivered
- [ ] Partner approves for merge

## Post-Merge

- [ ] Independent AI review completed
- [ ] Score ≥ 8/10 confirmed or iterations made
- [ ] Phase 1 (contract) authorized
