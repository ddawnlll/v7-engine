# Specialist Scan Readiness — V2 OKX P2

## Can symbol_specialist_scan.py be built now?
**YES** — 20/20 Tier A+B symbols ready.

## Ready Symbols
- ADAUSDT, ARBUSDT, ATOMUSDT, AVAXUSDT, BCHUSDT, BNBUSDT, BTCUSDT, DOTUSDT
- ETHUSDT, FILUSDT, LINKUSDT, LTCUSDT, NEARUSDT, OPUSDT, SOLUSDT, SUIUSDT
- UNIUSDT, XRPUSDT, APTUSDT, DOGEUSDT

## Scanner Input Paths
- Joined 1h panel: cache/v7_lite_scalp_dataset_v2_okx_p2/joined/scalp_1h_panel/version=p2/panel.parquet
- OKX 5m: cache/v7_lite_scalp_dataset_v2_okx_p2/microstructure/okx_trades_features_5m/
- OKX 15m: cache/v7_lite_scalp_dataset_v2_okx_p2/microstructure/okx_trades_features_15m/
- OKX 1h: cache/v7_lite_scalp_dataset_v2_okx_p2/microstructure/okx_trades_features_1h/

## Recommended First Scan Scope
- symbols: BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT, DOGEUSDT, ADAUSDT, LINKUSDT
- time window: last available (recent ~1hr of OKX trades)
- feature groups: okx_5m, okx_1h
- alpha families: momentum, volume imbalance, realized_vol
