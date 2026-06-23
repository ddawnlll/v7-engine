# Research — V7 Policy Critic

> Status: Docs/Design Only
> Created: 2026-06-23

## Overview

This directory contains deep-dive research documents on every major topic relevant to the V7 Policy Critic. Each doc follows a consistent structure: abstract, why it matters for V7, what the literature says, how it applies, how it can fail, business implication, implementation implication, citations, and decision (use now, later, or reject).

## Reading Order

1. **Foundation**: `rl_basics.md` → `offline_rl.md`
2. **Core algorithms**: `implicit_q_learning_iql.md` → `conservative_q_learning_cql.md`
3. **Alternative approaches**: `decision_transformer.md` → `distributional_rl_quantile_q.md`
4. **Safety & evaluation**: `safe_rl_and_shielding.md` → `ope_and_fqe.md` → `conformal_calibration.md` → `backtest_overfitting_dsr_pbo.md`
5. **Failure modes**: `reward_hacking.md` → `trading_rl_failure_modes.md`
6. **Domain context**: `financial_ml_validation.md` → `gbdt_vs_deep_rl_for_tabular_finance.md`

## Research Methodology

All research conducted via Tavily MCP (`mcp__tavily__tavily-search`). Primary sources (arXiv, conference proceedings, journal papers) preferred. Blog posts and community sources used only for educational context, not for design decisions.

## Source Trust Ratings

| Rating | Criteria |
|--------|----------|
| Highest | Peer-reviewed conference/journal paper or established textbook |
| High | Preprint with strong evidence, official implementation, or widely-cited |
| Medium | Blog post, community resource, or secondary source |

## Decision Taxonomy

| Decision | Meaning |
|----------|---------|
| **USE NOW** | Recommended for current/next implementation phase |
| **USE LATER** | Promising but requires prerequisites (data, infrastructure, validation) |
| **REJECT** | Not suitable for V7; documented rationale |
