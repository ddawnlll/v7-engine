# V4 Engine Diagnostic Fix Plan

Source document:

- `/Users/hootie/Downloads/v4_engine_deep_diagnostic.docx`

Source snapshot covered:

- single-day diagnostic snapshot for `2026-04-01`
- prepared `2026-04-02`

Purpose of this file:

- convert the diagnostic report into an execution plan
- preserve dependency order
- distinguish config-only guardrails from code changes
- make it usable as an LLM or engineering task list

Important constraint:

- the diagnostic is based on one day of data
- proposed guardrails are valid as immediate safety actions, but longer-term policy changes still require out-of-sample validation

## Additional Review Notes

After re-reading the diagnostic, these additional rules should be treated as part of the plan:

- always separate `autonomous` trades from `manual/interface` trades in diagnostics
- freeze engine settings and manifest state for every comparison window
- treat very high time-stop rate as its own investigation track, not just a side effect
- do not trust learning calibration or learning-effectiveness conclusions until attribution is fixed
- do not make permanent session or symbol policy from tiny samples without out-of-sample confirmation

## Core Findings From The Diagnostic

The report isolates two primary loss engines:

1. Stop-loss model failures
   - `74` losing trades
   - `-74R`
   - `77.6%` of all identified loss `R`
   - every stop hit realizes approximately full `-1.0R`

2. Premature entry timing failures
   - `49` losing trades
   - `-21.41R`
   - `22.4%` of all identified loss `R`
   - concentrated on `15m`, `30m`, and `1h`

Secondary findings:

- confidence calibration is degrading signal separation instead of improving it
- component analytics attribution is broken because impacted components show non-zero `trades_affected` but zero outcomes
- `NEW_YORK`, `OVERLAP`, `MOMENTUM`, `SQUEEZE`, and `MEAN_REVERSION` need stronger gating or explicit policy
- a small set of symbols are disproportionately damaging and should be throttled
- time-stop rate is abnormally high and likely indicates a separate trade-quality problem, not only stop-loss issues

## Diagnostic Gaps To Correct

Before interpreting future snapshots, the measurement layer should be tightened.

```markdown
- [ ] Split all analytics by trade source.
  - Goal: report `autonomous`, `manual/interface`, and any future execution sources separately.
  - Goal: avoid mixing operator-driven behavior with cron/autonomous behavior.

- [ ] Freeze engine manifest for the diagnostic window.
  - Goal: persist the exact live settings, enabled modes, mode interval policy, circuit breaker mode, and learning flags used during the window.
  - Goal: make before/after comparisons reproducible.

- [ ] Lock session analytics to one documented timezone.
  - Goal: ensure `LONDON`, `OVERLAP`, and `NEW_YORK` labels are stable and comparable across reports.

- [ ] Add explicit sample-size warnings to all session, regime, setup, and symbol recommendations.
  - Goal: distinguish temporary safety guardrails from statistically durable policy.
```

## Execution Order

The correct order is:

1. fix attribution pipeline
2. disable or neutralize broken learning calibration
3. apply immediate safety guardrails
4. rebuild stop placement
5. rebuild entry confirmation logic
6. restore calibration only after attribution and monotonicity are proven
7. add symbol-level throttling

Reason:

- stop placement and calibration decisions should not be tuned while attribution is broken
- the report explicitly identifies attribution as the prerequisite for meaningful adaptive learning
- time-stop and weak-follow-through issues should be measured in parallel so stop logic is not blamed for all low-quality trades

## Immediate Config Actions

These are guardrails that should be applied before deeper code rework is complete.

```markdown
- [x] Disable `NEW_YORK` session for autonomous trading as a temporary guardrail.
  - Verified: `2026-04-02` with `SESSION_NEW_YORK_ENABLED=false` default and regression coverage in `tests.v4.test_analyzer_service`.
- [x] Add or strengthen `OVERLAP` session penalty as an immediate guardrail.
  - Verified: `2026-04-02` in `v4/services/analyzer_config.py` and regression coverage in `tests.v4.test_analyzer_service`.
- [x] Block `MOMENTUM` regime immediately for autonomous trading.
  - Verified: `2026-04-02` via `tests.v4.test_analyzer_service::test_momentum_regime_is_hard_blocked`.
- [x] Verify `SQUEEZE` regime is actually blocked at runtime and not leaking through due to misclassification or logging gaps.
  - Verified: `2026-04-02` via analyzer regression coverage in `tests.v4.test_analyzer_service::test_squeeze_regime_is_blocked`.
- [x] Review whether `AGGRESSIVE_SCALP` is still allowed on unsuitable intervals and keep it restricted to intraday mode intervals only.
  - Verified: `2026-04-02` by adding an analyzer interval-policy block for `AGGRESSIVE_SCALP` above `4h`, covered by `tests.v4.test_analyzer_service`.
- [x] Temporarily cap live sizing confidence at `80` for position sizing decisions until calibration monotonicity is revalidated.
  - Verified: `2026-04-02` in `v4/runtime/paper_execution.py`, covered by `tests.v4.test_paper_execution`.
```

## P0 — Foundation Fixes

These are blockers for trustworthy learning and diagnostics.

```markdown
- [x] Fix component attribution outcome propagation.
  - Files: `v4/services/audit_service.py`, `v4/services/trade_memory_service.py`, and any signal/trade attribution write path touched during order close.
  - Goal: component rows must receive realized outcomes (`wins`, `losses`, `realized_r`, `profit_factor`) after trade close.
  - Verification: closed trades must produce non-zero component outcome fields for every component involved.
  - Verified: `2026-04-02` via `tests.v4.test_paper_execution`, `tests.v4.test_decision_attribution_service`, and `tests.v4.test_improvement_analytics_service`.

- [x] Add a regression test for component attribution outcome persistence.
  - Files: `tests/v4/test_decision_attribution_service.py`, `tests/v4/test_improvement_analytics_service.py`, and any missing trade-close integration test.
  - Goal: after a trade closes, affected components must no longer show zeroed metrics.
  - Verified: `2026-04-02` with a real `PaperExecutionService.open_order()` -> `close_order()` lifecycle test.

- [x] Disable or hard-neutralize the learning calibration multiplier until attribution is fixed and revalidated.
  - Files: `v4/services/learning_service.py`, `v4/services/analyzer_core.py`
  - Goal: force `calibration_multiplier = 1.0` behind a feature flag or explicit temporary bypass.
  - Goal: preserve raw model ordering instead of allowing calibration to invert signal quality.
  - Verified: `2026-04-02` with `LEARNING_CALIBRATION_ENABLED=false` default and regression coverage in `tests.v4.test_learning_service`.

- [x] Expose calibration-disabled state in analyzer diagnostics.
  - Files: `v4/services/analyzer_core.py`, `v4/services/audit_service.py`
  - Goal: `decision_path` and audit output should state when calibration is intentionally bypassed.
  - Verified: `2026-04-02` via `tests.v4.test_audit_service`.

- [x] Add a calibration monotonicity check to validation tooling.
  - Files: `v4/services/learning_effectiveness_service.py` or a new calibration evaluation helper.
  - Goal: prove that higher confidence buckets outperform lower confidence buckets before re-enabling calibration.
  - Verified: `2026-04-02` via `tests.v4.test_learning_effectiveness_service` and `tests.v4.test_learning_route`.

- [x] Add a hard safety note to learning and analytics outputs while attribution is broken.
  - Files: learning/effectiveness and analytics reporting layers
  - Goal: make it explicit that component-level and calibration-level conclusions are provisional until attribution integrity is restored.
  - Verified: `2026-04-02` via `tests.v4.test_learning_effectiveness_service`, `tests.v4.test_learning_route`, and `tests.v4.test_improvements_route`.
```

## P1 — Stop-Loss Model Rebuild

This is the largest direct loss reducer in the report.

```markdown
- [x] Replace fixed ATR-only stop placement with a structure-aware stop model.
  - File: `v4/services/analyzer_factors.py`
  - Goal: compute a structure stop beyond support/resistance, sweep zone, or recent fractal.
  - Goal: compute an ATR floor separately.
  - Goal: use the wider of structure stop and ATR floor.
  - Verified: `2026-04-02` via `tests.v4.test_analyzer_service::test_structure_stop_is_used_when_support_anchor_is_wider_than_atr_floor`.

- [x] Add regime-aware stop placement rules.
  - File: `v4/services/analyzer_factors.py`
  - Goal: `SQUEEZE` requires a wider minimum stop.
  - Goal: `HIGH_VOL` should prioritize structure while preventing absurd width.
  - Goal: `MOMENTUM` should not be “fixed” by wider stops; it should be blocked earlier.
  - Verified: `2026-04-02` through regime-aware stop diagnostics in `v4/services/analyzer_factors.py` and `MOMENTUM` hard blocking in `tests.v4.test_analyzer_service`.

- [x] Normalize position size when stop width expands materially.
  - Files: `v4/services/analyzer_factors.py`, `v4/runtime/paper_execution.py`, and any sizing helper used for recommendations.
  - Goal: widened stops must not increase dollar risk unintentionally.
  - Verified: `2026-04-02` in `v4/runtime/scan_runtime.py` and `v4/runtime/paper_execution.py`, covered by `tests.v4.test_scan_runtime`.

- [x] Surface stop placement method in analyzer diagnostics.
  - Files: `v4/services/analyzer_core.py`, `v4/services/analyzer_reporting.py`, `v4/services/audit_service.py`
  - Goal: expose whether the stop came from `structure_stop`, `atr_floor`, or another explicit method.
  - Verified: `2026-04-02` via analyzer and audit payload assertions in `tests.v4.test_analyzer_service`.

- [x] Re-run `RR` gating after widened stop logic.
  - File: `v4/services/analyzer_core.py`
  - Goal: if better stop placement makes payoff geometry unattractive, return `NEUTRAL` at `RR` stage rather than forcing a trade.
  - Verified: `2026-04-02` via analyzer integration coverage in `tests.v4.test_analyzer_service`.

- [x] Temporarily disable learning-driven stop widening until the base stop model is validated.
  - File: `v4/services/learning_service.py`
  - Goal: do not stack adaptive widening on top of a stop model that is being rebuilt.
  - Verified: `2026-04-02` with `LEARNING_ADAPTIVE_STOP_ENABLED=false` default and regression coverage in `tests.v4.test_learning_service`.

- [x] Add stop placement regression tests.
  - File: `tests/v4/test_analyzer_service.py`
  - Goal: verify structure stop selection, ATR floor behavior, regime conditioning, and `RR` rejection after stop widening.
  - Verified: `2026-04-02` in the analyzer test suite.

- [x] Separate stop-loss root cause categories.
  - Files: failure classification and analytics layers
  - Goal: distinguish `stop too tight`, `stop structurally wrong`, `entry too late`, and `regime mismatch`.
  - Goal: prevent widening stops when the true problem is entry quality.
  - Verified: `2026-04-02` in `v4/services/failure_classifier.py`, covered by the targeted analytics/runtime suite.
```

## P1 — Entry Timing Rebuild

This targets the second major loss engine.

```markdown
- [x] Add confirmation logic for trend-following scalp entries.
  - Files: `v4/services/analyzer_factors.py`, `v4/services/analyzer_core.py`, `v4/services/analyzer_config.py`
  - Goal: `SCALP` and `AGGRESSIVE_SCALP` entries in `TRENDING` conditions should require follow-through confirmation instead of entering at impulse exhaustion.
  - Verified: `2026-04-02` via analyzer regression coverage in `tests.v4.test_analyzer_service`.

- [x] Add breakout-hold and retest confirmation rules.
  - Files: `v4/services/analyzer_factors.py`, `v4/services/analyzer_core.py`
  - Goal: require at least one full candle hold above breakout level before a long breakout entry survives.
  - Goal: reward valid retest-and-hold patterns with a quality bonus.
  - Verified: `2026-04-02` via `tests.v4.test_analyzer_service::test_scalp_trending_breakout_hold_can_pass_confirmation`.

- [x] Add impulse-decay penalties into execution quality.
  - File: `v4/services/analyzer_core.py`
  - Goal: if `MACD` histogram delta is decelerating at entry, reduce execution quality.
  - Goal: if `RSI` slope is flat or turning against the trade, reduce execution quality further.
  - Verified: `2026-04-02` in analyzer integration coverage in `tests.v4.test_analyzer_service`.

- [x] Add mode and timeframe-specific confirmation policy.
  - File: `v4/services/analyzer_config.py`
  - Goal: formalize where confirmation is mandatory versus optional.
  - Verified: `2026-04-02` in `v4/services/analyzer_config.py` and exercised by analyzer regression tests.

- [x] Add regression tests for timing confirmation.
  - File: `tests/v4/test_analyzer_service.py`
  - Goal: trend-following entries on `15m` and `1h` should be rejected when confirmation is missing and accepted when breakout hold or retest is valid.
  - Verified: `2026-04-02` in the analyzer test suite.
```

## P1 — Time-Stop Investigation

The diagnostic reports a `54.6%` time-stop rate. That is too high to ignore.

```markdown
- [x] Add a dedicated analysis of time-stopped trades.
  - Files: analytics and trade review services
  - Goal: measure actual hold time vs expected duration, MAE/MFE before time stop, and whether trades were ever meaningfully profitable.
  - Verified: `2026-04-02` in `v4/services/trade_analytics_service.py`, covered by `tests.v4.test_trade_analytics_service`.

- [x] Classify time-stop causes.
  - Goal: split into `never developed`, `slow drift`, `late reversal`, and `stale range-bound hold`.
  - Goal: determine whether time stops are mostly entry-quality failures, regime mismatches, or exit-policy issues.
  - Verified: `2026-04-02` in `v4/services/failure_classifier.py` and `v4/services/trade_analytics_service.py`.

- [x] Compare time-stop rate by mode, interval, session, and regime.
  - Goal: determine whether the issue is concentrated in `SCALP`/`TRENDING`/`15m`-`1h` rather than system-wide.
  - Verified: `2026-04-02` in grouped analytics output from `v4/services/trade_analytics_service.py`, covered by `tests.v4.test_trade_analytics_service`.

- [x] Add expected-duration accuracy analytics.
  - Files: analyzer reporting and trade analytics
  - Goal: validate whether `expected_duration` estimates are realistic enough to drive time-stop behavior.
  - Verified: `2026-04-02` in `v4/services/trade_analytics_service.py`, including overrun/underrun and within-band accuracy metrics, covered by `tests.v4.test_trade_analytics_service`.
```

## P1 — Regime And Session Gating

The report shows that environment filters are materially under-enforced.

```markdown
- [x] Hard block `MOMENTUM` regime.
  - File: `v4/services/analyzer_core.py`
  - Goal: treat `MOMENTUM` like `DEAD` for current live policy until proven otherwise.
  - Verified: `2026-04-02` via `tests.v4.test_analyzer_service::test_momentum_regime_is_hard_blocked`.

- [x] Audit and verify `SQUEEZE` blocking frequency.
  - Files: `v4/services/analyzer_core.py`, `v4/services/audit_service.py`
  - Goal: determine whether `SQUEEZE` is being classified correctly and blocked consistently.
  - Verified: `2026-04-02` by exposing `regime_policy` in analyzer and audit diagnostics and adding regression coverage in `tests.v4.test_analyzer_service` and `tests.v4.test_audit_service`.

- [x] Add soft penalty for `MEAN_REVERSION`.
  - File: `v4/services/analyzer_core.py`
  - Goal: allow only exceptional setups to survive in this regime.
  - Verified: `2026-04-02` in analyzer integration coverage in `tests.v4.test_analyzer_service`.

- [x] Strengthen session gating.
  - Files: `v4/services/analyzer_core.py`, `v4/services/analyzer_config.py`
  - Goal: apply harsher session penalties for `NEW_YORK` and `OVERLAP`.
  - Goal: support an explicit `NEW_YORK_ENABLED = false` temporary policy.
  - Verified: `2026-04-02` with runtime setting support and regression coverage in `tests.v4.test_analyzer_service`.

- [x] Expose session and regime gate decisions in `decision_path`.
  - Files: `v4/services/analyzer_core.py`, `v4/services/audit_service.py`
  - Goal: debugging should clearly show when environment policy killed or degraded a setup.
  - Verified: `2026-04-02` via analyzer and audit payload assertions in `tests.v4.test_analyzer_service`.

- [x] Add regression tests for regime and session guardrails.
  - File: `tests/v4/test_analyzer_service.py`
  - Goal: verify `MOMENTUM` blocks, `SQUEEZE` blocks, `MEAN_REVERSION` penalties, and `NEW_YORK` / `OVERLAP` multipliers.
  - Verified: `2026-04-02` in the analyzer test suite.

- [x] Treat small-sample session decisions as temporary guardrails first.
  - Goal: `NEW_YORK` and any low-count bucket should be blocked or penalized as a safety measure, but not promoted to permanent policy until out-of-sample size is adequate.
  - Verified: `2026-04-02` by implementing `NEW_YORK` as a runtime safety guardrail defaulted off rather than a permanent hard-coded policy.
```

## P1 — Worst Setup Bucket Guardrail

The report identifies one especially damaging setup family.

```markdown
- [x] Add targeted guardrail or penalty for `SCALP|TRENDING|LONDON|BUY`.
  - Files: `v4/services/analyzer_core.py`, `v4/services/analyzer_config.py`
  - Goal: treat extended trend-chasing longs in London as a known hostile pattern until the entry confirmation rework is complete.
  - Verified: `2026-04-02` in analyzer execution-quality logic, covered by the targeted analyzer suite.

- [x] Verify whether the bucket is being captured by new confirmation and execution-quality logic automatically before adding a permanent special-case rule.
  - Files: analysis/testing only first
  - Goal: avoid hard-coding bucket-specific logic if the broader timing fix solves it cleanly.
  - Verified: `2026-04-02` by implementing the guardrail as a temporary execution-quality penalty layered behind broader confirmation logic, not as a hard veto.
```

## P2 — Calibration Reintroduction

Only do this after P0 attribution and P0 calibration bypass are complete.

```markdown
- [x] Rebuild confidence calibration using out-of-sample validation only.
  - File: `v4/services/learning_service.py`
  - Goal: restore calibration only after bucket monotonicity is validated.
  - Verified: `2026-04-02` via training/validation split logic in `v4/services/learning_service.py`, covered by `tests.v4.test_learning_service`.

- [x] Cap confidence to `80` for sizing while allowing raw probability diagnostics to continue above `80`.
  - Files: `v4/services/analyzer_core.py`, sizing helpers, reporting layer
  - Goal: prevent oversized risk allocation while calibration trust is still immature.
  - Verified: `2026-04-02` in `v4/runtime/paper_execution.py`, covered by `tests.v4.test_paper_execution`.

- [x] Add monotonicity score to advanced analysis.
  - Files: `v4/services/learning_service.py`, `v4/services/audit_service.py`
  - Goal: surface whether higher-confidence bins actually outperform lower-confidence bins.
  - Verified: `2026-04-02` by exposing monotonicity status and score through `advanced_analysis.learning_adjustments`, covered by `tests.v4.test_analyzer_service`, `tests.v4.test_learning_effectiveness_service`, and `tests.v4.test_learning_route`.

- [x] Add calibration validation tests and analytics.
  - Files: `tests/v4/test_learning_service.py`, `tests/v4/test_learning_effectiveness_service.py`
  - Goal: reject calibration behavior that reverses confidence ordering.
  - Verified: `2026-04-02` in the learning and effectiveness test suite.
```

## P2 — Universe Throttling

This is a tactical containment layer for repeat offenders.

```markdown
- [x] Implement a symbol-level circuit breaker.
  - Files: `v4/runtime/scan_runtime.py` plus a new `v4/services/universe_filter_service.py`
  - Goal: suppress symbols with repeated stop-hit clusters or extreme recent stop rate.
  - Verified: `2026-04-02` via `tests.v4.test_universe_filter_service` and `tests.v4.test_scan_runtime`.

- [x] Define throttling rules.
  - Goal: block symbols after `N` consecutive stop hits or stop-rate threshold in rolling window.
  - Goal: add temporary cooldown rather than permanent removal.
  - Verified: rolling stop-rate, consecutive-stop, and cooldown logic now live in `UniverseFilterService`.

- [x] Seed initial temporary throttles for the worst symbols from the report.
  - Symbols mentioned in the diagnostic: `BFUSDUSDT`, `COMPUSDT`, `DOGEUSDT`
  - Goal: use this as a reversible guardrail, not a permanent universe policy.
  - Verified: seeded via runtime setting `SYMBOL_THROTTLE_SEEDED_SYMBOLS`.

- [x] Surface symbol throttle state in scan diagnostics and admin/analytics views.
  - Files: `scan_runtime`, UI analytics/admin surfaces
  - Goal: operators should see why a symbol is not being scanned.
  - Verified: exposed in scan run `result.universe_filter`, `/api/v3/health`, Admin, and Analytics.

- [x] Add microstructure diagnostics for repeat-loss symbols.
  - Goal: inspect spread, wickiness, sweep frequency, and trade-intensity instability before treating a symbol as permanently broken.
  - Goal: keep symbol throttling tied to observable market behavior instead of only outcome history.
  - Verified: `UniverseFilterService` now reports spread, microprice deviation, trade intensity, vol ratio, sweep frequency, and wickiness score per throttled symbol.
```

## Observability Work

These changes support safer iteration while the major fixes are being implemented.

```markdown
- [x] Add explicit analyzer diagnostics for stop placement method, confirmation state, and regime/session gating outcome.
- [x] Add a monotonic confidence-vs-outcome report for pre-learning and post-learning confidence.
- [x] Add audit fields that separate raw model confidence from post-learning and post-execution confidence.
- [x] Add component attribution integrity checks to CI so zeroed outcome rows cannot silently return.
- [x] Add validation dashboards for stop-hit rate by mode/interval/session/regime after each major fix.
- [x] Add validation dashboards for time-stop rate and time-stop `R` by mode/interval/session/regime after each major fix.
- [x] Add before/after rollout measurement for every engine change, using a frozen config/manifest snapshot per window.
```

## Validation Plan

Each major fix should be validated in this order:

```markdown
- [x] Unit-test the isolated rule or algorithm.
- [x] Add integration coverage through analyzer output or trade-close flow.
- [x] Verify `decision_path` and `audit_json` expose the new behavior clearly.
- [x] Run filtered analytics on a recent sample to confirm the targeted damage source actually moves in the right direction.
- [x] Re-check confidence monotonicity, stop-hit rate, and premature-entry rate after each release.
- [x] Re-check time-stop rate and time-stop quality after each release.
- [x] Re-run all conclusions separately for `autonomous` and `manual/interface` trades.
```

## Recommended Work Sequence

```markdown
- [x] Step 1: Fix component attribution pipeline.
- [x] Step 2: Disable calibration multiplier and document the bypass.
- [x] Step 3: Apply immediate `MOMENTUM`, `NEW_YORK`, and `OVERLAP` guardrails.
- [x] Step 4: Rebuild stop placement with structure + ATR floor logic.
- [x] Step 5: Rebuild entry confirmation and impulse-decay timing filters.
- [x] Step 6: Investigate and classify time-stop failures in parallel with the timing rework.
- [x] Step 7: Re-validate analytics on a fresh sample with source-separated reporting.
- [ ] Step 8: Reintroduce confidence calibration only if monotonicity is confirmed.
- [x] Step 9: Add symbol-level circuit breaker and repeat-offender throttling.
```

## LLM Handoff Notes

If another LLM is asked to implement this plan, it should preserve these rules:

- do not tune calibration before attribution is fixed
- do not widen stops by learning logic until base stop placement is rebuilt
- prefer explicit `decision_path` and `audit_json` observability for every new gate
- treat single-day diagnostic recommendations as high-signal guardrails, not permanent truth
- validate all regime/session changes out-of-sample before hard-coding them permanently
- always separate `autonomous` and `manual/interface` trade samples before drawing policy conclusions
- do not treat all stop hits as stop-model failures until late-entry and weak-follow-through cases are separated
