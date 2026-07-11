# V4 Schema

This document describes the active `v4` operational PostgreSQL schema.

Source of truth:

- [../db/models.py](../db/models.py)
- [../migrations/versions/20260331_0001_v4_foundation.py](../migrations/versions/20260331_0001_v4_foundation.py)

The `v4` rule is:

- PostgreSQL is the operational system of record
- each table has one clear ownership purpose
- repositories expose small obvious CRUD functions around these tables

## `v4_runtime_settings`

Purpose:

- persistent runtime configuration

Written by:

- settings API
- operator runtime updates

Read by:

- health and settings routes
- runtime boot and autonomous loop

Main columns:

- `key`
- `value`
- `updated_at`

Important runtime keys now include:

- `PAPER_DEFAULT_BALANCE`

## `v4_candles`

Purpose:

- persisted market candles used by scans and chart views

Written by:

- market-data runtime
- exchange bootstrap and refresh jobs

Read by:

- scan runtime
- market routes
- analyzer input builders

Main columns:

- `symbol`
- `interval`
- `open_time_utc`
- `close_time_utc`
- `open`
- `high`
- `low`
- `close`
- `volume`
- `source`
- `stale`

## `v4_scan_runs`

Purpose:

- durable scan-run metadata

Written by:

- manual scan runtime
- autonomous loop

Read by:

- scans routes
- dashboard queries
- admin summaries

Main columns:

- `run_id`
- `requested_by`
- `status`
- `symbols_csv`
- `intervals_csv`
- `modes_csv`
- `signal_count`
- `summary`
- `error_text`
- `created_at_utc`
- `started_at_utc`
- `finished_at_utc`
- `payload_json`
- `result_json`

## `v4_signals`

Purpose:

- persisted analyzer outputs linked to scan runs

Written by:

- scan runtime
- analyzer service integration layer

Read by:

- markets routes
- scans detail views
- dashboard query service

Main columns:

- `signal_id`
- `run_id`
- `symbol`
- `interval`
- `mode`
- `direction`
- `confidence`
- `regime`
- `trend`
- `trend_strength`
- `summary`
- `no_trade_reason`
- `strategy_version`
- `snapshot_json`
- `features_json`
- `factors_json`
- `created_at_utc`

`features_json` now stores the analyzer feature vector and labeled execution outcome fields used for later calibration.

## `v4_orders`

Purpose:

- persisted order ledger for paper execution

Written by:

- paper execution runtime
- manual order actions

Read by:

- trades page
- portfolio service
- admin summaries

Main columns:

- `order_id`
- `signal_id`
- `source`
- `symbol`
- `interval`
- `mode`
- `direction`
- `status`
- `entry`
- `stop_loss`
- `take_profit`
- `close_price`
- `risk_reward`
- `confidence`
- `opened_at_utc`
- `closed_at_utc`
- `payload_json`

The order payload also carries execution accounting details such as:

- `reserved_cost`
- `entry_notional`
- `fees`
- `gross_proceeds`
- `net_proceeds`
- `budget_reconciled_at_utc` for legacy open trades that were backfilled into the paper budget model

## `v4_fills`

Purpose:

- fill-level execution records

Written by:

- paper execution runtime

Read by:

- order inspection
- position calculations
- portfolio summaries

Main columns:

- `fill_id`
- `order_id`
- `symbol`
- `direction`
- `quantity`
- `price`
- `fee`
- `filled_at_utc`

## `v4_positions`

Purpose:

- current and historical position state

Written by:

- paper execution runtime
- order close/update flows

Read by:

- portfolio routes
- trades page
- dashboard summaries

Main columns:

- `position_id`
- `symbol`
- `interval`
- `mode`
- `direction`
- `quantity`
- `average_entry`
- `mark_price`
- `unrealized_pnl`
- `status`
- `opened_at_utc`
- `closed_at_utc`
- `payload_json`

## `v4_portfolio_snapshots`

Purpose:

- periodic portfolio state checkpoints

Written by:

- portfolio service
- autonomous loop checkpoints

Read by:

- portfolio routes
- dashboard query service

Main columns:

- `snapshot_id`
- `total_equity`
- `cash_balance`
- `unrealized_pnl`
- `realized_pnl`
- `open_positions`
- `closed_trades`

The snapshot payload additionally records:

- `paper_balance`
- `invested_capital`
- `net_r`

## `v4_paper_accounts`

Purpose:

- persisted paper-trading cash account used to fund orders

Written by:

- paper execution runtime
- paper budget routes

Read by:

- portfolio routes
- admin paper budget panel
- order open validation

Main columns:

- `account_key`
- `balance`
- `created_at`
- `updated_at`
- `snapshot_json`
- `created_at_utc`

## `v4_alerts`

Purpose:

- durable operator alert records

Written by:

- alert service
- health/runtime degradation detectors

Read by:

- alerts routes
- admin route
- dashboard health summaries

Main columns:

- `alert_id`
- `severity`
- `kind`
- `scope`
- `message`
- `active`
- `payload_json`
- `detected_at_utc`

## Repository Ownership

Repository mapping:

- [../db/repos/settings_repo.py](../db/repos/settings_repo.py)
- [../db/repos/candle_repo.py](../db/repos/candle_repo.py)
- [../db/repos/scan_repo.py](../db/repos/scan_repo.py)
- [../db/repos/signal_repo.py](../db/repos/signal_repo.py)
- [../db/repos/order_repo.py](../db/repos/order_repo.py)
- [../db/repos/portfolio_repo.py](../db/repos/portfolio_repo.py)
- [../db/repos/alert_repo.py](../db/repos/alert_repo.py)

Each repository should expose only obvious operations:

- `get_*`
- `list_*`
- `save_*`
- `delete_*` where necessary

This is the schema boundary `v4` should build on before adding higher-level runtime behavior.
