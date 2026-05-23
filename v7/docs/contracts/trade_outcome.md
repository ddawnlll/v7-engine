# V7 TradeOutcome Contract

## Purpose

This document defines the **`TradeOutcome`** contract for V7.

`TradeOutcome` is the atomic **system-level normalized outcome record** attached to one `DecisionEvent`.

It answers one question:

> After one normalized decision event exists, how should the system represent what eventually happened in a normalized, auditable, replay-compatible, and learning-compatible way?

This document defines **outcome semantics**.

It does not define:

- broker order payloads
- fill-book schemas
- exchange ledger schemas
- final dashboard design
- raw training label implementation details

Those belong elsewhere.

---

## Core Position

V7 keeps the strong V6 outcome principle:

- outcome is larger than a label
- outcome must preserve execution truth, path truth, comparative truth, and readiness truth
- one decision lifecycle should lead to one canonical normalized outcome object

But V7 extends the outcome object in five ways:

1. **explicit simulation-family lineage**
2. **explicit cost-model and execution-assumption lineage**
3. **batch/session-aware grouping**
4. **optional evaluation-run and simulation-run identity**
5. **stronger decision-time context visibility for later audit**

The result is still a **normalized lifecycle object**, not a fill object and not a raw label blob.

`TradeOutcome` may reference real execution truth, paper forward simulation, historical replay, or other simulated truth. These must remain distinguishable in lineage. Monte Carlo evidence is diagnostic/distributional and is not the same as an actual realized outcome.

---

## Relationship To The Contract Family

The V7 lifecycle contract family is:

- `AnalysisRequest`
- `AnalysisResult`
- `DecisionEvent`
- `TradeOutcome`

Their roles differ:

### `AnalysisRequest`
What runtime gave to the engine.

### `AnalysisResult`
What the engine returned.

### `DecisionEvent`
What the system recorded as the normalized evaluated decision.

### `TradeOutcome`
What eventually happened afterward, and how later systems should interpret that consequence.

So `TradeOutcome` is not a model output.
It is a lifecycle object created and updated by the system after the decision exists.

---

## Position In The Flow

Conceptually:

`AnalysisRequest`
→ `AnalysisResult`
→ `DecisionEvent`
→ execution / no-execution / replay-only path
→ `TradeOutcome`

This ordering matters because outcome must describe the consequence of a decision, not retroactively rewrite the decision itself.

`DecisionEvent` records what was known and decided at decision time.
`TradeOutcome` records what became known later.

---

## In Scope

`TradeOutcome` defines:

- outcome identity
- decision linkage
- execution summary
- resolution status
- realized outcome
- path metrics
- comparative outcome
- normalized interpretation
- observability metadata
- simulation/evaluation lineage
- batch/session lineage

---

## Out of Scope

`TradeOutcome` does **not** define:

- full raw request duplication
- full raw result duplication
- full raw event duplication
- fill-level accounting
- broker/exchange-native schemas
- training dataset row formats
- raw label-builder internals
- model-debug internals

---

## Atomic Outcome Rule

One `TradeOutcome` represents **one normalized consequence record for one `DecisionEvent`**.

That consequence may correspond to:

- a live trade
- a paper trade
- a replay-only projected path
- a runtime skip with counterfactual evaluation
- a correct no-trade
- a blocked or degraded decision with later outcome attachment

The key rule is:

- one decision event
- one canonical outcome object

If multiple execution artifacts exist underneath, the outcome object should summarize or reference them rather than break one-outcome-per-decision semantics.

---

## Top-Level Shape

The semantic shape of `TradeOutcome` should be:

```text
TradeOutcome
├── contract
├── identity
├── lineage
├── execution_summary
├── resolution_status
├── realized_outcome
├── path_metrics
├── comparative_outcome
├── quality_and_interpretation
├── observability
└── optional_extended_metadata
```

This keeps outcome meaning explicit while staying compatible with both replay and live paths.

---

## 1. Contract

This section identifies the outcome as a versioned outcome artifact.

### Required fields
- `outcome_schema_version`
- `contract_version`
- `event_schema_version`

### Strongly recommended fields
- `simulation_family_version`
- `comparative_family_version`

### Purpose
Request, result, and event are already versioned semantic objects.
Outcome must be versioned as well.

### Notes
- `outcome_schema_version` tracks the `TradeOutcome` object itself
- `contract_version` ties the outcome back to the request/result/event boundary family
- `event_schema_version` ties it to the decision-event semantics it references
- `simulation_family_version` identifies the outcome-generating simulation family
- `comparative_family_version` identifies how counterfactual comparisons are defined

---

## 2. Identity

This section uniquely identifies the outcome itself.

### Required fields
- `trade_outcome_id`
- `decision_event_id`
- `timestamp_utc`

### Recommended fields
- `trace_id`
- `comparison_group_id`
- `outcome_family_id`

### Purpose
- `trade_outcome_id` is the canonical outcome identity
- `decision_event_id` ties outcome directly to its decision
- `timestamp_utc` records when the outcome record was materialized or updated
- `comparison_group_id` helps compare shadow/replay/live variants of the same underlying state family

### Rules
Outcome identity must stay stable even if raw execution tables or replay artifacts change underneath it.

---

## 3. Lineage

This section preserves the causal lineage from decision to outcome.

### Required fields
- `request_id`
- `engine_name`
- `engine_version`
- `request_kind`
- `outcome_source`

### Strongly recommended fields
- `analysis_batch_id`
- `decision_session_id`
- `model_scope`
- `trade_mode`
- `model_artifact_version`
- `artifact_id`
- `calibration_artifact_version`
- `calibration_artifact_id`
- `policy_artifact_version`
- `cost_model_version`
- `fee_model_version`
- `slippage_model_version`
- `execution_assumption_family`
- `simulation_family_id`
- `comparative_family_id`

### Optional fields
- `candidate_source`
- `replay_mode`
- `paper_or_live_mode`
- `snapshot_builder_version`
- `state_schema_version`
- `feature_schema_version`
- `portfolio_artifact_version`
- `risk_policy_version`
- `evaluation_run_id`
- `simulation_run_id`
- `replay_run_id`
- `monte_carlo_run_id`
- `simulation_profile_version`

### Expected concepts

#### `outcome_source`
- `LIVE_EXECUTION`
- `PAPER_EXECUTION`
- `REPLAY_PROJECTION`
- `OFFLINE_LABELING`
- `SKIP_EVAL`

### Purpose
This section answers:
- what kind of outcome is this?
- did it come from live execution, paper execution, replay, or labeling?
- which engine and request family produced the original decision?
- which `model_scope` / `trade_mode` and scope-compatible artifacts produced it?
- under which simulation and cost semantics was it resolved?
- in which batch/session/run grouping did it occur?

### Rules
- lineage must be explicit
- `model_scope`, artifact, calibration, and policy lineage must remain scope-compatible when present
- simulated outcome lineage and live execution lineage must remain distinguishable
- Monte Carlo run lineage must not be interpreted as actual realized outcome lineage
- hidden generation assumptions are not allowed
- `evaluation_run_id`, `simulation_run_id`, `replay_run_id`, and `monte_carlo_run_id` are optional, but when present they must remain stable and searchable

---

## 4. Execution Summary

This section summarizes whether and how the decision became an execution path.

### Required fields
- `execution_path`
- `execution_decision`
- `position_opened`

### Recommended fields
- `order_group_id`
- `paper_trade_id`
- `position_id`
- `entry_timestamp_utc`
- `exit_timestamp_utc`
- `execution_block_reason`

### Example concepts

#### `execution_path`
- `NOT_EXECUTED`
- `PAPER_EXECUTED`
- `LIVE_EXECUTED`
- `REPLAY_ONLY`
- `SKIPPED_BY_RUNTIME`
- `BLOCKED_BY_RUNTIME`

#### `execution_decision`
- `EXECUTED`
- `SKIPPED`
- `BLOCKED`
- `NOT_APPLICABLE`

### Purpose
Many important outcomes are not simply “a trade was executed and closed.”

Examples:
- the system recommended `NO_TRADE` and executed nothing
- the system was actionable but runtime skipped due to constraints
- replay produced a projected path with no real execution
- paper trade executed but live trade did not

The outcome object must normalize all of these cases.

### `request_kind × execution_path` legality note

Some combinations are natural:
- `live_scan` × `LIVE_EXECUTED`
- `live_scan` × `PAPER_EXECUTED`
- `replay_eval` × `REPLAY_ONLY`
- `validation` × `REPLAY_ONLY`

Some combinations should normally be treated as suspicious or invalid unless explicitly justified by system design:
- `replay_eval` × `LIVE_EXECUTED`
- `shadow` × `LIVE_EXECUTED` in a comparison-only workflow

Validation should reject or flag illegal combinations rather than silently accepting them.

---

## 5. Resolution Status

This section captures whether the outcome is final.

### Required fields
- `outcome_status`
- `is_final`
- `resolution_reason`

### Recommended fields
- `outcome_ready_timestamp_utc`
- `pending_horizon_family`
- `invalidity_reason`

### Example concepts

#### `outcome_status`
- `PENDING`
- `RESOLVED`
- `PARTIALLY_RESOLVED`
- `INVALIDATED`
- `UNAVAILABLE`

#### `resolution_reason`
- `HORIZON_COMPLETE`
- `TRADE_CLOSED`
- `STOP_HIT`
- `TARGET_HIT`
- `TIME_EXIT`
- `SKIP_EVAL_COMPLETE`
- `DATA_INCOMPLETE`
- `EXECUTION_INCOMPLETE`

### Purpose
Outcomes do not resolve instantly.
Some remain pending for hours, days, or longer.
Some can never be resolved cleanly because data or execution history is incomplete.

Later learning and evaluation must distinguish:
- final outcomes
- still pending outcomes
- invalid outcomes

### Rules
- pending outcomes must not masquerade as final
- invalidated outcomes must retain explicit invalidity reason
- later systems must be able to filter by finality safely

---

## 6. Realized Outcome

This section records the core realized or projected result.

### Strongly recommended fields
- `best_realized_action`
- `realized_return`
- `realized_r`
- `gross_pnl`
- `net_pnl`
- `fees_paid`
- `slippage_cost`
- `hold_duration_bars`
- `hold_duration_minutes`
- `exit_reason`

### Optional audit-echo fields
- `decision_confidence_seen`
- `decision_confidence_kind_seen`
- `decision_expected_r_seen`
- `decision_margin_seen`
- `entry_readiness_seen`
- `entry_valid_for_bars_seen`
- `time_sensitivity_seen`

### Example concepts

#### `best_realized_action`
- `LONG_NOW`
- `SHORT_NOW`
- `NO_TRADE`
- `WAIT_1_BAR_LONG`

#### `exit_reason`
- `STOP_HIT`
- `TARGET_HIT`
- `TIME_EXIT`
- `MANUAL_EXIT`
- `RUNTIME_EXIT`
- `PROJECTED_HORIZON_END`
- `NOT_APPLICABLE`

### Purpose
This section captures the main realized or projected result the system cares about after the path resolves.

### Important unit rule
Where possible:
- `realized_r` should use normalized **R-multiple** semantics
- raw monetary PnL can also be included, but it should not replace normalized comparison fields

### Rules
- outcome should stay interpretable across replay, paper, and live contexts
- audit-echo fields may summarize what was seen at decision time, but must not silently rewrite history

---

## 7. Path Metrics

This section captures path-aware quality rather than only terminal outcome.

### Strongly recommended fields
- `mfe`
- `mae`
- `mfe_r`
- `mae_r`
- `time_to_mfe`
- `time_to_mae`
- `time_to_target`
- `time_to_stop`
- `target_hit_before_stop`
- `stop_hit_before_target`
- `path_quality_score`

### Recommended lineage-support fields
- `path_metric_family_version`

### Purpose
Final return alone is not enough.
Path-aware metrics are required to judge whether a state represented a clean, noisy, or dangerous opportunity.

### Rules
- `path_quality_score` is an interpretation aid, not the only source of truth
- path metrics must remain compatible with replay projection and real execution where feasible
- the metric-generation family should be traceable when it matters

---

## 8. Comparative Outcome

This section compares the realized or projected outcome against alternatives.

### Strongly recommended fields
- `counterfactual_best_action`
- `counterfactual_second_best_action`
- `regret_score`
- `regret_r`
- `missed_opportunity_score`
- `saved_loss_score`
- `alternative_action_gap`

### Recommended no-trade fields
- `skip_regret_r`
- `skip_saved_loss_r`
- `skip_was_correct`
- `no_trade_counterfactual_quality`

### Purpose
The system should learn from market-first counterfactuals rather than only from taken trades.

This section makes outcome useful for:
- no-trade evaluation
- timing studies
- calibration studies
- “good skip” vs “missed opportunity” distinction
- regret-aware review

### Examples
- runtime skipped a long that later returned +3R cleanly
- `NO_TRADE` was correct because both directional paths were poor
- a trade won, but regret was still high because another action would have done better

### Rules
- comparative outcome must remain consistent with the comparative family/version used
- no-trade quality must remain first-class

---

## 9. Quality And Interpretation

This section gives the outcome a normalized interpretation.

### Strongly recommended fields
- `outcome_quality`
- `outcome_label`
- `is_good_decision`
- `is_good_execution`
- `is_good_no_trade`
- `is_ambiguous`
- `quality_flags`

### Recommended versioning fields
- `interpretation_version`
- `label_interpretation_version`

### Example concepts

#### `outcome_quality`
- `HIGH`
- `MEDIUM`
- `LOW`
- `AMBIGUOUS`

#### `outcome_label`
- `CLEAN_LONG_OPPORTUNITY`
- `CLEAN_SHORT_OPPORTUNITY`
- `CORRECT_NO_TRADE`
- `WRONG_DIRECTION`
- `HIGH_REGRET_SKIP`
- `DANGEROUS_TRADE`
- `AMBIGUOUS_STATE`
- `LOW_INFORMATION_STATE`

### Purpose
Raw metrics are not enough.
Later systems need a normalized interpretation layer that can drive:
- review
- evaluation
- dataset filtering
- curriculum weighting
- promotion studies

### Rules
- the interpretation layer should be explicit and versioned
- downstream systems should not be forced to re-infer everything ad hoc

### Extension convention for `outcome_label`

If a later system needs new labels beyond the initial set, they should be:
- explicitly documented
- versioned under the interpretation layer
- preferably namespaced or grouped by interpretation family rather than added ad hoc

---

## 10. Observability

This section carries metadata needed for audit, comparison, and debugging.

### Strongly recommended fields
- `warnings`
- `data_quality_flags`
- `label_quality_flags`
- `horizon_family`
- `stop_logic_version`
- `target_logic_version`
- `cost_model_version_seen`
- `simulation_family_version_seen`
- `decision_policy_version_seen`
- `portfolio_policy_version_seen`
- `risk_policy_version_seen`
- `payload_references`
- `review_tags`

### Optional context-seen fields
- `decision_time_portfolio_context`
- `decision_time_exposure_tier`
- `decision_time_cluster_pressure`
- `decision_time_drawdown_state`

### Purpose
Later systems need to inspect:
- why an outcome is trustworthy or not
- under which horizon family it was resolved
- which stop/target/cost semantics were used
- what policy/portfolio/risk context existed when the decision was made

### Rules
- keep required observability fields small and stable
- use `payload_references` for large artifacts rather than bloating the outcome core

---

## 11. Optional Extended Metadata

This section allows controlled future expansion.

### Possible future fields
- richer execution-path decompositions
- benchmark-relative returns
- portfolio-relative outcomes
- specialist-model comparison outputs
- broader market-relative performance

### Rule
These fields must remain optional in the first V7 outcome contract.

---

## Request/Result/Event/Outcome Consistency Rules

The outcome must remain consistent with its upstream lifecycle objects.

### Required consistency
- `identity.decision_event_id == event.identity.decision_event_id`
- `lineage.request_id == event.identity.request_id`
- `lineage.engine_name == event.lineage.engine_name`
- `lineage.engine_version == event.lineage.engine_version`
- `lineage.analysis_batch_id == event.lineage.analysis_batch_id` when both exist
- `lineage.decision_session_id == event.lineage.decision_session_id` when both exist
- `realized_outcome.decision_confidence_seen == event.decision_summary.confidence` when confidence echo is stored
- `realized_outcome.decision_expected_r_seen == event.decision_summary.expected_r` when expected-R echo is stored
- `realized_outcome.entry_readiness_seen == event.decision_summary.entry_readiness_seen` when timing echo is stored
- `realized_outcome.entry_valid_for_bars_seen == event.decision_summary.entry_valid_for_bars_seen` when timing echo is stored

### Allowed transformation
The outcome may:
- summarize consequence
- normalize execution/no-execution paths
- interpret path quality
- compute comparative regret
- add finality status
- attach learning-facing interpretation

The outcome may **not** rewrite what the system knew at decision time.

---

## Required vs Optional

### Required in first V7 outcome contract
- `contract.outcome_schema_version`
- `contract.contract_version`
- `contract.event_schema_version`
- `identity.trade_outcome_id`
- `identity.decision_event_id`
- `identity.timestamp_utc`
- `lineage.request_id`
- `lineage.engine_name`
- `lineage.engine_version`
- `lineage.outcome_source`
- `execution_summary.execution_path`
- `execution_summary.execution_decision`
- `execution_summary.position_opened`
- `resolution_status.outcome_status`
- `resolution_status.is_final`
- `resolution_status.resolution_reason`

### Strongly recommended in first V7 outcome contract
- `lineage.analysis_batch_id`
- `lineage.decision_session_id`
- `lineage.cost_model_version`
- `lineage.simulation_family_id`
- `realized_outcome.best_realized_action`
- `realized_outcome.realized_r`
- `realized_outcome.exit_reason`
- `path_metrics.mfe_r`
- `path_metrics.mae_r`
- `comparative_outcome.counterfactual_best_action`
- `comparative_outcome.regret_r`
- `quality_and_interpretation.outcome_label`
- `quality_and_interpretation.is_good_decision`
- `observability.horizon_family`

### Optional for controlled expansion
- `lineage.evaluation_run_id`
- `lineage.simulation_run_id`
- `lineage.replay_run_id`
- `lineage.monte_carlo_run_id`
- `lineage.simulation_profile_version`
- richer portfolio-relative metrics
- richer specialist comparison metadata
- broader market-relative context

---

## What Must Not Be In The Outcome

To keep the outcome object disciplined, the following must **not** become required outcome semantics:

### 1. Full raw request duplication
Outcome should point back to lineage, not duplicate the whole state.

### 2. Full raw response duplication
Outcome should describe consequence, not re-embed the whole engine result.

### 3. Order-book or fill-book internals
Detailed execution internals belong to execution/accounting records.

### 4. Hidden hindsight rewrite of the decision
Outcome must not pretend the system knew outcome information at decision time.

### 5. Unversioned interpretation blobs
If a normalized label or quality field matters, it should be explicit and versioned.

---

## Creation Timing

A `TradeOutcome` should be materialized **after** a `DecisionEvent` exists and once enough information is available to attach at least an initial resolution state.

This means:
- an initial outcome record may be created in `PENDING` state
- later updates may move it to `RESOLVED`, `PARTIALLY_RESOLVED`, or `INVALIDATED`

### Important principle
The system should not wait until everything is final before creating an outcome object.
It should create the object when the lifecycle begins to matter, then update resolution status explicitly.

This is necessary for:
- long-hold trades
- paper monitoring
- replay pipeline stages
- asynchronous evaluation workflows

---

## Replay Compatibility

Replay must be able to materialize `TradeOutcome` using the same semantic language as live and paper flows.

That means:
- replay outcome is not a different species of outcome
- replay/live differences live in lineage, source, horizon, and optional metadata
- the normalized outcome meaning remains the same

This is crucial for:
- comparing real execution against projected outcome
- offline evaluation
- promotion evidence
- long-term dataset consistency

---

## Validation Rules

`TradeOutcome` should be validated before it is persisted or published.

At minimum, validation should check:

- required sections and fields exist
- `decision_event_id` resolves to a valid decision event
- `execution_summary` and `resolution_status` are internally consistent
- final outcomes do not lack required realized or comparative fields where mandated
- pending outcomes do not masquerade as final
- outcome source and live/paper/replay lineage do not contradict each other
- quality and interpretation labels remain legal for the given resolution state
- `evaluation_run_id`, `simulation_run_id`, `replay_run_id`, and `monte_carlo_run_id`, if present, are well-formed and consistent with lineage context

### Important rule
Validation must protect the system from silently training on:
- unresolved outcomes
- invalid outcomes
- mislabeled skip outcomes
- inconsistent replay/live semantics

---

## Example Semantic Shape

```json
{
  "contract": {
    "outcome_schema_version": "trade-outcome-0.2",
    "contract_version": "v7-0.2",
    "event_schema_version": "decision-event-0.2",
    "simulation_family_version": "simfam-0.2",
    "comparative_family_version": "cmpfam-0.2"
  },
  "identity": {
    "trade_outcome_id": "to_123",
    "decision_event_id": "de_123",
    "trace_id": "trace_999",
    "comparison_group_id": "cmp_abc",
    "timestamp_utc": "2026-04-05T16:30:00Z"
  },
  "lineage": {
    "request_id": "req_123",
    "engine_name": "v7",
    "engine_version": "0.2.0",
    "request_kind": "live_scan",
    "outcome_source": "PAPER_EXECUTION",
    "analysis_batch_id": "batch_001",
    "decision_session_id": "session_001",
    "candidate_source": "dense",
    "replay_mode": null,
    "paper_or_live_mode": "PAPER",
    "model_artifact_version": "model-0.2",
    "calibration_artifact_version": "calib-0.2",
    "policy_artifact_version": "policy-0.2",
    "snapshot_builder_version": "snapshot-0.2",
    "state_schema_version": "state-0.2",
    "feature_schema_version": "features-0.2",
    "cost_model_version": "cost-0.2",
    "fee_model_version": "fee-0.2",
    "slippage_model_version": "slippage-0.2",
    "execution_assumption_family": "default-paper",
    "simulation_family_id": "simfam_main",
    "comparative_family_id": "cmpfam_main",
    "evaluation_run_id": "eval_2026_04_05_01",
    "simulation_run_id": "sim_2026_04_05_01"
  },
  "execution_summary": {
    "execution_path": "PAPER_EXECUTED",
    "execution_decision": "EXECUTED",
    "position_opened": true,
    "order_group_id": "ordgrp_1",
    "paper_trade_id": "paper_123",
    "position_id": null,
    "entry_timestamp_utc": "2026-04-05T12:01:00Z",
    "exit_timestamp_utc": "2026-04-05T16:15:00Z",
    "execution_block_reason": null
  },
  "resolution_status": {
    "outcome_status": "RESOLVED",
    "is_final": true,
    "resolution_reason": "TIME_EXIT",
    "outcome_ready_timestamp_utc": "2026-04-05T16:15:00Z",
    "pending_horizon_family": null,
    "invalidity_reason": null
  },
  "realized_outcome": {
    "best_realized_action": "LONG_NOW",
    "realized_return": 0.021,
    "realized_r": 1.4,
    "gross_pnl": 140.0,
    "net_pnl": 132.0,
    "fees_paid": 6.0,
    "slippage_cost": 2.0,
    "hold_duration_bars": 17,
    "hold_duration_minutes": 255,
    "exit_reason": "TIME_EXIT",
    "decision_confidence_seen": 0.78,
    "decision_confidence_kind_seen": "CALIBRATED",
    "decision_expected_r_seen": 1.35,
    "decision_margin_seen": 0.42,
    "entry_readiness_seen": "CHASING",
    "entry_valid_for_bars_seen": 1,
    "time_sensitivity_seen": "EXPIRING_SOON"
  },
  "path_metrics": {
    "mfe": 0.031,
    "mae": -0.011,
    "mfe_r": 2.1,
    "mae_r": -0.7,
    "time_to_mfe": 11,
    "time_to_mae": 3,
    "time_to_target": null,
    "time_to_stop": null,
    "target_hit_before_stop": false,
    "stop_hit_before_target": false,
    "path_quality_score": 0.72,
    "path_metric_family_version": "pathfam-0.2"
  },
  "comparative_outcome": {
    "counterfactual_best_action": "LONG_NOW",
    "counterfactual_second_best_action": "WAIT_1_BAR_LONG",
    "regret_score": 0.08,
    "regret_r": 0.2,
    "missed_opportunity_score": 0.0,
    "saved_loss_score": 0.0,
    "alternative_action_gap": 0.17,
    "skip_regret_r": 0.0,
    "skip_saved_loss_r": 0.0,
    "skip_was_correct": false,
    "no_trade_counterfactual_quality": "LOW"
  },
  "quality_and_interpretation": {
    "outcome_quality": "MEDIUM",
    "outcome_label": "CLEAN_LONG_OPPORTUNITY",
    "is_good_decision": true,
    "is_good_execution": true,
    "is_good_no_trade": false,
    "is_ambiguous": false,
    "quality_flags": [],
    "interpretation_version": "interp-0.2",
    "label_interpretation_version": "labelinterp-0.2"
  },
  "observability": {
    "warnings": [],
    "data_quality_flags": [],
    "label_quality_flags": [],
    "horizon_family": "short_medium",
    "stop_logic_version": "stop-0.2",
    "target_logic_version": "target-0.2",
    "cost_model_version_seen": "cost-0.2",
    "simulation_family_version_seen": "simfam-0.2",
    "decision_policy_version_seen": "policy-0.2",
    "portfolio_policy_version_seen": "portfolio-0.2",
    "risk_policy_version_seen": "risk-0.2",
    "payload_references": {},
    "review_tags": ["trend", "momentum_breakout"],
    "decision_time_portfolio_context": {"open_positions": 2},
    "decision_time_exposure_tier": "MEDIUM",
    "decision_time_cluster_pressure": "LOW",
    "decision_time_drawdown_state": "NORMAL"
  },
  "optional_extended_metadata": {}
}
```

This example is semantic guidance, not final transport syntax.

---

## Evolution Rules

`TradeOutcome` should evolve with the same general rules as the request, response, and decision-event contracts:

1. keep the stable outcome core explicit
2. prefer additive changes over breaking changes
3. version the outcome schema independently
4. do not silently change the meaning of stable outcome fields
5. keep large optional artifacts behind references

This keeps outcomes usable across:
- live runtime review
- paper-trade analysis
- replay labeling
- evaluation pipelines
- promotion studies

---

## Final Position

`TradeOutcome` is the object that turns a decision lifecycle into learning-compatible evidence.

Without it:
- decision events remain disconnected from consequence
- paper/live/replay outcomes remain fragmented
- no-trade cannot be evaluated honestly
- regret cannot be measured consistently
- path quality gets lost
- promotion and calibration rely on brittle, ad hoc joins

The correct V7 `TradeOutcome` is therefore:

- decision-linked
- execution-aware
- path-aware
- replay-compatible
- explicit about finality
- rich enough for learning
- simulation-family-aware
- cost-model-aware
- batch/session-aware
- small enough to remain stable

That is the outcome backbone V7 needs to close the loop.
