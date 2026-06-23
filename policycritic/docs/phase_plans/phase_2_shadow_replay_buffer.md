# Phase 2 — Shadow Replay Buffer

> Status: NOT STARTED
> Prerequisite: Phase 1 complete (PolicyCriticReview contract registered)
> Duration: 3-4 weeks estimated

## Goal

Build the replay buffer emitter that pairs canonical market state at decision time with authoritative SimulationOutput to produce (state, action, realized_r_net, mae_r, next_state, terminal) tuples. Store tuples in PostgreSQL. Zero live influence — data recording only.

## Entry Criteria

- [ ] Phase 1 exit criteria met (contract registered)
- [ ] DecisionEvent → TradeOutcome linkage verified as reliable
- [ ] Next-state definition agreed (state at next scheduled analysis, not state at exit)
- [ ] Reward normalization scheme agreed (train-split statistics, frozen for val/test)
- [ ] Data split strategy validated (temporal, purged, embargoed)

## Deliverables

1. **`runtime/db/repos/replay_buffer_repo.py`** — `ReplayBufferTuple` CRUD operations. Schema: `id UUID PK`, `signal_id UUID`, `state_json JSONB`, `action VARCHAR(16)`, `reward_r DOUBLE PRECISION`, `drawdown_mae_r DOUBLE PRECISION`, `next_state_json JSONB`, `terminal BOOLEAN`, `lineage_json JSONB`, `created_at_utc TIMESTAMP`, `data_split VARCHAR(16)`.

2. **`runtime/services/policy/replay_buffer_emitter.py`** — Tuple assembler service. For each resolved DecisionEvent: (a) fetch canonical state at decision time from snapshot, (b) fetch SimulationOutput from simulation engine replay adapter, (c) extract `realized_r_net` from ActionOutcome, `mae_r` from PathMetrics, (d) fetch next state at next scheduled analysis, (e) determine terminal from exit_reason, (f) assemble and persist tuple.

3. **Database migration** — Add `replay_buffer_tuple` table with indexes on signal_id, data_split, (symbol, regime_label).

4. **NO_TRADE record support** — Emit tuples where action=NO_TRADE with reward=0.0, drawdown_proxy=0.0. Use SimulationOutput.NoTradeOutcome for saved_loss_r / missed_opportunity_r metadata.

## Exit Criteria

- [ ] ≥ 1000 resolved tuples stored covering 3+ market regimes
- [ ] NO_TRADE records ≥ 20% of total
- [ ] Data split validated (70/15/15 train/val/test, temporal, no leakage)
- [ ] Reward normalization statistics computed on training split only
- [ ] Tuple completion rate > 95%
- [ ] Terminal episodes ≥ 5%
- [ ] All supported symbols present
- [ ] Temporal leakage test passes (no future information in state)
- [ ] Integration test: emit → store → retrieve → validate roundtrip

## Files Involved

**Created**: `runtime/db/repos/replay_buffer_repo.py`, `runtime/services/policy/__init__.py`, `runtime/services/policy/replay_buffer_emitter.py`
**Modified**: Database migration file (new)

## Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| Two simulation paths diverge | High | Wrong reward values | Route through `/simulation` engine, NOT runtime historical engine |
| Next-state definition ambiguous | Medium | Broken Markov property | Explicit spec: state at next scheduled analysis timestamp |
| Temporal leakage in data splits | Medium | Invalid evaluation | Purge + embargo; validate with leakage detection test |
| NO_TRADE under-representation | Medium | Biased training | Enforce ≥ 20% NO_TRADE; stratified sampling by regime |

## What Must NOT Be Implemented in This Phase

- ❌ Any critic training (needs tuples first)
- ❌ Any critic inference in scan loop
- ❌ Any live influence on execution
- ❌ Any reward function beyond simulation's existing `realized_r_net`

## Rollback Plan

Drop `replay_buffer_tuple` table. Remove emitter service. Revert migration. Data is training-only; no production impact.
