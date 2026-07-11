# V4 Engine Change Analysis

Date:

- `2026-04-02`

Scope:

- P0 attribution and calibration safety fixes
- P1 stop-loss, timing, regime/session, and time-stop work
- P2 universe throttling
- observability and rollout-validation additions

Purpose:

- document what changed
- record what was verified
- summarize what improved
- identify what is still unresolved

## Change Summary

### Foundation and learning safety

- component attribution now persists realized trade outcomes on close
- learning calibration is runtime-gated and bypassed by default
- calibration monotonicity is measured explicitly before reintroduction
- learning and improvement analytics now emit safety notes when attribution is incomplete

Primary files:

- [../services/decision_attribution_service.py](../services/decision_attribution_service.py)
- [../services/learning_service.py](../services/learning_service.py)
- [../services/improvement_analytics_service.py](../services/improvement_analytics_service.py)

### Stop model rebuild

- stop placement is no longer ATR-only
- analyzer now computes:
  - structure stop
  - ATR floor stop
  - capped structure-aware stop selection
- widened stop geometry feeds back into:
  - `RR` gating
  - sizing risk adjustment
  - diagnostics and audit

Primary files:

- [../services/analyzer_factors.py](../services/analyzer_factors.py)
- [../services/analyzer_core.py](../services/analyzer_core.py)
- [../runtime/paper_execution.py](../runtime/paper_execution.py)

### Entry timing and environment gating

- breakout-hold and retest confirmation logic added
- impulse-decay penalties added to execution quality
- `MOMENTUM` hard-blocked
- `SQUEEZE` blocking and policy surfaced explicitly
- `AGGRESSIVE_SCALP` restricted to intraday intervals up to `4h`
- session/regime policy is now visible in diagnostics
- session alias normalization now treats `OVERLAP` as `LONDON_NEW_YORK_OVERLAP`
- wide-stop position sizing now scales down explicitly only beyond `1.5 ATR`

Primary files:

- [../services/analyzer_core.py](../services/analyzer_core.py)
- [../services/analyzer_config.py](../services/analyzer_config.py)
- [../services/analyzer_factors.py](../services/analyzer_factors.py)

### Time-stop analysis

- analytics now breaks out time-stop behavior by:
  - mode
  - interval
  - session
  - regime
  - source
- expected-duration accuracy is measured directly
- time-stop cause categories are tracked
- time-stop quality categories are tracked
- analyzer timing is now conditioned by regime and session
- execution can now close stale trades early via `EARLY_STALE_EXIT`

Primary files:

- [../services/analyzer_reporting.py](../services/analyzer_reporting.py)
- [../runtime/paper_execution.py](../runtime/paper_execution.py)
- [../services/trade_analytics_service.py](../services/trade_analytics_service.py)
- [../services/failure_classifier.py](../services/failure_classifier.py)

### Universe throttling

- added a symbol-level tactical circuit breaker
- symbols can now be throttled by:
  - seeded guardrail
  - consecutive stop-hit cluster
  - rolling stop-hit rate
- throttling is cooldown-based, not permanent
- scan runtime records throttle-driven skips explicitly
- health, admin, and analytics now surface current throttle state

Primary files:

- [../services/universe_filter_service.py](../services/universe_filter_service.py)
- [../runtime/scan_runtime.py](../runtime/scan_runtime.py)
- [../api/routes/health.py](../api/routes/health.py)
- [Legacy: interface/src/routes/AdminRoute.tsx (original trading-bot repo)]
- [Legacy: interface/src/routes/AnalyticsRoute.tsx (original trading-bot repo)]

### Observability additions

- analyzer and audit now expose:
  - stop method
  - confirmation state
  - regime policy
  - raw model confidence
  - post-learning confidence
  - post-execution confidence placeholder
  - raw model probability
  - post-learning probability
  - execution quality multiplier
- analytics now exposes:
  - confidence monotonicity
  - stop-hit validation dashboards
  - time-stop validation dashboards
  - rollout measurement with manifest hashes

## Validation Evidence

### Targeted runtime and observability suite

Command:

```bash
.venv_v4/bin/python -m unittest \
  tests.v4.test_universe_filter_service \
  tests.v4.test_scan_runtime \
  tests.v4.test_trade_analytics_service \
  tests.v4.test_improvement_analytics_service \
  tests.v4.test_health_route \
  tests.v4.test_decision_attribution_service
```

Result:

- `23` tests passed

### Broader engine suite

Command:

```bash
.venv_v4/bin/python -m unittest \
  tests.v4.test_analyzer_service \
  tests.v4.test_learning_service \
  tests.v4.test_audit_service \
  tests.v4.test_paper_execution \
  tests.v4.test_failure_classifier \
  tests.v4.test_trade_analytics_service \
  tests.v4.test_improvement_analytics_service \
  tests.v4.test_scan_runtime \
  tests.v4.test_health_route \
  tests.v4.test_decision_attribution_service \
  tests.v4.test_learning_effectiveness_service \
  tests.v4.test_learning_route \
  tests.v4.test_analytics_route \
  tests.v4.test_improvements_route
```

Result:

- `70` tests passed

### Frontend validation

Command:

```bash
cd interface && bun run build
```

Result:

- build passed

### Live analytics sample

Checked against the configured local Postgres runtime database.

Window:

- last `30` days
- `min_samples = 5`

Observed:

- closed trades: `258`
- win rate: `47.29%`
- average realized `R`: `+0.1359R`
- stop-hit rate: `29.84%`
- time-stop rate: `54.65%`
- pre-learning confidence monotonicity: `PASS`
- post-learning confidence monotonicity: `MIXED`
- throttled symbols at sample time: `0`
- expected-duration within `25%` band on time stops: `3.55%`
- time-stop cause mix:
  - `never_developed`: `67`
  - `stale_range_bound_hold`: `50`
  - `late_reversal`: `24`
- time-stop quality mix:
  - `flat_positive`: `67`
  - `stale`: `50`
  - `adverse`: `24`

Source separation:

- `AUTO`
  - closed trades: `258`
  - win rate: `47.29%`
  - net `R`: `+35.0617R`
  - stop-hit rate: `29.84%`
  - time-stop rate: `54.65%`

Interpretation:

- current live sample in the last `30` days contains only autonomous closed trades
- there were no separate `manual/interface` closed trades in the observed window
- source separation logic is therefore operationally satisfied, but the live sample does not provide a manual comparison set yet
- the time-stop problem is now more specific than before:
  - most time stops are not violent failures
  - they are dominated by flat non-development and stale holding behavior
  - only a minority are late reversals

### Direct analyzer payload check

Direct analyzer output confirmed:

- `decision_path` includes:
  - `probability_raw`
  - `probability_final`
  - `confidence_raw`
  - `confidence_final`
  - `entry_quality_breakdown`
  - `risk_reward`
  - `expected_value`
  - `session_label`
  - `neutral_stage`
- `advanced_analysis.stop_model` includes:
  - `stop_method`
  - `atr_floor_stop`
  - `structure_stop`
  - `stop_distance`
  - `stop_distance_atr`
- `advanced_analysis.confirmation` includes:
  - `policy`
  - `passed`
  - `bonus`
  - `reasons`
  - `signals`
- `advanced_analysis.regime_policy` includes:
  - `regime`
  - `detail`
  - `dead_policy`
  - `squeeze_policy`
  - `mean_reversion_penalty`
  - `momentum_policy`
- `audit_json` now carries:
  - `confidence_model_raw`
  - `confidence_post_learning`
  - `confidence_post_execution`

## What Improved

- stop-hit rate is materially below the original diagnostic’s stop-loss-dominated failure picture
- confidence ordering before learning remains monotonic on the current sample
- component attribution outcome propagation is no longer zeroed
- scan runtime can now suppress repeat-offender symbols explicitly and explain why
- rollout and analytics surfaces now have enough observability to measure changes instead of guessing
- timing estimates are no longer purely distance-and-ATR based; session/regime conditioning is explicit
- stale positions now have a dedicated exit path instead of always waiting for the full time stop

## What Is Still Not Good

- time-stop rate is still too high at `54.65%`
- expected-duration quality is still poor, with only `3.55%` of time stops landing within the `25%` accuracy band
- post-learning confidence monotonicity is only `MIXED`
- the live 30-day sample does not yet contain a separate manual closed-trade comparison set
- `EARLY_STALE_EXIT` is implemented, but there is not enough new live data yet to measure whether it reduces stale-hold occupancy

## Main Current Conclusion

The stop model, gating, attribution, observability, and timing model are materially stronger than before, and the engine is no longer in the same blind state that produced the original diagnostic. The biggest remaining live weakness is still stale/non-developing trade occupancy, but the engine now has a direct early-exit mechanism and regime/session-conditioned duration estimates to attack that problem.

That makes the next analysis target clear:

- reduce time-stop rate
- tighten duration realism and stale-hold handling
- improve post-learning confidence monotonicity back to `PASS`
- continue monitoring whether stop-hit improvements hold out-of-sample
