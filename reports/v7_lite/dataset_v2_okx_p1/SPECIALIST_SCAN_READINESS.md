# Specialist Scan Readiness — V2 OKX P1

Generated: 2026-07-09T11:09:46.040964+00:00

## Can symbol_specialist_scan.py be built now?

**YES** — 8 Tier-A symbols ready.

## Ready Symbols

- BTCUSDT
- ETHUSDT
- SOLUSDT
- BNBUSDT
- XRPUSDT
- DOGEUSDT
- ADAUSDT
- LINKUSDT

## Ready Timeframes

- 1h

## Feature Groups Available

- Binance local OHLCV 1h: ✅
- OKX trades 5m: 8 symbols
- OKX trades 15m: 8 symbols
- OKX trades 1h: 8 symbols

## Scanner Input Paths

- OHLCV panel: `cache/v7_lite_expanded_panel_v1/panel_v7lite_expanded_close.parquet`
- Joined 1h panel: `cache/v7_lite_scalp_dataset_v2_okx_p1/joined/scalp_1h_panel/version=p1/panel.parquet`
- OKX 5m features: `cache/v7_lite_scalp_dataset_v2_okx_p1/microstructure/okx_trades_features_5m/`
- OKX 15m features: `cache/v7_lite_scalp_dataset_v2_okx_p1/microstructure/okx_trades_features_15m/`
- OKX 1h features: `cache/v7_lite_scalp_dataset_v2_okx_p1/microstructure/okx_trades_features_1h/`

## Blockers

- 15m base panel not available locally (BLOCKED_LOCAL_15M_MISSING)
- 15m joined panel not built
- No full alpha discovery run in this sprint
