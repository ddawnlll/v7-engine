# Simulation Entrypoint Discovery

**Generated:** 2026-07-08T09:14:00Z

## Discovery Pipeline (AlphaForge → Simulation)

| Field | Value |
|-------|-------|
| entrypoint_file | `alphaforge/src/alphaforge/discovery/pipeline.py` |
| candidate_command | `PYTHONPATH=alphaforge/src:v7/src:. python3 -c "from alphaforge.discovery.pipeline import run_discovery; ..."` |
| required_inputs | `DiscoveryConfig(mode, symbols, panel_cache, folds, confidence_threshold)` |
| required_outputs | `DiscoveryResult` with `.metrics` (return_metrics, risk_metrics, exit_breakdown, cost_decomposition, symbol_breakdown) |
| confidence | HIGH |
| can_run_now | YES — panel cache exists at `cache/factor_sprint/` |
| blocker | None |

## Trade Generation

| Field | Value |
|-------|-------|
| trade_class | `BacktestTradeResult` (defined in `alphaforge/src/alphaforge/discovery/__init__.py`) |
| fields | `signal`, `realized_r_net`, `realized_r_gross`, `fee_cost_r`, `slippage_cost_r`, `funding_cost_r`, `hold_bars`, `exit_price`, `exit_reason`, `path_quality_score` |
| signal_fields | `bar_index`, `timestamp`, `symbol`, `side`, `entry_price`, `atr`, `stop_price`, `target_price`, `confidence`, `model_score`, `initial_risk` |
| backtest_path | `alphaforge/src/alphaforge/discovery/backtest.py` → `backtest_signals()` |

## Central Simulation (Factor Signals → Economic Truth)

| Field | Value |
|-------|-------|
| entrypoint_file | `experiments/v7_lite/central_sim_bridge_p0.py` |
| candidate_command | `PYTHONPATH=simulation/src:alphaforge/src:v7/src:. python3 experiments/v7_lite/central_sim_bridge_p0.py --events FACTOR_SIGNAL_EVENTS.csv --panel-cache cache/factor_sprint/ --output results.csv` |
| required_inputs | `FACTOR_SIGNAL_EVENTS.csv` (columns: timestamp, symbol, factor_name, score, direction, entry_price, atr) |
| required_outputs | `CENTRAL_SIM_RESULTS.csv` (columns: timestamp, symbol, factor_name, direction, central_long_r_net, central_short_r_net, central_best_action, central_action_gap_r) |
| confidence | HIGH — script is complete and imports resolve |
| can_run_now | YES — needs FACTOR_SIGNAL_EVENTS.csv (P0.2 output) |
| blocker | FACTOR_SIGNAL_EVENTS.csv does not yet exist |

## TrainingAdapter

| Field | Value |
|-------|-------|
| file | `simulation/adapters/training_adapter.py` |
| method | `TrainingAdapter.run(SimulationInput) -> SimulationOutput` |
| input | `SimulationInput(symbol, decision_timestamp, mode, primary_interval, entry_price, atr, future_path, profile)` |
| output | `SimulationOutput(long_outcome, short_outcome, best_action, action_gap_r)` |

## Panel Cache

| Field | Value |
|-------|-------|
| path | `cache/factor_sprint/panel_d8c8d55e3b8b107e_*.parquet` |
| fields | close, high, low, open, volume |
| symbols | ~20 symbols (BTCUSDT, ETHUSDT, SOLUSDT, etc.) |
| date_range | 2023-01-01 to 2026-05-31 (~3.5 years of 1h data) |
| bar_count | ~29,900 |

## Existing Leaderboard Data

| File | Records | Key Fields |
|------|---------|------------|
| `reports/ALPHA_INVENTORY_FULL.csv` | 171 | alpha_id, net_R_per_trade, trade_count, status, tags |
| `reports/alphaforge/factor_sprint/ALPHA_R_LEADERBOARD.csv` | 64 | alpha_name, config_name, avg_R, total_R, trades, profit_factor |
| `reports/alphaforge/factor_sprint/ALPHA_LEADERBOARD_V2.csv` | 49 | factor_name, horizon, direction, mean_rank_ic, ic_ir |
| `reports/alphaforge/factor_sprint/PROXY_R_LEADERBOARD_V2.csv` | 34 | alpha_name, avg_R, total_R, trades, simulation_source |
| `alphaforge_report/alpha_ledger.json` | 170 entries | Full alpha lifecycle records |
