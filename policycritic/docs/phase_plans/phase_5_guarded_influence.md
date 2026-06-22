# Phase 5 — Guarded Influence

> Status: NOT STARTED
> Prerequisite: Phase 4 complete (shadow critic stable ≥ 30 days)
> Duration: 8-12 weeks estimated

## Goal

Enable the Policy Critic to exert **advisory influence** on trade execution within explicit hard gate limits. The critic's DOWNWEIGHT_CONFIDENCE and VETO_TO_NO_TRADE verdicts are **enacted by V7 policy** (not by the critic directly). SWING mode first. Human approval required at every sub-stage.

## Sub-Phase 5A: DOWNWEIGHT_CONFIDENCE (SWING only, 4-6 weeks)

### Goal
Enable the critic's confidence downweight recommendation to affect the confidence gate.

### Mechanism
1. Critic emits `DOWNWEIGHT_CONFIDENCE` with `confidence_adjustment_factor` (e.g., 0.6)
2. V7 policy multiplies `confidence_final_score` by `confidence_adjustment_factor`
3. Re-tripped confidence gate may block the trade
4. Verdict recorded in `runtime_interpretation.suppression_reason = 'critic_downweighted'`

### Exit Criteria
- Downweight rate bounded (not 0%, not 100%)
- Shadow comparison: downweighted trades have worse realized outcomes than non-downweighted (confirms critic is identifying risk)
- Human approval

## Sub-Phase 5B: VETO_TO_NO_TRADE (SWING only, 4-6 weeks)

### Goal
Enable the critic's NO_TRADE veto recommendation to be enacted by V7 policy.

### Mechanism
1. Critic emits `VETO_TO_NO_TRADE` with rationale
2. V7 policy sets `recommended_action = NO_TRADE`
3. `policy_passed = false`, `suppression_reason = 'critic_veto'`
4. This is an advisory veto made effective BY policy, not by the critic directly

### Exit Criteria
- Veto rate bounded away from 0 and 1
- Shadow comparison: vetoed trades would have had worse realized outcomes
- DSR p < 0.05 and PBO < 0.10 maintained
- Walk-forward ≥ 4/5 folds maintained
- No safety metric degradation
- Human approval

## Entry Criteria

- [ ] Phase 4 exit criteria met (shadow critic stable ≥ 30 days)
- [ ] ≥ 10,000 replay buffer tuples
- [ ] V3 IQL critic trained and OPE-validated (for 5B)
- [ ] Human approval for Phase 5 start
- [ ] SWING mode only (SCALP/AGGRESSIVE remain HOLD)

## Exit Criteria

- [ ] 5A and 5B exit criteria met
- [ ] Critic verdict audit trail complete for all influenced decisions
- [ ] Per-regime breakdown shows no single-regime degradation
- [ ] FQE CI overlap maintained (live shadow OPE vs realized)
- [ ] 30-day stable operation with guarded influence
- [ ] Human approval for continued operation

## Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| Critic becomes de facto gate (over-trust) | Medium | Bypasses gate intent | Config-gated; human approval required; kill-switch |
| Veto rate too high (conservative collapse) | Medium | Blocks profitable trades | Monitor veto rate; bounded check |
| Veto rate too low (ineffective) | Medium | Adds complexity without value | Compare vetoed vs non-vetoed outcomes |
| Regime-specific degradation | Medium | Loses money in specific regimes | Per-regime monitoring; auto-degrade on detection |
| Human over-reliance on critic | Low | Reduced oversight | Mandatory periodic review; no automation of trust |

## What Must NOT Be Implemented in This Phase

- ❌ Critic opening or closing trades
- ❌ Critic bypassing any hard gate
- ❌ SCALP/AGGRESSIVE live influence (HOLD)
- ❌ V4 sizing/exit proposals (Phase 6)
- ❌ Autonomous live trading without human approval
- ❌ Removal of the safe degrade path

## Rollback Plan

Disable critic influence via `POLICY_CRITIC_MODE=shadow` (revert to Phase 4 behavior). All execution reverts to gate-only. Audit trail preserved.
