                    ┌────────────────────────┐
                    │      Klines API         │
                    │ OHLCV, volume, trades   │
                    │ taker buy volume        │
                    └───────────┬────────────┘
                                │
                                ▼
                    ┌────────────────────────┐
                    │ Data Cleaning           │
                    │ missing candle, outlier │
                    │ timezone, symbol align  │
                    └───────────┬────────────┘
                                │
                                ▼
                    ┌────────────────────────┐
                    │ Deterministik Features │
                    │ return, vol, RSI, ATR, │
                    │ volume z-score, trend  │
                    └───────────┬────────────┘
                                │
                ┌───────────────┴────────────────┐
                │                                │
                ▼                                ▼
┌──────────────────────────────┐   ┌──────────────────────────────┐
│ Unsupervised Feature Layer   │   │ Label Generation Layer        │
│ anomaly score, regime id,    │   │ future return, direction,     │
│ liquidity shock, clustering  │   │ top/bottom quantile           │
└───────────────┬──────────────┘   └──────────────┬───────────────┘
                │                                 │
                └───────────────┬─────────────────┘
                                ▼
                    ┌────────────────────────┐
                    │ Final Training Dataset │
                    │ X = features           │
                    │ y = labels             │
                    └───────────┬────────────┘
                                │
                                ▼
              ┌────────────────────────────────────┐
              │ Hybrid XGBoost Model Layer          │
              │                                    │
              │ 1) XGBoost Classifier               │
              │    long / short / no-trade          │
              │                                    │
              │ 2) XGBoost Regressor                │
              │    expected future return           │
              └───────────┬────────────────────────┘
                          │
                          ▼
              ┌────────────────────────────┐
              │ Signal Engine              │
              │ probability + expected ret │
              │ confidence filter          │
              └───────────┬────────────────┘
                          │
                          ▼
              ┌────────────────────────────┐
              │ Risk & Portfolio Layer     │
              │ position size, max risk,   │
              │ stop, take profit, no-trade│
              └───────────┬────────────────┘
                          │
                          ▼
              ┌────────────────────────────┐
              │ Backtest / Paper / Live    │
              │ monitoring, drift, retrain │
              └────────────────────────────┘