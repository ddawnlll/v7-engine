# Go-to-Market Internal Strategy — V7 Policy Critic

## 1. Internal Rollout Model

The Policy Critic is an **internal tool** — it is not a customer-facing product. "Go-to-market" means deployment into the V7 trading pipeline, with the operator as the primary user.

## 2. Stakeholder Map

| Stakeholder | Role | Concerns |
|------------|------|---------|
| **Quant/Trader** | Defines reward function, evaluates critic quality | "Does this actually improve PnL?" |
| **ML Engineer** | Builds replay buffer, trains critic models | "Is the data pipeline reliable?" |
| **Backend Engineer** | Wires critic into scan runtime | "Will this slow down the scan loop?" |
| **Risk Manager** | Approves live influence, monitors drawdown | "Can this lose more money than baseline?" |
| **Operator** | Views critic verdicts in dashboards | "Do I trust these recommendations?" |
| **Partner/PM** | Approves phase transitions, allocates resources | "What's the ROI timeline?" |

## 3. Phased Rollout to Stakeholders

### Phase 0-1: Design & Schema
- **Audience**: Quant, ML Engineer, Partner
- **Deliverable**: Docs package (this repo)
- **Buy-in needed**: Proceed to contract definition

### Phase 2-3: Infrastructure & Training
- **Audience**: ML Engineer, Backend Engineer
- **Deliverable**: Replay buffer + trained V2 critic
- **Buy-in needed**: DSR/PBO pass → proceed to shadow runtime

### Phase 4: Shadow Runtime
- **Audience**: Backend Engineer, Operator (dashboard visibility only)
- **Deliverable**: Critic recording verdicts, zero influence
- **Buy-in needed**: 30 days stable → proceed to guarded influence

### Phase 5: Guarded Influence
- **Audience**: All stakeholders
- **Deliverable**: Advisory influence in SWING mode
- **Buy-in needed**: Human approval at each sub-stage; no safety degradation

### Phase 6: Business Validation
- **Audience**: Partner, Risk Manager
- **Deliverable**: ≥ 90 days evidence package
- **Buy-in needed**: Live readiness decision (or permanent shadow)

## 4. Operational Readiness Checklist

### Before Shadow Runtime (Phase 4)
- [ ] PolicyCriticReview contract registered
- [ ] Replay buffer populated and validated
- [ ] V2 critic trained, OPE-validated
- [ ] Critic inference latency < 10ms p99
- [ ] Safe degrade path tested (critic unavailable → system unchanged)
- [ ] Shadow persistence tested under load
- [ ] Dashboard showing critic verdicts ready

### Before Guarded Influence (Phase 5)
- [ ] ≥ 30 days stable shadow operation
- [ ] V3 IQL critic trained, FQE-validated
- [ ] DSR p<0.05, PBO<0.10 maintained
- [ ] Human approval documented
- [ ] Kill-switch tested (disable critic → revert to gate-only)
- [ ] Per-regime monitoring dashboard ready
- [ ] Rollback plan tested

### Before Live Consideration (Phase 6)
- [ ] ≥ 90 days guarded influence evidence
- [ ] Net improvement DSR significant
- [ ] No safety metric degradation
- [ ] V4 optimizer validated (if applicable)
- [ ] Formal shield compliance verified
- [ ] All stakeholders signed off

## 5. Communication Plan

| Phase Transition | Communication | Format |
|-----------------|--------------|--------|
| Design lock | Partner review of docs package | PR review |
| Contract registered | Technical notice | PR merge |
| Shadow runtime | Dashboard announcement | Internal channel |
| Guarded influence enabled | All-hands notice + risk briefing | Meeting + documentation |
| Business validation complete | Evidence package presentation | Report + meeting |

## 6. Failure Communication

If the critic degrades or is rolled back:
1. **Immediate**: Kill-switch via config → system reverts to gate-only
2. **Within 24 hours**: Incident report with root cause
3. **Within 1 week**: Decision on re-enablement conditions

## 7. Organizational Buy-In Requirements

| Decision | Approver | Documentation Required |
|----------|---------|----------------------|
| Proceed to Phase 1 | Partner | Design package approval |
| Proceed to Phase 3 (training) | Partner + ML Lead | Replay buffer validation report |
| Enable shadow runtime | Engineering Lead | Integration test pass |
| Enable DOWNWEIGHT_CONFIDENCE | Risk Manager + Partner | Shadow evidence + DSR/PBO |
| Enable VETO_TO_NO_TRADE | Risk Manager + Partner | Extended shadow evidence + human approval |
| Live consideration | All stakeholders | ≥ 90 days evidence package |
