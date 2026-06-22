# Independent AI Review Packet — V7 Policy Critic

> **Status**: PENDING — this packet is written for an external AI (ChatGPT, Claude separate instance, or other) to review the docs and produce a score.
> **Pass threshold**: 8/10 minimum

## Instructions for Reviewing AI

You are reviewing a docs/design package for a "V7 Policy Critic" — an advisory safety layer for an algorithmic trading system. Your task: read the docs listed below and score the package across 10 dimensions on a 0-10 scale.

### What This Package Is

The V7 Policy Critic is a proposed learned component that reviews trade decisions from a supervised model (XGBoost-based AlphaForge scorer), scores risk, adjusts confidence, and recommends NO_TRADE when expected value is negative. It is strictly advisory — deterministic safety gates sit above it and retain hard veto.

The package is **docs/design only**. No implementation exists. No runtime behavior has been changed.

### Scoring Dimensions

For each dimension, provide a score (0-10) and 2-3 sentences of evidence.

1. **Repo integration** — Are docs linked from main entry points? Is the folder structure clear? Can a new engineer find their way?
2. **Technical correctness** — Are claims about the codebase verified? Are RL concepts correctly explained? Are citations accurate?
3. **Research depth** — Do research docs cover each topic substantively? Are primary sources preferred over blogs? Are limitations honestly discussed?
4. **Implementation readiness** — Do phase plans specify exact files, entry/exit criteria, risks, and rollback plans? (Note: low implementation readiness by design — this is a docs phase.)
5. **Business usefulness** — Is there a clear business case? Are ROI scenarios realistic? Are costs estimated?
6. **Risk realism** — Are failure modes honestly catalogued? Are mitigations credible? Is residual risk assessed?
7. **Profitability modeling quality** — Are formulas explicit? Are scenarios conservative? Are caveats documented?
8. **Authority boundary clarity** — Is the veto chain clear? Is the advisory-only constraint consistently reinforced?
9. **Phase plan clarity** — Are phases well-scoped? Are evidence gates explicit? Is rollback specified?
10. **Citation quality** — Are sources peer-reviewed where possible? Are URLs provided? Are trust ratings explained?

### Docs to Review

Start with these entry points:
1. `policycritic/docs/README.md`
2. `policycritic/docs/ai_summary.md`
3. `policycritic/docs/problem_statement.md`
4. `policycritic/docs/folder_tree.md`

Then review one doc from each section as a sample:
5. `policycritic/docs/phase_plans/phase_3_offline_training_and_evaluation.md`
6. `policycritic/docs/research/implicit_q_learning_iql.md`
7. `policycritic/docs/business/profitability_calculation.md`
8. `policycritic/docs/quality/self_scorecard.md`

If time permits, skim additional docs for depth assessment.

### Output Format

```
## Independent AI Review — V7 Policy Critic Docs

### Scores

| # | Dimension | Score (/10) | Evidence |
|---|-----------|------------|----------|
| 1 | Repo integration | X | ... |
| ... | ... | ... | ... |

### Overall: X.X / 10

### Pass/Fail: [PASS if ≥ 8.0, FAIL otherwise]

### Strengths
- ...

### Weaknesses
- ...

### Most Underdeveloped Area
- ...

### Recommendation
- [MERGE READY / NEEDS WORK / REJECT]
```

## Repo Context (for the Reviewing AI)

- The v7-engine repo is in early design phase. `v7/src/` is greenfield (only `.gitkeep`).
- AlphaForge (XGBoost scorer) is spec-only; P5/P6/P9 phases not started.
- The V6 inference engine lives in a sibling repo, not v7-engine.
- The simulation engine (`simulation/engine/engine.py`) is implemented and produces the authoritative reward surface.
- `runtime/db/repos/shadow_policy_repo.py` and `policy_dataset_repo.py` exist.
- Old-repo claims that could not be verified are marked `old_repo_context_unverified`.

## Note on Self-Score

Claude's internal self-assessment scored this package at 8.1/10. Your independent score may differ. Please score honestly — the goal is partner-grade quality, not ego.
