# data/ — Canonical Data Root

All data lives here. Every system (`lib/`, `v7/`, `alphaforge/`) uses this directory as the single source of truth for data.

## Directory Layout

```
data/
  raw/          — Raw data from Binance (klines, funding rates, etc.)
  processed/    — Cleaned/normalized data ready for feature generation
  cache/        — Fast local cache (in-memory or disk)
  results/      — Output artifacts: evaluation results, backtest reports
  models/       — Trained model artifacts (XGBoost bundles, calibration files)
```

## Rules

- **No data outside `data/`.** Every system writes and reads data through this directory.
- **`lib/` writes to `data/raw/`** after fetching from Binance.
- **`v7/` and `alphaforge/` write to `data/processed/`, `data/results/`, `data/models/`**.
- **`data/cache/`** is ephemeral — can be deleted anytime without loss of provenance.
- **Large files** are gitignored. Use DVC or manual archiving for large artifacts.
- **`.gitkeep` files** are tracked so the directory structure exists in fresh clones.
