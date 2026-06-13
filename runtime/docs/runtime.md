# V4 Runtime

This document describes the active `v4` scan runtime path.

For a dedicated scan-engine handoff focused on timing, control flow, and performance analysis, see:

- [/Users/hootie/src/trading-bot/v4/docs/scanning.md](/Users/hootie/src/trading-bot/v4/docs/scanning.md)

Source files:

- [/Users/hootie/src/trading-bot/v4/runtime/market_data.py](/Users/hootie/src/trading-bot/v4/runtime/market_data.py)
- [/Users/hootie/src/trading-bot/v4/runtime/scan_runtime.py](/Users/hootie/src/trading-bot/v4/runtime/scan_runtime.py)
- [/Users/hootie/src/trading-bot/v4/runtime/autonomous_loop.py](/Users/hootie/src/trading-bot/v4/runtime/autonomous_loop.py)
- [/Users/hootie/src/trading-bot/v4/runtime/paper_execution.py](/Users/hootie/src/trading-bot/v4/runtime/paper_execution.py)
- [/Users/hootie/src/trading-bot/v4/api/routes/scans.py](/Users/hootie/src/trading-bot/v4/api/routes/scans.py)

## Runtime Components

### Market data runtime

Owns:

- fetch candles from Binance through the existing Python client path
- persist candles to PostgreSQL
- fall back to cached PostgreSQL candles when exchange fetch fails
- mark stale market data explicitly

### Scan runtime

Owns:

- expand one scan request across symbols, intervals, and modes
- fetch market data snapshots
- derive higher-timeframe bias when possible
- call the analyzer wrapper
- persist scan runs
- persist signal rows

### Autonomous loop

Owns:

- load runtime settings
- pause or resume scanning
- call the scan runtime periodically
- call the paper-trade monitor periodically
- isolate scan exceptions so one bad cycle does not kill the loop

### Scan routes

Own:

- list persisted scan runs
- trigger manual scans
- inspect one persisted scan run and its signals

## One Scan Cycle

This is the active `v4` scan flow.

### 1. Request arrives

Entry points:

- `POST /api/v3/scans`
- or `AutonomousLoop.run_once()`

The request provides:

- `symbols`
- `intervals`
- `modes`
- `requested_by`

### 2. Scan run row is created

In:

- [/Users/hootie/src/trading-bot/v4/runtime/scan_runtime.py](/Users/hootie/src/trading-bot/v4/runtime/scan_runtime.py)

The runtime persists a `v4_scan_runs` row immediately with:

- `run_id`
- `status = RUNNING`
- scope fields
- initial payload JSON

### 3. Market data is loaded per symbol and interval

For each `symbol + interval` pair:

- `MarketDataRuntime.get_market_snapshot(...)` is called

That path:

- fetches fresh candles from Binance when possible
- persists them to `v4_candles`
- builds the indicator snapshot used by the analyzer

If exchange fetch fails:

- cached candles are loaded from PostgreSQL
- the snapshot is flagged as stale
- the scan can continue in degraded mode
- invalid-symbol / unsupported-market `4xx` responses are treated as skipped market tasks
- those tasks increment skip counts instead of poisoning the entire scan

### 4. Higher-timeframe bias is derived

If a higher timeframe mapping exists:

- `15m -> 1h`
- `1h -> 4h`
- `4h -> 1d`

the runtime loads that market snapshot and derives:

- `BUY`
- `SELL`
- or `MIXED`

That value is attached to the snapshot as `htf_trend`.

### 5. Analyzer runs per mode

For each `mode` in the scan request:

- `analyze_snapshot(symbol, interval, mode, snapshot)` is called

This produces one normalized signal dict.

### 6. Signal rows are persisted

Each analyzer output is written to:

- `v4_signals`

with:

- `signal_id`
- `run_id`
- market scope
- direction and confidence
- summary
- full snapshot JSON
- factors JSON

### 7. Run result is finalized

After all tasks complete:

- the runtime counts buy / sell / neutral signals
- counts stale tasks
- records any per-task errors
- updates `v4_scan_runs`

The run row is finalized with:

- `status`
- `signal_count`
- `summary`
- `error_text`
- `result_json`
- `finished_at_utc`

## One Autonomous Loop Cycle

The `v4` loop is intentionally small.

### 1. Load settings

From:

- `v4_runtime_settings`

Relevant keys:

- `AUTONOMOUS_ENABLED`
- `AUTONOMOUS_SYMBOLS`
- `AUTONOMOUS_INTERVALS`
- `AUTONOMOUS_MODES`
- `AUTONOMOUS_SCAN_INTERVAL_SECONDS`

### 2. Check pause / disable state

If paused:

- return without scanning

If disabled by settings:

- log and return without scanning

### 3. Run one scan

The loop calls:

- `ScanRuntime.run_scan(...)`

using settings-derived symbols, intervals, and modes.

### 4. Log completion or failure

On success:

- log the completed `run_id`

On failure:

- catch the exception
- log it
- keep the loop process alive

### 5. Sleep until next interval

The loop sleeps for:

- `AUTONOMOUS_SCAN_INTERVAL_SECONDS`
- `AUTONOMOUS_MONITOR_INTERVAL_SECONDS`

then repeats.

## Paper Trade Flow

The paper execution runtime now manages both execution state and cash accounting.

### Paper account model

- one singleton paper account is stored in `v4_paper_accounts`
- the default reset value comes from runtime setting `PAPER_DEFAULT_BALANCE`
- the current free cash balance is separate from portfolio snapshots

### Default setup

- default paper balance is `$100`
- admin can raise or lower the default value in runtime settings
- admin can also deposit funds into the live paper account or reset the account back to the current default
- admin can run a one-time reconciliation for legacy open paper trades created before budget tracking existed

### Order open path

When a paper order opens:

- required cash is computed as `entry * quantity + opening_fee`
- the runtime rejects the order if free paper cash is insufficient
- free paper cash is deducted immediately
- order, fill, and position rows are persisted

### Order close path

When a paper order closes:

- proceeds are computed as `exit_price * quantity - closing_fee`
- free paper cash is credited with those proceeds
- realized PnL and realized R are persisted on the order and position records
- the linked signal outcome is labeled for later calibration

### Portfolio accounting

Portfolio snapshots now separate:

- `cash_balance`: current free paper cash
- `invested_capital`: entry notional currently tied up in open positions
- `unrealized_pnl`: mark-to-market PnL on open positions
- `total_equity = cash_balance + invested_capital + unrealized_pnl`

Portfolio summary windows now expose:

- today equity change and percent
- rolling 3 day equity change and percent
- realized PnL and closed-trade counts inside each window

These windows are used by the portfolio page KPI cards and snapshot panel.

### Failure and refund behavior

- if order creation fails after cash is deducted, the deduction is refunded
- if order close persistence fails after proceeds are credited, the credit is reverted
- paper balance reset is blocked while open paper orders still exist

## Failure Behavior

### Exchange failure

Behavior:

- market-data fetch can fall back to cached PostgreSQL candles
- stale state is carried into the scan result
- the scan can still complete in degraded mode

### Per-symbol failure

Behavior:

- one symbol or interval failure is recorded in the run result
- the remaining tasks still execute

### Loop failure

Behavior:

- one failing scan cycle is logged
- the loop continues on the next interval

## Runtime Rule

Keep the runtime understandable:

- one market-data component
- one scan function
- one periodic loop
- one persistence boundary

That is the `v4` operating rule.
