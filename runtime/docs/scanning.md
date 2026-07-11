# V4 Scanning

This document describes how scanning works in the current `v4` system.

It is intended as an LLM handoff document for analyzing scan-time improvements.

Primary source files:

- [../runtime/scan_runtime.py](../runtime/scan_runtime.py)
- [../runtime/market_data.py](../runtime/market_data.py)
- [../runtime/autonomous_loop.py](../runtime/autonomous_loop.py)
- [../runtime/scan_control.py](../runtime/scan_control.py)
- [../api/routes/scans.py](../api/routes/scans.py)
- [../services/universe_filter_service.py](../services/universe_filter_service.py)
- [../services/analyzer_service.py](../services/analyzer_service.py)
- [../runtime/paper_execution.py](../runtime/paper_execution.py)

## Executive Summary

The scan engine is a serial run coordinator with a concurrent market-fetch stage.

High-level shape:

1. A scan request defines `symbols × intervals × modes`.
2. Early pruning removes duplicate scope, mode-ineligible interval pairs, and throttled symbols before expensive work begins.
3. Active `symbol + interval` fetches run through a bounded thread pool.
4. For each fetched snapshot, analysis runs per allowed mode.
5. Non-neutral eligible signals can create orders through paper execution.
6. The run writes progress snapshots, debug state, and a final persisted result.

Important architecture fact:

- Fetch concurrency exists at the `symbol + interval` layer.
- Analysis is still executed in-process after each fetch result returns.
- Autonomous scans do not overlap. One long run delays the next run.

## Entry Points

There are two ways scans start.

### Manual / interface scan

Route:

- `POST /api/v3/scans`

Flow:

- receives `symbols`, `intervals`, `modes`, optional `scan_workers`, and `requested_by`
- resolves per-mode interval policy through `resolve_mode_intervals(...)`
- calls `ScanRuntime.run_scan(...)`

### Autonomous scheduled scan

Path:

- `AutonomousLoop.run_once()`

Flow:

- loads settings from runtime settings
- checks `AUTONOMOUS_ENABLED`
- checks circuit breaker state
- resolves symbols, intervals, modes, and per-mode interval policy
- calls `ScanRuntime.run_scan(..., requested_by="autonomous")`

Important:

- autonomous scans are blocked if circuit breaker status is `OPEN`
- autonomous scans are not blocked if circuit breaker status is `DEGRADED`
- autonomous scans are serialized by the loop; no concurrent overlapping runs

## Scan Scope Expansion

The requested scan scope is expanded in two stages.

### Stage 1: mode-interval filtering

The engine does not analyze every mode on every interval blindly.

`mode_interval_sets = _normalize_mode_intervals(...)`

That produces the actual allowed interval set for each mode.

Then:

- `allowed_mode_pairs = [(interval, mode) ...]`
- `total_tasks = len(symbols) * len(allowed_mode_pairs)`
- `requested_tasks_before_pruning = len(symbols) * len(intervals) * len(modes)`

This means the displayed task count is:

- per symbol
- multiplied by each allowed `interval + mode` pair

Not:

- raw `symbols × intervals`
- raw `symbols × intervals × modes` blindly

### Stage 2: symbol throttling

Before fetch begins, the universe filter runs:

- `UniverseFilterService.evaluate(symbols)`

This may remove symbols temporarily due to:

- seeded guardrails
- stop-hit clusters
- rolling stop-rate thresholds
- cooldown windows

Output:

- `requested_symbols`
- `active_symbols`
- `throttled_symbols`
- throttle reasons

Tasks for throttled symbols are immediately counted as skipped at:

- `skip_stages.UNIVERSE_FILTER`
- `skipped.symbol_throttled`

No fetch or analysis happens for those tasks.

The persisted `result.scope` payload now records:

- requested tasks before pruning
- effective tasks after pruning
- fetch task count
- estimated bundle requests without HTF memoization
- estimated unique bundle requests with memoization
- pruning breakdown:
  - `mode_interval_policy`
  - `universe_filter`
  - deduplication counts

## Runtime Pipeline

`ScanRuntime.run_scan(...)` is the core path.

### Step 1: initialize run state

The runtime computes:

- worker count
- min confidence
- max trades per day
- fetch timeout
- universe filter state
- total task count
- initial skip counts

It creates:

- `run_id = scan-<uuid>`
- initial `v4_scan_runs` row with `status = RUNNING`
- initial `result_json` progress payload

It also creates:

- engine manifest row
- trace event `SCAN_STARTED`
- control-state activation via `scan_control.activate_run(...)`

### Step 2: build fetch tasks

After filtering:

- `effective_intervals` are intervals still needed by at least one mode
- `interval_tasks = [(symbol, interval) for symbol in active_symbols for interval in effective_intervals]`

Fetch concurrency is determined by:

- `resolved_workers`
- `max_fetch_workers = min(resolved_workers, len(interval_tasks))`

Then a `ThreadPoolExecutor` is used for fetches.

### Step 3: fetch market snapshots

Each submitted fetch calls:

- `_fetch_interval_bundle(symbol, interval)`

That does:

1. `_get_market_snapshot_cached(symbol, interval, ...)`
2. `_resolve_htf_trend(symbol, interval, ...)` if applicable

Important details:

- market snapshots are fetched per `symbol + interval`
- analysis does not run until that fetch future completes
- HTF trend fetch is a second nested market snapshot call when the interval maps to a higher timeframe

The runtime now memoizes both:

- base market bundles per run
- HTF trend resolutions per run

This means a scan can reuse:

- a fetched `1h` bundle as the HTF input for `15m`
- then reuse the same `1h` bundle again when `1h` is scanned directly later in the same run

This matters for performance:

- one visible scan task may involve more than one exchange fetch
- HTF resolution adds additional fetch pressure

### Step 4: market data runtime behavior

`MarketDataRuntime.get_market_snapshot(...)`:

1. fetches candles from Binance through the configured candle fetcher
2. persists the frame into `v4_candles`
3. builds indicator snapshot data

Fallback behavior:

- if live fetch fails, cached candles are loaded from PostgreSQL
- the snapshot is marked `stale_market_data = true`
- the scan can continue if cache exists
- if neither live nor cached data is available, the task errors

Performance implication:

- every successful fetch also writes fresh candles to PostgreSQL
- scans are not read-only; they incur write pressure too

Current write-pressure mitigation:

- `CandleRepository.replace_symbol_interval(...)` now skips the delete-and-rewrite path when the stored interval payload already matches the fetched frame
- `result.timing.stages.candle_write_skips` counts these skipped writes
- `result.timing.stages.rows_written` shows actual row volume written during the run

### Step 5: control checks during fetch

While fetch futures are pending, the runtime keeps looping with:

- `wait(..., timeout=0.25, return_when=FIRST_COMPLETED)`

During this wait loop it:

- updates debug heartbeat state
- records pending fetch count
- records oldest pending fetch age
- honors pause / stop requests
- times out hung fetches using `SCAN_FETCH_TIMEOUT_SECONDS`

So a scan can spend large time in:

- waiting for market data futures
- not in analysis

This is a critical distinction when diagnosing scan slowness.

### Step 6: analyze fetched snapshots

Once one fetch future completes:

- one snapshot is available for that `symbol + interval`
- then the engine loops through every allowed mode for that interval

For each mode:

1. control is checked again
2. `analyze_snapshot(symbol, interval, mode, snapshot)` is called
3. analysis timing is recorded
4. skip classification is applied

Possible outcomes:

- skipped neutral
- skipped low confidence
- skipped missing levels
- skipped duplicate open
- skipped daily cap reached
- skipped market unavailable
- analyzer error
- accepted signal path

### Step 7: accepted signal path

If a signal survives skip classification:

1. audit payload is built
2. signal row is persisted into `v4_signals`
3. signal attribution is captured
4. paper execution may create an order
5. trade attribution is captured on order creation/close path

This means scan runtime is not only analysis:

- it is also persistence
- audit generation
- attribution
- and optional execution

### Step 8: progress persistence

Throughout the run, `_update_run_progress(...)` persists:

- task counts
- skips
- created orders
- stale task count
- timing statistics
- current task
- debug payload
- universe filter payload

This is how the UI reads scan state.

### Step 9: finalization

When the run exits, `_finalize_run(...)` writes:

- final status
- summary
- error text
- result payload
- trace event

Possible final statuses include:

- `COMPLETED`
- `DEGRADED`
- `FAILED`
- `STOPPED`

## Scan Control

`ScanControlService` persists shared control state.

State fields include:

- `desired_state`
- `stop_requested`
- `stop_requested_by`
- `pause_requested_by`
- `resume_requested_by`
- `active_run_id`
- `active_status`
- `current_task`
- `progress_updated_at_utc`
- `last_action`

Routes:

- `POST /api/v3/scans/control/pause`
- `POST /api/v3/scans/control/resume`
- `POST /api/v3/scans/control/stop`
- `POST /api/v3/scans/control/trigger`

Important distinction:

- `stop` stops the current active run
- `trigger` wakes the autonomous loop to start the next autonomous scan cycle
- `trigger` does not force a running scan to restart

## Stop / Pause / Failure Semantics

This matters for diagnostics.

### `STOPPED`

`STOPPED` is not necessarily a failure.

It usually means:

- manual stop request
- admin stop request
- scans page stop request
- stale reconcile cancel after no progress for 5 minutes

Current result payload may include:

- `stopped = true`
- `stop_cause`
- `stop_requested_by`
- `control_last_action`
- `stale_cancelled`
- `stale_cancelled_at_utc`

### `DEGRADED`

`DEGRADED` means:

- the run completed but error rate crossed the degraded threshold
- usually some tasks failed but the run still returned a result set

### `FAILED`

`FAILED` means:

- the run crashed or could not finalize normally

### Key diagnostic rule

Do not treat `STOPPED` as proof that scanning is slow or broken.

A stopped run may have:

- zero fetches
- zero analyses
- zero execution errors

That means the stop happened before the expensive part even started.

## Timing Metrics

Each run records timing stats in:

- `result.timing.analysis`
- `result.timing.market_fetch`

It also records stage-level timings in:

- `result.timing.stages.analysis`
- `result.timing.stages.market_fetch_total`
- `result.timing.stages.market_fetch_live`
- `result.timing.stages.market_fetch_cache_load`
- `result.timing.stages.market_persist`
- `result.timing.stages.indicator_build`
- `result.timing.stages.htf_resolve`
- `result.timing.stages.signal_audit`
- `result.timing.stages.signal_persist`
- `result.timing.stages.signal_attribution`
- `result.timing.stages.execution`

It also records stage counters:

- `market_bundle_requests`
- `market_bundle_unique_fetches`
- `market_bundle_cache_hits`
- `htf_trend_requests`
- `htf_trend_unique_resolutions`
- `htf_trend_cache_hits`
- `analysis_tasks`
- `signals_emitted`
- `orders_created`
- `rows_written`
- `candle_write_skips`

Each block contains:

- `count`
- `avg_ms`
- `min_ms`
- `max_ms`

Interpretation:

- `analysis.count == 0` means analyzer never ran
- `market_fetch.count == 0` means no snapshot fetch completed
- large total wall time with low counts usually means waiting, pausing, or stop/cancel behavior

## Debug Payload

Each run may carry debug data in `result.debug`.

Current fields include:

- `last_progress_reason`
- `last_progress_at_utc`
- `last_completed_task`
- `pending_fetch_count`
- `pending_fetch_tasks`
- `oldest_pending_fetch_age_seconds`
- `timed_out_fetch_tasks`
- `wait_heartbeats`
- `fetch_timeout_seconds`

When stalled during fetch wait, the engine records:

- pending symbol/interval pairs
- how long they have been waiting
- timeout events if they exceed the fetch timeout

This is the main payload for diagnosing “scan is slow”.

## Interpreting The New Runtime Metrics

The fastest way to diagnose a slow run now is:

1. Check `result.scope`
2. Check `result.timing.market_fetch`
3. Check `result.timing.stages`

Interpretation rules:

- High `market_fetch.avg_ms` with low `analysis.avg_ms` means the run is fetch-bound.
- Large `market_bundle_requests - market_bundle_unique_fetches` means the per-run cache is preventing redundant bundle work.
- Large `htf_trend_requests` with low `htf_trend_unique_resolutions` means HTF memoization is working.
- High `market_persist.avg_ms` with low `candle_write_skips` means PostgreSQL writes are still a real part of wall time.
- High `rows_written` with low signal count means the scan is paying heavy market-data cost for limited trading output.
- High `requested_tasks_before_pruning` with much lower `effective_tasks` means early pruning is doing useful work before fetch begins.

## Autonomous Loop Interaction

`AutonomousLoop.run_forever()` manages:

- scan cadence
- open-order monitor cadence
- wake-up triggers

Important behaviors:

- one autonomous scan run must finish before the next one starts
- scan interval is target cadence, not guaranteed overlap cadence
- long scan duration delays the next scan cycle
- manual trigger sets `next_scan_at = now`, but does not create overlap
- circuit breaker `OPEN` blocks autonomous scans entirely

Implication:

If one scan takes a very long time:

- autonomous scheduling appears late
- but the bottleneck may be the existing run duration, not the scheduler

## Why Scans Can Be Slow

The main scan-time cost centers are:

1. Remote candle fetch latency
2. Higher-timeframe secondary fetches
3. Candle persistence to PostgreSQL
4. Indicator snapshot building
5. Analyzer execution per mode
6. Signal persistence and audit generation
7. Paper-execution checks for accepted signals
8. Serial non-overlapping autonomous run policy

Most likely expensive surfaces in current architecture:

- `symbol + interval` fetches from Binance
- HTF trend fetch amplification
- large scope sizes:
  - many symbols
  - many intervals
  - many modes
- progress wait loops when futures hang or slow down

Less likely primary bottleneck:

- pure analyzer compute alone, unless timing stats show large `analysis.avg_ms`

## Scope Amplification

Runtime cost scales with:

- number of active symbols after throttling
- number of effective intervals
- number of allowed modes per interval

If you request:

- 100 symbols
- 9 intervals
- 3 modes

the effective task count can become very large even before fetch retries, HTF fetches, and persistence overhead are included.

## Example Diagnostic Interpretation

Example pattern:

- `status = STOPPED`
- `completed_tasks = 24`
- `total_tasks = 1200`
- `timing.analysis.count = 0`
- `timing.market_fetch.count = 0`
- `skip_stages.UNIVERSE_FILTER = 24`
- `errors = []`

Correct interpretation:

- the run did not fail in analyzer compute
- the run did not even reach market fetch completion
- the completed tasks were throttle skips
- the run was stopped externally before real scan work began

Incorrect interpretation:

- “the analyzer took 9000 seconds”

This example is useful because it shows why stop/failure classification must be separated from actual performance diagnosis.

## What An LLM Should Focus On For Scan-Time Improvements

A useful scan-time analysis should answer:

1. How much wall time is spent waiting for market fetch versus analyzing snapshots?
2. How much HTF fetch amplification exists for the current interval set after memoization?
3. How much PostgreSQL write overhead is added by candle replacement during scans, and how often are writes skipped?
4. Can the analyzer stage be parallelized separately from fetch?
5. Is worker count now the main limiter, or is remote latency still dominating?
6. Can candle persistence be reduced or batched further for repeated scans?
7. Can scope be pruned earlier before fetch?
8. Can some intervals or modes share more work from one fetched base frame?

## Existing Safety / Debug Features

Current runtime already includes:

- pause / resume / stop control
- stale run reconcile cancel
- fetch timeout handling
- universe filter diagnostics
- timing stats for fetch and analysis
- persisted progress snapshots
- trace events for start / skip / stop / timeout

This means the best next step is not generic logging.
It is targeted measurement of:

- fetch wait
- HTF amplification
- DB write cost
- analyzer cost by mode
- execution cost on accepted signals

## Non-Goals Of This Document

This document explains the current scan system.

It does not define:

- desired future architecture
- queue redesign
- distributed workers
- exchange client redesign

Those are optimization topics to evaluate separately.
