# Phase Plans — V7 Policy Critic

> Status: Docs/Design Only
> Created: 2026-06-23

## Overview

The Policy Critic is deployed across 7 phases (Phase 0 through Phase 6). Each phase has explicit entry criteria, exit criteria, file scope, risks, and rollback plans.

**Phase 0 is the current phase** (docs/design only). Phases 1-6 are planned but not started.

## Phase Summary

| Phase | Name | Duration (est.) | Live Authority | Status |
|-------|------|----------------|----------------|--------|
| 0 | Research and Design | 2-3 weeks | None | **IN PROGRESS** |
| 1 | Observability and Schema | 2-3 days | None | NOT STARTED |
| 2 | Shadow Replay Buffer | 3-4 weeks | None | NOT STARTED |
| 3 | Offline Training and Evaluation | 12-18 weeks | None | NOT STARTED |
| 4 | Shadow Critic Runtime | 2-3 weeks | Shadow only | NOT STARTED |
| 5 | Guarded Influence | 8-12 weeks | Advisory (gated) | NOT STARTED |
| 6 | Business Validation | 12+ weeks | Conditional | NOT STARTED |

## Reading Order

1. `phase_0_research_and_design.md` — Current phase: docs, research, design lock
2. `phase_1_observability_and_schema.md` — Contracts, schemas, audit trail
3. `phase_2_shadow_replay_buffer.md` — Replay buffer emitter + storage
4. `phase_3_offline_training_and_evaluation.md` — Supervised + OPE + IQL training
5. `phase_4_shadow_critic_runtime.md` — Shadow-only critic in scan loop
6. `phase_5_guarded_influence.md` — Advisory influence with hard gate limits
7. `phase_6_business_validation.md` — Profitability evidence, live readiness

## Gate Principle

**Each phase transition requires evidence, not ambition.** No phase may begin before its predecessor's exit criteria are met. Human approval is required for any transition beyond Phase 4.
