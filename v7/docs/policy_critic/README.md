# V7 Policy Critic — Documentation README

## Purpose

This doc set contains the design, research, and codebase mapping for the V7 Policy Critic:
an advisory offline-RL component that reviews the proposed action (LONG/SHORT/NO_TRADE)
and returns a verdict (ALLOW / DOWNWEIGHT_CONFIDENCE / VETO_TO_NO_TRADE / REQUIRE_REVIEW).

The critic is the LOWEST authority in the truth hierarchy (simulation > realized > contract > runtime > model).
It can downgrade but never upgrade execution.

## Doc Tree

| File | Purpose |
|------|---------|
| `ai_summary.md` | Dense synthesis entry point |
| `design.md` | Full design recommendation |
| `codebase_maps/v7_pipeline_map.md` | V7/V6 decision flow, gates, field names |
| `codebase_maps/alphaforge_map.md` | AlphaForge scorer, calibration, field surface |
| `codebase_maps/simulation_map.md` | Simulation cost model, reward, replay |
| `codebase_maps/contracts_runtime_map.md` | Contracts, runtime wiring, PolicyCriticReview |
| `research/offline_rl_methods.md` | IQL/CQL/BCQ/DT literature |
| `research/critic_calibration.md` | QR-DQN, conformal, FQE, Cal-QL |
| `research/reward_design.md` | Cost-aware reward design |
| `research/finance_rl_failures.md` | RL failures in finance, guardrails |

## Reading Order

1. `ai_summary.md` — start here
2. `design.md` — full rationale
3. `codebase_maps/*` — codebase grounding
4. `research/*` — literature grounding (source URLs in each file)

## Lock Status

LOCK_CANDIDATE — not yet LOCKED. Open holds documented in ai_summary.md.

## Source

Generated 2026-06-21 by V7 Policy Critic RL Research Workflow (9 agents, ~1M subagent tokens).
