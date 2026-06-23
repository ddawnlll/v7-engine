# Replay Buffer Design

> Status: Docs/Design Only — Replay buffer does NOT exist in this repo
> Created: 2026-06-23 (adapted from old repo source material)

## 1. Why A Replay Buffer Is Required

### 1.1 The Single Most Critical Missing Infrastructure

The replay buffer is the prerequisite for **all forms of learning from experience**. Without it:

| What's Blocked | Why |
|---|---|
| V2 Supervised Critic | No (state, action, reward) tuples for training |
| V3 Offline IQL Critic | No (s, a, r, s', terminal) tuples for offline RL |
| V4 Constrained Optimizer | No trajectory data for optimization |
| Off-Policy Evaluation (OPE/FQE) | No held-out transition data for evaluation |
| Reward function design | No stored transitions to replay and re-score |
| Regime analysis | No structured data linking state to outcomes |
| Critic calibration | No ground-truth outcome data for calibration curves |

### 1.2 Current State vs Required State

| Capability | Current (v7-engine) | Required (V2+) |
|---|---|---|
| Events recorded | DecisionEvent + TradeOutcome (SQL JOIN) | Structured (s,a,r,s',terminal) tuples |
| Next state | NOT recorded as structured transition | Required (state at next scheduled analysis) |
| Terminal flag | exit_reason on TradeOutcome | Required as explicit boolean |
| Lineage | Partial (signal_id, order_id) | Full (decision_event_id, model_artifact_version, regime_label, data_split) |
| Authoritative reward | `simulation/engine/engine.py` ActionOutcome.realized_r_net | Needs pairing with state at decision time |
| NO_TRADE records | Not stored as transitions | Required (critic must learn when NOT to trade) |
| Drawdown proxy | mae_r on PathMetrics (simulation) / aggregate run-level (runtime) | Per-decision mae_r needed |

---

## 2. Tuple Specification

### 2.1 Required Fields

```
ReplayBufferTuple {
    state:           dict            # Canonical market state at decision time
    action:          str             # LONG_NOW / SHORT_NOW / NO_TRADE
    reward:          float           # realized_r_net — net return in R-multiples after ALL costs
    drawdown_proxy:  float           # mae_r — maximum adverse excursion in R-multiples
    next_state:      dict            # State at next scheduled analysis (same symbol+mode)
    terminal:        bool            # True if end of episode
    lineage:         dict            # Full traceability metadata
}
```

### 2.2 Tuple Assembly

The tuple assembler pairs two data sources that currently exist separately:

1. **State at decision time** → Canonical market snapshot from AlphaForge snapshot builder (planned) or V6 adapter (interim)
2. **Outcome** → `simulation/engine/engine.py` `simulate(SimulationInput) → SimulationOutput`

**Critical rule**: Reward MUST come from `/simulation` engine (authoritative economic truth), NOT from `runtime/services/historical_simulation_engine.py` (separate backtest harness with divergent fee/slippage).

### 2.3 Field Details

#### state
The canonical market state at decision time. Fields: symbol, mode, primary_interval, timestamp, calibrated_p_long/short/no_trade, expected_R_long/short, confidence, confidence_kind, regime, anomaly_score, reconstruction_error, long_alpha_R, short_alpha_R. Source: AlphaForge prediction row (planned) or V6 AnalysisResult (interim).

#### action
Action proposed by the behavioral policy: `"LONG_NOW"`, `"SHORT_NOW"`, `"NO_TRADE"`.

#### reward (realized_r_net)
Net realized return in R-multiples after ALL costs:
```
realized_r_net = realized_r_gross - fee_cost_r - slippage_cost_r
```
From `simulation/engine/engine.py` ActionOutcome. Clip to `[-5R, +5R]` for training stability.

Funding cost is DEFERRED — `realized_r_net` currently excludes funding. Spot-only valid.

#### drawdown_proxy (mae_r)
Maximum Adverse Excursion in R-multiples from `simulation/engine/engine.py` PathMetrics.

#### next_state
State at the **next scheduled analysis** for the same symbol + mode. Preserves the Markov property. NOT the state at trade exit — it's the next regular analysis timestamp.

#### terminal
True if episode ended before next regular analysis: session end, exchange halt, circuit breaker, symbol delisted, data gap. Filter: only `resolution_status == COMPLETE` tuples used for training; exclude UNRESOLVED/INVALIDATED.

#### lineage
```json
{
    "signal_id": "uuid",
    "decision_event_id": "uuid",
    "trade_outcome_id": "uuid",
    "model_artifact_version": "v7_alphaforge_v1",
    "calibration_artifact_version": "v7_calib_v1",
    "data_split": "train",
    "regime_label": "trending_up",
    "generated_at_utc": "2026-06-23T12:00:00Z",
    "resolved_at_utc": "2026-06-23T20:00:00Z",
    "symbol": "BTCUSDT",
    "mode": "SWING",
    "primary_interval": "4h",
    "holding_time_minutes": 480,
    "unclipped_reward_r": 2.3
}
```

---

## 3. NO_TRADE Records

### 3.1 Why NO_TRADE Must Be Recorded

The critic must learn **when NOT trading is correct**. If the replay buffer only contains LONG_NOW/SHORT_NOW actions, the critic learns that "always take some action" is optimal — which is the **opposite** of what we want.

### 3.2 NO_TRADE Tuple

```json
{
    "state": "<state at decision time>",
    "action": "NO_TRADE",
    "reward": 0.0,
    "drawdown_proxy": 0.0,
    "next_state": "<next analysis state>",
    "terminal": false,
    "lineage": {
        "reason": "no_trade_by_model",
        ...
    }
}
```

The simulation engine already evaluates NO_TRADE as a first-class action via `NoTradeOutcome`:
- `saved_loss_r`: avoided loss when directional trade would have lost
- `missed_opportunity_r`: foregone gain when directional trade would have won
- `no_trade_quality`: CORRECT_NO_TRADE / SAVED_LOSS / MISSED_OPPORTUNITY / AMBIGUOUS_NO_TRADE

### 3.3 NO_TRADE Sampling Ratio

During training, NO_TRADE records should be **subsampled** to prevent class imbalance:
- Target ratio: NO_TRADE ≤ 50% of training batch
- Strategy: stratified sampling by regime + action
- Oversample minority actions if needed

---

## 4. Data Quality Requirements

### 4.1 Leakage Prevention

| Leakage Vector | Prevention |
|---|---|
| Future data in state | State is from decision time only; validate with temporal split |
| Train/val/test contamination | `lineage.data_split` enforces strict separation |
| Look-ahead in reward | Reward computed from post-decision data only via simulation engine |
| Regime label contamination | Regime computed from pre-decision data only |
| Next-state glimpse | Next state NEVER used during critic forward pass |

### 4.2 Reward Normalization

Normalization statistics computed on training split only and frozen for val/test.

### 4.3 Minimum Data Requirements

| Requirement | Minimum | Recommended |
|---|---|---|
| Total tuples | 1,000 | 10,000+ |
| Distinct symbols | All supported | All supported |
| Market regimes | ≥ 3 | ≥ 5 |
| Actions per symbol-regime | ≥ 50 | ≥ 200 |
| NO_TRADE ratio | ≥ 20% | 30-40% |
| Terminal episodes | ≥ 5% | 10-15% |
| Data split ratio | 70/15/15 | 70/15/15 |

---

## 5. Storage Design (Sketch Only)

### 5.1 Recommended Approach

Extend existing PostgreSQL infrastructure. The `PolicyDatasetRepository` (`runtime/db/repos/policy_dataset_repo.py`) already handles `PolicyExample` persistence. A `ReplayBufferTuple` table would follow the same pattern.

### 5.2 Why PostgreSQL

- Existing infrastructure — no new systems to maintain
- ACID guarantees for audit trail
- JSONB for flexible lineage metadata
- Adequate for V1-V2 scale (10K-100K tuples)
- Re-evaluate for V3-V4 if performance requires it

---

## 6. What Is Blocked Without The Replay Buffer

| Component | Dependency | Status |
|---|---|---|
| V2 Supervised Critic training | (s, a, r) tuples | **BLOCKED** |
| V3 IQL Critic training | (s, a, r, s', terminal) tuples | **BLOCKED** |
| V4 Constrained Optimizer | Trajectory sequences | **BLOCKED** |
| Off-Policy Evaluation (FQE) | Held-out transition data | **BLOCKED** |
| Reward function iteration | Historical transitions for re-scoring | **BLOCKED** |
| Critic calibration | Ground-truth outcome distribution | **BLOCKED** |
| Backtest overfitting tests (PBO, DSR) | Multiple train/test splits | **BLOCKED** |

---

## 7. Implementation Prerequisites

Before implementing the replay buffer:

1. PolicyCriticReview contract defined and registered in `contracts/registry.json`
2. V1 shadow critic recording PolicyCriticReview records
3. DecisionEvent → TradeOutcome linkage verified as reliable
4. Next-state definition agreed and validated
5. Reward normalization scheme agreed and tested on historical data
6. Data split strategy (temporal) validated on existing datasets
7. Tuple assembler design: pair canonical snapshot at decision time + SimulationOutput

---

## 8. Related Documents

- [[pipeline.md]] — Versioned pipeline showing when replay buffer is needed
- [[rl_intro_for_v7.md]] — Why offline RL requires (s,a,r,s',terminal) tuples
- [[policy_critic_design.md]] — How critic consumes replay buffer data
- [[source_inventory.md]] — Papers on offline RL data requirements
- `v7/docs/policy_critic/codebase_maps/simulation_map.md` — Simulation reward surface + critical findings

## 9. References

- Levine et al. 2020, "Offline Reinforcement Learning: Tutorial, Review, and Perspectives" — [arXiv:2005.01643](https://arxiv.org/abs/2005.01643) (Section 4: data requirements)
- Fu et al. 2021, "Benchmarks for Deep Off-Policy Evaluation" — [arXiv:2103.16526](https://arxiv.org/abs/2103.16526)
- `simulation/engine/engine.py` — Authoritative economic truth: ActionOutcome, NoTradeOutcome, PathMetrics
- `simulation/engine/costs.py` — Cost model (fee + slippage; funding DEFERRED)
- `runtime/db/repos/policy_dataset_repo.py` — Existing policy example persistence
- `runtime/db/repos/shadow_policy_repo.py` — Existing shadow decision persistence
