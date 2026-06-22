# Phase 6 — Business Validation

> Status: NOT STARTED
> Prerequisite: Phase 5 complete (guarded influence stable ≥ 60 days)
> Duration: 12+ weeks estimated

## Goal

Produce statistically significant evidence that the Policy Critic improves net trading expectancy without degrading any safety metric. This is the evidence package required before any live promotion consideration. V4 constrained optimizer sizing/exit proposals are developed and validated in this phase.

## Sub-Phase 6A: Profitability Evidence (8-12 weeks)

### Goal
Run shadow comparison over ≥ 90 days to measure critic impact on net expectancy.

### Metrics
- Net expectancy (realized_r_net) with critic vs without critic (shadow baseline)
- DSR p-value for improvement
- Per-regime breakdown (trending, ranging, volatile, transition)
- Drawdown profile comparison (max drawdown, avg drawdown duration)
- Win rate, average win, average loss, profit factor comparison
- Trade frequency impact (does critic reduce overtrading?)

### Exit Criteria
- Improvement DSR p < 0.05
- No per-regime degradation
- No drawdown profile worsening
- ≥ 90 days of continuous shadow comparison

## Sub-Phase 6B: V4 Constrained Optimizer (12-16 weeks)

### Goal
Develop critic-driven sizing and exit proposals within explicit shield constraints.

### Deliverables
- `v7/src/v7/alpha/policy_bridge/policy_critic/constrained_optimizer_v4.py`
- Formal shield compliance verification
- Adversarial simulation test suite
- Stress test suite (flash crash, extreme volatility, liquidity crisis)

### Exit Criteria
- Shield compliance: 100% (zero violations)
- Sizing proposals within gate bounds
- Multi-regime validation (≥ 5 regimes)
- Adversarial simulation pass
- Stress testing pass
- Human approval

## Entry Criteria

- [ ] Phase 5 exit criteria met
- [ ] Guarded influence stable ≥ 60 days
- [ ] ≥ 90 days shadow comparison data
- [ ] DSR/PBO/FQE all maintained
- [ ] Human approval for Phase 6 start

## Exit Criteria

- [ ] Business case validated: statistically significant net improvement
- [ ] V4 optimizer validated and shield-compliant
- [ ] All metrics maintained across ≥ 90 days
- [ ] Live readiness checklist completed
- [ ] Human approval (mandatory — no automation)

## Files Involved

**Created**: `v7/src/v7/alpha/policy_bridge/policy_critic/constrained_optimizer_v4.py`, adversarial test suite, stress test suite
**Modified**: None (critic already wired from Phase 4-5)

## Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| Improvement not statistically significant | Medium | Critic adds complexity without value | Honest assessment; may recommend critic removal |
| V4 sizing proposals amplify risk | Medium | Real financial loss | Shield compliance gating; human approval |
| Regime shift during validation period | Medium | Invalidates before/after comparison | Multi-regime requirement; long validation period |
| Live readiness never achieved | Low | Critic remains advisory shadow permanently | Acceptable outcome — critic still provides audit value |

## What Must NOT Be Implemented in This Phase

- ❌ Automatic live promotion (human approval required)
- ❌ Removal of any hard gate
- ❌ SCALP/AGGRESSIVE live influence (permanently HOLD without independent evidence)
- ❌ Autonomous operation without human oversight

## Rollback Plan

Disable V4 optimizer independently of V3 critic. Revert to Phase 5 behavior. All execution reverts.
