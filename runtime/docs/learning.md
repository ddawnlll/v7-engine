# V4 Learning Layer

This document describes the adaptive learning and self-correction layer added on top of the `v4` analyzer.

Primary code:

- [/Users/hootie/src/trading-bot/v4/services/learning_service.py](/Users/hootie/src/trading-bot/v4/services/learning_service.py)
- [/Users/hootie/src/trading-bot/v4/services/learning_effectiveness_service.py](/Users/hootie/src/trading-bot/v4/services/learning_effectiveness_service.py)
- [/Users/hootie/src/trading-bot/v4/runtime/learning_loop.py](/Users/hootie/src/trading-bot/v4/runtime/learning_loop.py)
- [/Users/hootie/src/trading-bot/v4/api/routes/learning.py](/Users/hootie/src/trading-bot/v4/api/routes/learning.py)
- [/Users/hootie/src/trading-bot/v4/runtime/paper_execution.py](/Users/hootie/src/trading-bot/v4/runtime/paper_execution.py)

## Purpose

The learning layer converts persisted trade outcomes and classified failures into bounded execution adjustments.

It does not replace the base analyzer.

It modifies the last mile of trade decision quality.

Main targets:

- reduce overconfidence
- penalize repeated bad entry timing
- penalize repeatedly failing components
- widen stops when repeated stop-loss failures dominate
- reject statistically bad execution patterns outright

## Inputs

The learning profile is built from:

- closed orders with realized `R`
- persisted failure classifications
- current snapshot execution context
- current factor names

## Profile Shape

`LearningProfile` includes:

- `generated_at`
- `lookback_days`
- `min_confidence`
- `samples`
- `confidence_calibration`
- `entry_penalties`
- `stop_loss_adjustments`
- `component_penalties`
- `hard_rejection_rules`
- `regime_stability`
- `active_adjustments`
- `top_penalties`
- `status`

## Activation Rules

The learning layer is intentionally gated.

It stays inactive until both are true:

- enough closed trades exist
- enough analyzed losses exist

Current thresholds are enforced in code and used as an anti-overfitting guard.

## Confidence Calibration

Closed trades are grouped into confidence buckets.

For each bucket, the engine computes:

- average predicted confidence
- realized win rate
- bounded calibration multiplier

The calibration path now has two layers:

- one global multiplier across the full recent sample
- one per-bucket multiplier blended with the global value when the bucket has enough rows

The multiplier is applied before final confidence gating.

Practical meaning:

- overconfident buckets get scaled down
- reasonably calibrated buckets stay close to `1.0`
- sparse buckets no longer silently default to an uninformative `1.0` if the wider sample is clearly overconfident

## Entry Timing Penalty

The learning layer tracks repeated timing failures, especially:

- `TIMING`
- `Entry Logic`

The live trade is then scored for early-entry risk using:

- extension away from `ema_21`
- extension away from `vwap`
- breakout without retest
- recent impulse extension
- RSI stretch
- microstructure leaning against the trade

That produces an `entry_timing_risk` score.

The learned timing pressure and live entry risk are combined into a bounded `entry_penalty`.

The timing penalty also has an activation floor when timing failures become dominant enough. That prevents the learning layer from discovering a real early-entry pattern and then applying only a cosmetic near-zero penalty.

## Direct Execution Penalty

Execution reasons are not display-only.

The live analyzer now applies an immediate execution penalty when the setup is stretched in ways that historically lead to bad path risk, including:

- stretched away from `vwap`
- breakout without retest
- adverse microstructure flow
- extension away from `ema_21`
- impulse extension
- RSI stretch

These execution penalties are multiplied directly into final confidence, alongside the learned entry and component penalties.

## Component Penalties

The engine aggregates recurring blamed components such as:

- `Stop Loss`
- `Entry Logic`
- `Trend Filter`
- `RSI`
- `MACD`
- `Volume`

Each component gets a bounded penalty driven by:

- failure frequency
- average severity
- average classifier confidence

The analyzer only applies relevant penalties to setups that actually involve matching factors or conditions.

For risk-model failure clusters, repeated `Stop Loss` blame now also creates direct confidence pressure even if a setup does not expose a named stop-loss factor in the visible factor list.

## Adaptive Stop Loss

When failures are concentrated in:

- `RISK_MODEL`
- `Stop Loss`
- `STOP_LOSS_HIT`

the learning layer computes an adaptive stop-loss multiplier.

This multiplier:

- widens the stop buffer
- stays bounded
- is strengthened when volatility is expanding
- is weakened by regime-stability damping when recent samples are unstable

## Regime-Stability Damping

The learning layer evaluates whether the recent sample is stable across regimes.

Outputs:

- `STABLE`
- `MIXED`
- `UNSTABLE`
- `INSUFFICIENT_DATA`

If regimes are unstable, the layer reduces its own influence.

This affects:

- final confidence directly
- entry penalties
- component penalties
- adaptive stop widening
- hard rejection sensitivity

## Hard Rejection

If a failure cluster is statistically dominant enough, the learning layer can return a destructive rejection.

That means:

- no order is emitted
- the analyzer returns `NEUTRAL`

This is intended for repeated bad execution patterns, not weak cosmetic nudges.

## Runtime Refresh

The learning profile is refreshed by a background loop:

- [/Users/hootie/src/trading-bot/v4/runtime/learning_loop.py](/Users/hootie/src/trading-bot/v4/runtime/learning_loop.py)

Current behavior:

- periodic recalculation from persisted data
- refresh does not block main scan or trade execution
- runtime state stores the latest learning refresh status

## Per-Trade Audit Trail

When a trade opens, the execution runtime persists a frozen learning audit on the order payload.

Stored fields include:

- `confidence_before`
- `confidence_after`
- `probability_before`
- `probability_after`
- `adjustments`
- `applied_at_utc`

This makes each trade reviewable later without recomputing the learning state from scratch.

## Effectiveness Reporting

The effectiveness service measures whether active adjustments are helping or hurting.

Current classifications:

- `IMPROVING`
- `NEUTRAL`
- `DEGRADING`
- `INSUFFICIENT_DATA`

It compares:

- adjusted trades
- baseline trades

using:

- average realized `R`
- win rate
- sample counts

## API

Current routes:

- `GET /api/v3/learning/profile`
- `GET /api/admin/learning/profile`
- `GET /api/v3/learning/effectiveness`
- `GET /api/admin/learning/effectiveness`

`/learning/profile` returns:

- active status
- sample size
- top penalties
- calibration data
- full learning profile
- effectiveness summary

`/learning/effectiveness` returns:

- per-adjustment status
- adjusted vs baseline counts
- average `R` deltas
- win-rate deltas
- overall health score

## Current Limits

The learning layer is implemented, but two outcomes still require live observation:

- repeated failure patterns decrease over time
- stop-loss hit rate decreases measurably

Those are operational validation items, not missing code paths.
