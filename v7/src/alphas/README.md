# Alpha Thesis Validation

Systematic walk-forward backtesting of three independent trading hypotheses
on Binance futures data. Designed to be **free** (uses Binance public API),
**reproducible** (data cached once), and **fast** (pickle cache for results).

## Directory Layout

```
src/alphas/
├── __init__.py                 # Package init with quick usage note
├── README.md                   # This file
├── requirements.txt            # Python dependencies (pandas, numpy, requests)
├── config.py                   # All configuration: thresholds, fees, paths, symbols
├── data.py                     # Data fetching (Binance API), CSV + pickle caching
├── utils.py                    # Regime detection, ATR, folds, R-multiple, bootstrap, output
├── engine.py                   # WalkForwardEngine — the reusable backtest core
├── main.py                     # Orchestrator entry point
└── hypothesises/               # All hypothesis implementations
    ├── __init__.py
    ├── altcoin_delay.py        # Hypothesis 1: Altcoin Delay
    ├── volatility_compression.py # Hypothesis 2: Volatility Compression
    ├── funding_divergence.py   # Hypothesis 3: Funding + Spot Divergence
    ├── open_interest_spike.py  # Hypothesis 4: Open Interest Spike
    ├── volume_anomaly.py       # Hypothesis 5: Volume Anomaly
    └── composite.py            # Composite signal builder (if 2+ hypotheses pass)
```

## Installation

```bash
pip install -r src/alphas/requirements.txt
```

## Usage

```bash
# Full validation (all 5 hypotheses + composite)
python -m alphas.main

# Data verification only
python -m alphas.main --check-data-only

# Single hypothesis
python -m alphas.main --hypo 4   # Open Interest Spike
python -m alphas.main --hypo 5   # Volume Anomaly

# Override symbol list
python -m alphas.main --symbols BTCUSDT ETHUSDT SOLUSDT
```

Run from the `src/` directory (or adjust `PYTHONPATH`).

## The Five Hypotheses

### 1. Altcoin Delay
**Theory:** When BTC moves > 3% in 4 hours, altcoins follow with 1-4 hour
delay as large players allocate BTC first, then rotate to altcoins.

**Signal conditions:**
- `BTC_4h_return > 3%` → long altcoin if altcoin return < BTC return
- `BTC_4h_return < -3%` → short altcoin if altcoin return > BTC return
- Delay windows tested: 1h, 2h, 4h

**Exit:** 2% stop / 4% TP / 24h max hold

### 2. Volatility Compression
**Theory:** After 72 hours of compressed volatility (< 50% of 30-day avg ATR),
a breakout in either direction has momentum.

**Signal conditions:**
- `ATR(14) < 0.50 × ATR_30d_avg` for 72+ consecutive hours
- Current candle breaks the compression-period high/low

**Exit:** 2R stop / 4R TP / 48h max hold

### 3. Funding + Spot Divergence
**Theory:** When funding rate is high (> 0.1% per 8h) but spot price isn't
rising, longs are paying for a failing move → short.

**Signal conditions:**
- `funding_rate > threshold` AND `spot_4h_return < threshold` → short
- `funding_rate < -threshold` AND `spot_4h_return > -threshold` → long

**Improvements:**
- Only fires at **funding interval boundaries** (every 8h), not on every 1h bar
- Requires **persistence**: funding must exceed threshold for 2+ consecutive
  periods before a signal triggers (reduces false positives)

**Blocked if:** Binance historical funding rate API is unavailable
(checked at runtime).

**Exit:** 2% stop / 4% TP / 12h max hold

## Methodology

### Walk-Forward Validation
- **12 monthly folds** (Jan 2022 – Dec 2024)
- **6-month rolling train window** (e.g., Jul–Dec 2021 train → Jan 2022 test)
- Parameter optimisation on train set only — never on test data
- **100 bootstrap resamples** per fold for stability metrics

### Baseline Comparisons
Every hypothesis is compared against:
1. **Random entry** — random direction at same signal frequency
2. **Buy-and-hold** — hold BTC
3. **Naive momentum** — enter when price moves > X%

### Anti-Survivorship Bias
Known delisted symbols (LUNA, FTT, CELSIUS) are included in the default
universe. If they are missing from the API, they are simply skipped.

### Fixed Exit Rules (Never Optimised)
| Rule               | Value  |
|--------------------|--------|
| Stop loss          | 2%     |
| Take profit        | 4% (2R)|
| Max hold (H1)      | 24h    |
| Max hold (H2)      | 48h    |
| Max hold (H3)      | 12h    |

## Caching

Three layers of caching make repeated runs fast:

| Layer | Location | Format | Cleared by |
|-------|----------|--------|------------|
| Raw klines & funding | `data/raw/*.csv` | CSV | Delete CSV files |
| Processed DataFrames | `data/cache/data/*.pkl` | Pickle | Delete `.pkl` files |
| Hypothesis results   | `data/cache/hypothesis_results/*.pkl` | Pickle | Delete `.pkl` or rerun |

**Pickle cache** stores the full `WalkForwardEngine` output including all
trades and fold results. Subsequent `python -m alphas.main` calls load in
~1 second instead of re-running.

To force a full recompute: `rm -rf data/cache`

## Deliverables

Per hypothesis (saved to `results/`):

| File | Description |
|------|-------------|
| `results_{hypo}.csv` | All trades with timestamps, symbols, R, regime |
| `stats_{hypo}.json` | Aggregate statistics (median R, win rate, regime breakdown) |
| `baseline_comparison_{hypo}.json` | Comparison vs random / momentum / buy-hold |
| `fold_results_{hypo}.json` | Per-fold performance (12 folds) |
| `rejection_decision_{hypo}.txt` | ACCEPTED or REJECTED with reason |

Also:
- `data_verification_report.json` — pre-test data completeness checks
- `final_summary_report.txt` / `final_summary.json` — overall gate decision

## Composite Signal

Only built if **≥ 2 hypotheses** have R-multiple > 1.5 and their
pairwise correlation is < 0.6.

```
COMPOSITE_LONG  = H1==long  AND H2 active AND (H3==long  OR H3 neutral)
COMPOSITE_SHORT = H1==short AND H2 active AND (H3==short OR H3 neutral)
```

H1 provides direction, H2 acts as a filter (movement certainty),
H3 provides confirmation.

## Recent Improvements (v2)

### 1. Altcoin Delay — Proper Temporal Alignment
**Before (bug):** BTC return and altcoin return were checked on the **same bar**.
The signal never actually captured a delay — it just checked if altcoin
underperformed BTC in the same 4h window.

**After (fix):** When BTC moves at bar `i`, the signal looks forward
`delay_bars` to bar `i + delay` and checks altcoin's return *from* bar `i`
*to* `i + delay`. If altcoin hasn't caught up, the delay is real → signal fires
at `i + delay`.

### 2. Volatility Compression — Direction Prediction
**Before:** Only detected that a breakout happened, did not predict direction.

**After:** Added **compression slope** analysis — tracks where price sits within
the compression range. If price is in the upper 40% → expect upside breakout.
Lower 40% → expect downside breakout. Only trades when the predicted direction
matches the actual breakout.

### 3. Funding Divergence — Persistence & Alignment
**Before:** Fired on any 1h bar where funding exceeded threshold.

**After:** Signals only fire at **funding interval boundaries** (every 8h).
Requires **persistence**: funding must exceed threshold for 2+ consecutive
funding periods before triggering. This eliminates noise from single-period
spikes.

### 4. Survivorship Bias — Expanded Delisted Universe
**Before:** Only 3 delisted symbols (LUNA, FTT, CELSIUS).

**After:** 34 known delisted symbols including Terra ecosystem (LUNA, UST),
FTX ecosystem (SRM, RAY, MAPS, FIDA), and 20+ low-volume delistings.

### 5. Realistic Cost Model
**Before:** Zero transaction costs.

**After:** When `REALISTIC_COST_MODEL = True` in `config.py`, every trade
incurs **taker fee (0.1%) + slippage (0.1–0.5% depending on liquidity tier)**.
Costs are applied to both entry and exit prices, directly reducing R-multiple.

### 6. Regime Filter
**Before:** No filtering — signals fired in all market regimes.

**After:** Signals in `BLOCKED_REGIMES` (default: `{"TRANSITION"}`) are
silently skipped. The regime detector classifies each bar as TRENDING,
RANGE, or TRANSITION before signal generation.

## Gating Rules

| Condition | Action |
|-----------|--------|
| **≥ 2 pass** | Proceed to system integration plan |
| **1 passes** | Write into V7 as single-point-of-failure, continue alpha search |
| **0 pass** | STOP. Do not build execution pipeline. Revisit alpha search. |

## Data Source

All data is fetched from **Binance public API** (free, no API key needed):

- Spot klines: `https://api.binance.com/api/v3/klines`
- Futures klines: `https://fapi.binance.com/fapi/v1/klines`
- Funding rate: `https://fapi.binance.com/fapi/v1/fundingRate`

Approximately **500 MB** for the full 60-symbol, 4-year dataset.
