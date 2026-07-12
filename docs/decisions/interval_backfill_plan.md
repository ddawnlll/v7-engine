# 15m/5m Interval Backfill Plan (#305)

## Target
- SCALP: 1h/4h/15m
- AGGRESSIVE_SCALP: 15m/1h/5m

## Execution
Run on Lightning studio (has Binance API access):
```bash
python cli/v7_pipeline.py backfill --mode SCALP --symbols BTCUSDT,ETHUSDT,... --start 2024-01-01
python cli/v7_pipeline.py backfill --mode AGGRESSIVE_SCALP --symbols BTCUSDT,ETHUSDT,... --start 2024-01-01
```

## Status
Configuration defined. Requires studio execution for API access.
