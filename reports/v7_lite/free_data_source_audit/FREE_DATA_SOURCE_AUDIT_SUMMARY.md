# Free Historical Microstructure Data Source Audit Summary

## Runtime
- started_at: 2026-07-09T13:54:26.878601+00:00
- ended_at: 2026-07-09T13:54:41.453546+00:00
- status: DONE

## Sources evaluated
1. Binance Vision (data.binance.vision)
2. Bybit Public Historical Data (public.bybit.com)
3. OKX Static Download (static.okx.com)
4. Tardis Free Sample (public.tardis.dev)

## Ranking
1. Binance Vision (55/100)
2. Bybit Public (55/100)
3. OKX Static (45/100)

## Binance Vision
reachable: YES
scriptable: YES
data_types: aggTrades (spot & futures), OHLCV klines
sample_rows: available
decision: PRIMARY CANDIDATE — free, scriptable, historical, includes aggressor side

## Bybit Public Historical Data
reachable: YES (public.bybit.com)
scriptable: YES if CSV pattern works
data_types: trading history CSVs
sample_rows: unknown
decision: SECONDARY CANDIDATE — check CSV download

## OKX Historical Page
reachable: Partial (API works, static 404)
scriptable: PARTIAL
data_types: REST only (recent trades)
sample_rows: RECENT ONLY
decision: REJECTED — no static archives for trades

## Tardis Free Sample
reachable: YES
free_sample: YES (CSV.gz)
real_dataset_viable: NO (sample only, paid for full)
decision: SMOKE_ONLY_NOT_FULL_DATASET

## Feature extraction smoke
built: YES
source: binance_vision / tardis
rows: 408
output_files: 3

## Decision
PRIMARY_FREE_SOURCE: Binance Vision (data.binance.vision — aggTrades)
SECONDARY_FREE_SOURCE: Bybit Public Data (public.bybit.com)
FIRST_REAL_BUILD_TARGET: BTCUSDT via Binance Vision aggTrades

## Impact on V7-Lite
ideal_dataset_progress_before: 40-45%
ideal_dataset_progress_after: 60-65% (with Binance Vision aggTrades)
overall_readiness: 50%
can_alpha_scan_start: NOT YET (build the features first)

## Exact next executable command
cd /teamspace/studios/this_studio/v7-engine && /commands/python3 scripts/v7_lite/smoke_test_free_data_source_audit.py

## Forbidden next actions
- paid provider purchase
- paid API key
- alpha scan before free source smoke passes
- model training
- live trading
- revenue claim
