# Truth V6 Re-run with Per-Trade Logging — Plan

**Generated:** 2026-07-08T08:40:00+00:00
**Status:** IMPLEMENTATION_READY

---

## Current State

Truth V6 (Discovery Pipeline V6) was the best raw alpha at +0.0515R with 870 trades.
However, per-trade data was **not persisted** — only aggregate metrics remain in the
alpha ledger (`alphaforge_report/alpha_ledger.json`). This blocks:
- BTCUSDT SHORT cost survival analysis
- Confidence percentile filtering
- Symbol/direction split verification
- Regime/Session breakdown

## Pipeline Probe Results (verified)

The discovery pipeline was tested with synthetic data (500 bars, 2 symbols, 3 folds):

| Stage | Status | Time |
|-------|--------|------|
| Data loading | ✅ PASS | ~1s |
| Feature computation (102 features) | ✅ PASS | ~2s |
| Walk-forward validation (XGBoost) | ✅ PASS | ~3s |
| Signal generation (226→51 after filter) | ✅ PASS | ~1s |
| Central simulation backtest (51 trades) | ✅ PASS | ~4s |
| Profitability analysis | ✅ PASS | ~1s |
| **Total** | ✅ | **~38s** |

Key finding: The pipeline ALREADY runs all trades through the central simulation engine
(`simulation/adapters/training_adapter.py`), using the same `TrainingAdapter` as the
central sim bridge. Per-trade results are captured in `BacktestTradeResult` objects
but are NOT exported to CSV — they go out of scope after `analyze_profitability()`.

## Required Change

A **single hook** needs to be added in `alphaforge/src/alphaforge/discovery/pipeline.py`
after `backtest_signals()` returns the trade results:

```python
# In run_discovery(), after line:
results = backtest_signals(trade_signals, ohlcv, profile)

# Add:
if hasattr(config, 'trade_log_path') and config.trade_log_path:
    import csv
    with open(config.trade_log_path, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow([
            "timestamp", "symbol", "direction", "confidence",
            "entry_price", "atr", "r_net", "r_gross",
            "fee_cost", "slippage_cost", "hold_bars",
            "exit_price", "exit_reason"
        ])
        for r in results:
            w.writerow([
                r.signal.timestamp, r.signal.symbol,
                r.signal.direction, r.signal.confidence,
                r.signal.entry_price, r.signal.atr,
                r.realized_r_net, r.realized_r_gross,
                r.fee_cost_r, r.slippage_cost_r,
                r.hold_bars, r.exit_price, r.exit_reason
            ])
    print(f"Wrote {len(results)} trades to {config.trade_log_path}")
```

This is a ~20-line additive change. It does NOT alter the simulation logic, cost model,
or any existing behavior.

## Exact Re-run Command

After adding the trade log hook:

```bash
PYTHONPATH=alphaforge/src:v7/src:.

python -m alphaforge.discover \\
    --mode SCALP \\
    --panel-cache cache/factor_sprint \\
    --symbols BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT \\
    --confidence-threshold 0.55 \\
    --folds 6 \\
    --output reports/v7_lite/discovery/truth_v6_replay.json
```

With the `trade_log_path` parameter added to `DiscoveryConfig`:

```bash
# Alternative: run via Python with explicit trade_log_path
python3 -c "
from alphaforge.discovery import DiscoveryConfig
from alphaforge.discovery.pipeline import run_discovery

config = DiscoveryConfig(
    mode='SCALP',
    symbols=('BTCUSDT','ETHUSDT','SOLUSDT','BNBUSDT'),
    panel_cache='cache/factor_sprint',
    confidence_threshold=0.55,
    folds=6,
    trade_log_path='reports/v7_lite/discovery/truth_v6_trades.csv',
)

result = run_discovery(config)
"
```

## Expected Output

| Field | Content |
|-------|---------|
| **Trade log CSV** | ~200-870 rows (depending on threshold) |
| **Columns** | timestamp, symbol, direction, confidence, entry_price, atr, r_net, r_gross, fee_cost, slippage_cost, hold_bars, exit_price, exit_reason |
| **Delta from original** | Original had 870 trades; replay may differ slightly due to random seed and data updates |
| **Processing time** | ~5-30 minutes (real data, 6 folds, 4 symbols) |

## If Pipeline Code Cannot Be Modified

If the source file cannot be modified, an alternative approach:

1. Subclass `run_discovery` in a wrapper script
2. Monkey-patch `backtest_signals` to capture results before passing through
3. Store captured results to CSV

```python
# experiments/v7_lite/truth_v6_replay_wrapper.py
from alphaforge.discovery import run_discovery
from alphaforge.discovery import backtest_signals as original_backtest
import functools

trade_log = []

@functools.wraps(original_backtest)
def capturing_backtest(*args, **kwargs):
    results = original_backtest(*args, **kwargs)
    trade_log.extend(results)
    return results

# Apply monkey-patch
import alphaforge.discovery.pipeline as pipeline_mod
pipeline_mod.backtest_signals = capturing_backtest

# Run pipeline
result = run_discovery(...)
```

## Verdict

| Label | Decision |
|-------|----------|
| **TRADE_LOG_FOUND** | ❌ Original trade data not persisted |
| **TRADE_LOG_REGENERATED** | ❌ Not yet run (requires code change) |
| **REGEN_SCRIPT_CREATED_NOT_RUN** | ✅ **Probe script created and tested; full re-run not done** |
| **BLOCKED_PIPELINE_ENTRYPOINT_UNKNOWN** | ❌ Entry point is known: `python -m alphaforge.discover` |
| **BLOCKED_SOURCE_DATA_MISSING** | ❌ Panel cache exists and is usable |

The blocker is a ~20-line code change to add a `trade_log_path` hook. Estimated effort: 15 minutes.

## Next Steps

1. Add `trade_log_path` to `DiscoveryConfig` (~3 lines)
2. Add CSV export hook in `pipeline.py` (~20 lines)
3. Run the re-play command (~5-30 min)
4. Analyze BTCUSDT SHORT segment for cost survival
