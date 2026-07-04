# FACTOR_SPRINT_001_TASKBOARD

## Goal
Generate first deterministic alpha lab outputs from real OHLCV.

## Frozen
- XGBoost discovery
- mining loop
- simulation labels
- orchestrator
- vendor research
- big refactor

## Active Outputs
- ALPHA_LEADERBOARD.csv
- ALPHA_R_LEADERBOARD.csv
- ALPHA_SANITY_REPORT.md
- V7_ALPHA_CANDIDATES.md

## Execution Mode
Sequential — single-process Python scripts, no parallel agent safety needed.

## Workers / Phases
- Phase A: Factor Core (`alphaforge/factors/`)
- Phase B: R Simulator (`alphaforge/factors/r_simulator.py`)
- Phase C: Sanity + Reporting (`alphaforge/factors/leaderboard.py`)
- Phase D: Data Health (`scripts/check_factor_data.py`)

## Data Lake Facts
- 20 symbols: ADAUSDT, APTUSDT, ARBUSDT, ATOMUSDT, AVAXUSDT, BNBUSDT, BTCUSDT, DOGEUSDT, DOTUSDT, ETHUSDT, FILUSDT, INJUSDT, LINKUSDT, MATICUSDT, NEARUSDT, OPUSDT, RUNEUSDT, SOLUSDT, SUIUSDT, XRPUSDT
- Interval: 1h only (no 15m, no native 4h)
- Format: parquet at `data_lake/raw/binance/um/klines/{SYMBOL}/1h/{YEAR}/{MONTH}.parquet`
- Range: 2023-01 to 2026-07
- Gateway: `DataGateway.read_klines(symbol, interval, start, end, source='bronze')`
- Venv: `.venv` (Python 3.12, numpy, pandas, pyarrow, scipy installed)

## Current Blockers
- None identified — data lake has 20 symbols with 1h OHLCV
- 4h must be derived from 1h via resample

## Done Criteria
- `reports/alphaforge/factor_sprint/ALPHA_LEADERBOARD.csv` exists with >= 12 rows
- `reports/alphaforge/factor_sprint/ALPHA_R_LEADERBOARD.csv` exists
- `reports/alphaforge/factor_sprint/V7_ALPHA_CANDIDATES.md` exists
- `reports/alphaforge/factor_sprint/DATA_HEALTH.md` exists
- All 4 scripts run successfully
