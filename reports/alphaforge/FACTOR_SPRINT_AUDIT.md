# AlphaForge Factor Sprint Audit

> **Generated:** 2026-07-04
> **Scope:** Full AlphaForge subsystem inspection for deterministic factor sprint pivot
> **Status:** AUDIT_COMPLETE — no implementation yet

---

## 1. Executive Summary

### What AlphaForge Currently Is

AlphaForge is a **research authority layer** within V7 Engine that owns alpha discovery, feature engineering, label generation, model training, walk-forward validation, and V7 handoff packaging. It is **heavily architected around XGBoost-based supervised learning** fed by simulation-derived labels (R-multiple targets). It has a secondary autonomous rule-mining pipeline (`alphaforge.mine.*`) that uses bitset enumeration + beam search to discover alpha rules from bucketed features.

The current architecture has 12 canonical docs, ~100 source files, and ~1,600 tests. It is **P0.9A-FREEZE** blocked — the existing implementation scaffold was built before the metric ownership redesign and is known to have confusion between signal-quality metrics and trade-outcome metrics.

### Can It Support Deterministic Factor Sprint Quickly?

**Yes, with caveats.** The existing code has many pieces we need:

- ✅ **Data loaders** — `lib/data_lake/gateway.py::DataGateway` provides a clean `read_klines(symbol, interval, start, end)` that reads Parquet from the data lake
- ✅ **Feature computation** — `alphaforge.features.pipeline` provides numpy-only causal OHLCV features (returns, volatility, ATR, momentum, volume, breakout, RSI, MACD, Bollinger Bands)
- ✅ **Multi-timeframe** — `alphaforge.features.mtf` provides 4h resampling from 1h data, 1d features, and 15m features
- ✅ **Regime classification** — `alphaforge.features.regime` provides TREND_UP/DOWN/RANGE/TRANSITION classification
- ✅ **IC / Rank-IC** — `alphaforge.reports.ic_metrics` has working `compute_ic()`, `compute_rank_ic()`, `compute_ic_ir()`
- ✅ **Report writing** — `alphaforge.reports.writer` provides JSON report output
- ✅ **Cost model** — `lib/costs/` has fee/slippage primitives that can be adapted

However:

- ❌ **No forward return computation exists** — there is no `compute_forward_return(close, hours)` function anywhere
- ❌ **No top-bottom decile spread computation** — no decile portfolio simulation
- ❌ **No factor evaluation scaffold** — the existing evaluation is for XGBoost model output, not univariate factor signals
- ❌ **No symbol universe management for factors** — the existing code thinks per-symbol or multi-symbol with manifest, not cross-sectional factor ranking
- ❌ **Data only has 1h** — the data_lake currently has only 1h OHLCV for 20 symbols. **No 15m, no 4h, no 1d.** The download script supports 4h resampling from 1h, but it hasn't been run yet
- ❌ **PyArrow/pandas/numpy are not installed in the base environment** — code analysis was possible but actual execution would need a virtual environment

### Biggest Blocker

**The data lake has only 1h OHLCV klines.** 4h data would need to be resampled (the script supports it but hasn't been run), and 15m data would need to be downloaded from Binance Vision separately. No 12h or 24h timeframe exists natively — those would need to be computed as forward-return horizons from 1h bars.

### Fastest Path to ALPHA_LEADERBOARD.csv

1. Set up a Python virtual environment with numpy, pandas, pyarrow, scipy
2. Write a single `factor_sprint.py` script in a new `alphaforge/factors/` module
3. Use `DataGateway.read_klines()` to load 1h OHLCV for 20 symbols
4. Use existing feature pipeline functions to compute candidate factors
5. Write a `compute_forward_returns()` helper (about 30 lines) for 1h/4h/12h/24h horizons
6. Compute Rank-IC per factor per symbol using existing `compute_rank_ic()`
7. Rank factors by mean absolute Rank-IC, write to CSV

**Estimated effort: ~150–250 lines of new code, no existing code deleted.**

---

## 2. Current AlphaForge Flow

The actual current end-to-end flow:

```
Raw Market Data (Binance API / Binance Vision)
    │
    ▼
[lib.market_data.binance.*] — KlinesService, BinanceClient, backfill
    │  Writes to data_lake/raw/binance/um/klines/{symbol}/{interval}/{year}/{month:02d}.parquet
    ▼
[lib.data_lake.*] — DataGateway, DataLakePaths, DataCatalog
    │  Reads parquet via read_klines(symbol, interval, start, end) → pd.DataFrame
    ▼
[alphaforge.data.manifest] — DataManifest (checksummed metadata, fixture-based)
    │  Currently uses fixtures from contracts/fixtures/, NOT real data
    ▼
[alphaforge.features.pipeline] — FeaturePipeline
    │  compute_features() → numpy arrays of 50+ features (returns, vol, ATR, momentum,
    │  volume, breakout, orderbook, regime, candle_pattern)
    │  Uses FeatureCache (parquet+zstd) for caching
    ▼
[alphaforge.labels.adapter] — LabelAdapter
    │  adapt_simulation_output() → AlphaForgeLabel (LONG_NOW/SHORT_NOW/NO_TRADE + R-multiple)
    │  Input is SimulationOutput from simulation engine (NOT real market data)
    ▼
[alphaforge.dataset.assembler] — DefaultAssembler
    │  Inner-join features + labels on (symbol, timestamp), purge-window enforcement
    ▼
[alphaforge.training.xgb_trainer] — XGBoost supervised training
    │  3-class softprob (LONG_NOW/SHORT_NOW/NO_TRADE)
    │  Mode-specific hyperparameters, walk-forward validation
    ▼
[alphaforge.validation.walk_forward_runner] — Walk-forward validation
    │  6-fold anchored expanding windows
    │  Computes per-fold Sharpe, expectancy_r, win_rate, profit factor, max drawdown
    ▼
[alphaforge.reports.empirical] — Empirical report builder
    │  Produces ModeResearchReport with OOS metrics, cost stress, regime breakdown
    ▼
[alphaforge.handoff.builders] — V7HandoffPackage builder
    │  Maps to V7 canonical G0-G10 gates
    ▼
[alphaforge.reports.writer] — JSON report output
    │  Writes to reports/ or artifacts/
```

**Alternative flow (the autonomous mining pipeline):**

```
CandidateOutcomeDataset (parquet)
    ▼
[alphaforge.mine.bucketizer] — FeatureBucketizer (equi-width discretization)
    ▼
[alphaforge.mine.bitset_engine] — BitsetEngine (bitwise rule matching)
    ▼
[alphaforge.mine.beam_search] — Beam search over rule space
    ▼
[alphaforge.mine.rule_scorer] — RuleScorer (mean_net_R, sharpen, symbol/regime stability)
    ▼
[alphaforge.mine.multi_testing] — MultiTestingCorrector (Bonferroni, FDR)
    ▼
[alphaforge.mine.oos_validator] — OOSValidator
    ▼
Top rules → alpha_registry.json
```

**Current reality:** Most of this pipeline works with **synthetic data** or **fixtures**. The real data pipeline (data_lake → features → labels) has never been fully exercised end-to-end because the simulation engine that produces labels is not yet running with live market data.

---

## 3. Current Entrypoints / Commands

| Command | File | Purpose | Status |
|---------|------|---------|--------|
| `make backfill` | (Makefile) | Download market data | Downloads 1h from Binance Vision |
| `make download` | `scripts/download_binance.py` | Max-perf download (async) | Downloads 1h, resamples 4h |
| `make simulate` | (Makefile) | Run simulation with cost model | Simulation not fully wired |
| `make build-dataset` | (Makefile) | Build training dataset | Uses synthetic data |
| `make train` | (Makefile) | Train XGBoost model | Gated, uses synthetic data |
| `make wfv` | (Makefile) | Walk-forward validation | Gated |
| `make report` | (Makefile) | Generate pipeline report | Produces JSON report |
| `make pipeline` | (Makefile) | End-to-end pipeline | All steps above |
| `python -m alphaforge.mine.cli` | `mine/cli.py` | Autonomous rule mining | Requires candidates parquet |
| `python -m alphaforge.train` | `train.py` | Full training pipeline | Uses synthetic by default |
| `python scripts/train_swing_model.py` | `scripts/train_swing_model.py` | TR-05 SWING baseline | Synthetic data |
| `python scripts/train_multi_timeframe.py` | `scripts/train_multi_timeframe.py` | Multi-timeframe training | Synthetic data |
| `python scripts/run_mining.py` | `scripts/run_mining.py` | Mining pipeline runner | Uses candidates |
| `python scripts/diagnostic_v031.py` | `scripts/diagnostic_v031.py` | v0.31A failure diagnostic | Read-only |
| `pytest alphaforge/tests/` | `tests/*.py` | Test suite | 1,578+ tests |
| `make data-health` | (Makefile) | Verify Binance data | Checks parquet integrity |
| `make candidate` | (Makefile) | Run candidate v0.2 | 2-class evaluation |

---

## 4. Current Data Inputs

### Real Data (data_lake)

| Aspect | Detail |
|--------|--------|
| **Location** | `data_lake/raw/binance/um/klines/{SYMBOL}/{INTERVAL}/{YEAR}/{MM}.parquet` |
| **Intervals available** | `1h` only (verified: 20 symbols all have `1h` directories) |
| **Approximate 4h?** | ❌ Not downloaded. Script supports resampling but hasn't been run |
| **Approximate 15m?** | ❌ Not downloaded. Would need separate download |
| **Symbols** | BTCUSDT, ETHUSDT, SOLUSDT, BNBUSDT, XRPUSDT, ADAUSDT, DOTUSDT, MATICUSDT, AVAXUSDT, UNIUSDT, LINKUSDT, ATOMUSDT, LTCUSDT, BCHUSDT, DOGEUSDT, FILUSDT, APTUSDT, ARBUSDT, OPUSDT, SUIUSDT (20 symbols) |
| **Years available** | 2023, 2024, 2025, 2026 (monthly parquet files) |
| **Parquet columns** | `timestamp, open, high, low, close, volume, quote_volume, trade_count, taker_buy_base_volume, taker_buy_quote_volume, interval` |
| **Reader** | `lib.data_lake.gateway.DataGateway.read_klines(symbol, interval, start, end)` → `pd.DataFrame` |
| **Path resolver** | `lib.data_lake.storage.DataLakePaths` |
| **Catalog** | `lib.data_lake.catalog.DataCatalog` |
| **Fee/slippage primitives** | `lib/costs/` |

### Synthetic Data (fixtures)

| Aspect | Detail |
|--------|--------|
| **Location** | `contracts/fixtures/alphaforge/` |
| **Purpose** | Deterministic testing, no real market data |
| **Format** | SimulationOutput JSON → AlphaForgeLabel |
| **Currently used by** | All AlphaForge tests, manifest construction |

### Key Gap

The `alphaforge.data.manifest.build_manifest()` and all data layer code is designed around **fixtures** (JSON simulation outputs), NOT the raw data_lake. The data_lake is accessed through `lib.data_lake.gateway`, but AlphaForge's own data layer (`alphaforge.data.*`) is fixture-oriented. There is no existing adapter from data_lake Parquet → AlphaForge DataManifest.

---

## 5. Current Label / Target Logic

Labels are generated **exclusively from SimulationOutput** — the simulation engine owned by `simulation/`. AlphaForge does NOT generate its own labels.

### Label Flow

```
Simulation Engine (simulation/) 
    │  Produces SimulationOutput: long_outcome, short_outcome, no_trade_outcome,
    │  best_action, action_gap_r, regret_r, is_ambiguous, etc.
    ▼
[alphaforge.labels.adapter.LabelAdapter]
    │  adapt_simulation_output(sim_output) → AlphaForgeLabel dict
    │  Fields: label_validity, decision, gross_r, net_r, cost, regime, etc.
    ▼
[alphaforge.datasets.candidate_outcomes] — CandidateOutcomeDataset
    │  Side-specific rows (LONG/SHORT), no best-of-side selection
    │  Schema: v002 with row_id, symbol, timestamp, timeframe, mode, side, etc.
    ▼
[alphaforge.datasets.baseline_targets] — Baseline targets (XSMOM)
    │  Cross-sectional momentum ranking targets
```

### Key Findings

⚠️ **Forward returns are NOT generated anywhere.** The label system thinks in terms of simulation R-multiple outcomes, not simple forward price returns. There is no `compute_forward_return(close, horizon)` function in the entire codebase.

⚠️ **Leakage risk:** The `train.py` has a function `generate_synthetic_labels()` and `generate_synthetic_ohlcv()` that creates random labels — this is for testing only but lives alongside real training code.

⚠️ **No simple return-based target exists.** The existing labels are binary classification targets (LONG/SHORT/NO_TRADE) or R-multiple regression targets. For factor sprint we need continuous forward returns (pct change over N bars).

---

## 6. Current Feature / Rule / Alpha Generation

### Feature Computation (`alphaforge.features.pipeline`)

The feature pipeline is **mature, causal, numpy-only, and well-tested**. It computes ~50 features in 7+ groups:

| Group | Features | Status |
|-------|----------|--------|
| Returns | log_return_1, log_return_N, return_volatility_N, return_zscore_N | ✅ **Ready for factor sprint** |
| Volatility | realized_volatility_N, high_low_range_N, garman_klass_vol_N, parkinson_vol_N | ✅ Ready |
| ATR | atr_N, atr_pct_N, atr_expansion_N | ✅ Ready |
| Momentum | momentum_N, roc_N, rsi_N, macd, macd_signal, macd_histogram | ✅ Ready |
| Volume | volume_ratio_N, volume_trend_N, vwap_deviation, obv_N | ✅ Ready |
| Breakout | bb_position, bb_width, highest_N, lowest_N, range_breakout_N | ✅ Ready |
| Candle Pattern | Various candlestick patterns | ✅ Ready |
| Orderbook | Spread, microstructure, VPIN, OBI, etc. | ⚠️ Requires orderbook data (none available) |
| Regime | CUSUM, HMM volatility, vol regime | ✅ **Ready for regime breakdown** |
| Cross-Sectional Rank | Rank momentum, rank volatility, etc. | ⚠️ HOLD — P0.9B dependency |

### Multi-Timeframe Features (`alphaforge.features.mtf`)

| Function | Purpose | Status |
|----------|---------|--------|
| `compute_4h_features(ohlcv_1h, n_bars)` | 4h context from resampled 1h | ✅ Ready (4h from 1h resampling) |
| `compute_1d_features(ohlcv_1h, n_bars)` | 1d context | ✅ Ready |
| `compute_15m_features(ohlcv_1h, n_bars)` | 15m refinement | ✅ Would need 15m data |

### Rule Mining (`alphaforge.mine.*`)

This is the **autonomous alpha discovery engine** — not the current focus. It discretizes features, enumerates rule combinations via bitsets, and scores them. We bypass this for factor sprint.

### XGBoost Training (`alphaforge.training.xgb_trainer`, `alphaforge.validation.walk_forward_runner`)

The ML training pipeline is mature but we **bypass it for factor sprint**. The `walk_forward_runner.py` is an XGBoost-specific 1,500+ line module that does model training, not factor evaluation.

---

## 7. Current Evaluation Metrics

| Metric | Existing Code | Location | Useful for Factor Sprint? |
|--------|--------------|----------|--------------------------|
| **Pearson IC** | ✅ `compute_ic()` | `alphaforge.reports.ic_metrics` | ✅ Yes |
| **Rank IC (Spearman)** | ✅ `compute_rank_ic()` | `alphaforge.reports.ic_metrics` | ✅ **Core metric** |
| **IC Information Ratio** | ✅ `compute_ic_ir()` | `alphaforge.reports.ic_metrics` | ✅ Yes |
| **Calibration Error (ECE/MCE)** | ✅ `compute_calibration_error()` | `alphaforge.reports.ic_metrics` | ❌ Not needed (no probabilities) |
| **Active trade metrics** | ✅ `compute_oos_metrics()` | `alphaforge.reports.metrics` | ⚠️ Decision-oriented, needs adaption |
| **Walk-forward metrics** | ✅ `compute_all_metrics()` | `alphaforge.validation.walk_forward_runner` | ⚠️ XGBoost-specific |
| **Sharpe ratio** | ✅ `compute_sharpe_ratio()` | `alphaforge.validation.walk_forward_runner` | ⚠️ Uses simulation outputs |
| **Win rate** | ✅ `compute_win_rate()` | `alphaforge.validation.walk_forward_runner` | ⚠️ Same |
| **Profit factor** | ✅ `compute_profit_factor()` | `alphaforge.validation.walk_forward_runner` | ⚠️ Same |
| **Max drawdown** | ✅ `compute_max_drawdown()` | `alphaforge.validation.walk_forward_runner` | ⚠️ Same |
| **Forward returns (1h/4h/12h/24h)** | ❌ **NOT IMPLEMENTED** | Nowhere | 🔴 **Must build** |
| **Top-bottom decile spread** | ❌ **NOT IMPLEMENTED** | Nowhere | 🔴 **Must build** |
| **Fee/slippage net return** | ⚠️ Partial | `lib/costs/` | ⚠️ Has primitives, no factor-level adapter |
| **Turnover** | ⚠️ In `compute_oos_metrics()` | `alphaforge.reports.metrics` | ⚠️ Decision-oriented |
| **Split consistency** | ❌ **NOT IMPLEMENTED** | Nowhere | 🔴 **Must build** |
| **BTC regime breakdown** | ✅ `RegimeEvaluator.evaluate()` | `alphaforge.validation.regime_eval` | ✅ **Reusable** |
| **Regime classification** | ✅ `classify_regime()` | `alphaforge.features.regime` | ✅ Yes |
| **Symbol stability** | ✅ `compute_symbol_metrics()` | `alphaforge.reports.stability` | ⚠️ Needs adaptation for factor outputs |

### Verdict

The evaluation layer needs **three new functions** (forward returns, decile spread, split consistency) and can reuse the rest. The IC/Rank-IC functions are ready. The regime evaluator is ready. The report writer is ready.

---

## 8. Current Reports / Artifacts

| File | Format | Purpose | Reusable? |
|------|--------|---------|-----------|
| `reports/alphaforge/mining/*/mining_summary.json` | JSON | Mining run summary | ❌ Mining-specific |
| `reports/alphaforge/mining/*/top_rules.json` | JSON | Top discovered rules | ❌ Mining-specific |
| `reports/alphaforge/mining/*/candidate_dataset.parquet` | Parquet | Candidates | ❌ Mining-specific |
| `reports/alphaforge_v01_complete_report.md` | MD | P0.8B completion | ❌ Historical |
| `reports/alphaforge_v01_raw_data.json` | JSON | Raw research data | ❌ Historical |
| `reports/candidates/alphaforge_scalp_1h_direction_v01.json` | JSON | Candidate alpha | ⚠️ Format specific |
| `reports/candidates/xsmom_baseline_daily.json` | JSON | XSMOM baseline | ⚠️ JSON format |
| `reports/alpha_factor_research.json` | JSON | Factor research | ⚠️ Different schema |
| `reports/accp/*.accp.yaml` | YAML | ACCP task reports | ❌ Execution artifacts |
| `contracts/schemas/alphaforge/mode_research_report.schema.json` | JSON Schema | Mode report schema | ⚠️ Heavy schema, not for CSV |
| `contracts/schemas/alphaforge/v7_handoff_package.schema.json` | JSON Schema | V7 handoff | ❌ Too heavy for sprint |

**For factor sprint, we should produce simple CSVs and MD**, not JSON schema-validated reports. The existing report infrastructure is schema-heavy and tied to the full AlphaForge report contract.

---

## 9. Component Classification

| Component / File | Current Purpose | Classification | Reason | Action |
|-|-|-|-|-|
| `lib/data_lake/gateway.py` | Read klines parquet from data lake | **KEEP_FOR_FACTOR_SPRINT** | Primary data reader for OHLCV | Use directly in factor script |
| `lib/data_lake/storage.py` | Path resolution | **KEEP_FOR_FACTOR_SPRINT** | Used by gateway | Use via gateway |
| `lib/data_lake/catalog.py` | Data catalog | **KEEP_FOR_FACTOR_SPRINT** | Optional coverage check | Use if needed |
| `lib/data_lake/spec.py` | DatasetSpec | **BYPASS_FOR_NOW** | Too much abstraction for sprint | Skip |
| `lib/costs/` | Fee/slippage primitives | **KEEP_FOR_FACTOR_SPRINT** | Fee/slippage for net returns | Import directly |
| `alphaforge/features/pipeline.py` | Causal OHLCV feature computation | **KEEP_FOR_FACTOR_SPRINT** | Core factor computation | Import compute_* functions |
| `alphaforge/features/mtf.py` | Multi-timeframe features | **KEEP_FOR_FACTOR_SPRINT** | 4h resampling from 1h | Use for 4h factors |
| `alphaforge/features/regime.py` | Regime classification | **KEEP_FOR_FACTOR_SPRINT** | Regime breakdown | Use classify_regime() |
| `alphaforge/features/cross_sectional_rank.py` | Cross-symbol rank features | **KEEP_FOR_LATER_ML_META_FILTER** | P0.9B dependency | Hold for later |
| `alphaforge/features/candle_pattern.py` | Candlestick patterns | **KEEP_FOR_FACTOR_SPRINT** | Potential factor source | Optional use |
| `alphaforge/features/orderbook.py` | Orderbook features | **BYPASS_FOR_NOW** | No orderbook data available | Bypass |
| `alphaforge/features/funding.py` | Funding rate features | **BYPASS_FOR_NOW** | Funding DEFERRED | Bypass |
| `alphaforge/reports/ic_metrics.py` | IC / Rank-IC computation | **KEEP_FOR_FACTOR_SPRINT** | Core evaluation metric | Use compute_rank_ic() directly |
| `alphaforge/reports/metrics.py` | Active trade metrics | **BYPASS_FOR_NOW** | Decision-oriented, not factor-oriented | Bypass |
| `alphaforge/reports/stability.py` | Symbol/regime stability | **KEEP_FOR_FACTOR_SPRINT** | Regime breakdown reuse | Adapt for factor outputs |
| `alphaforge/reports/regime_eval.py` | RegimeEvaluator | **KEEP_FOR_FACTOR_SPRINT** | Per-regime performance breakdown | Reuse directly |
| `alphaforge/reports/writer.py` | JSON report writer | **BYPASS_FOR_NOW** | Schema-heavy, we want CSV/MD | Bypass |
| `alphaforge/reports/builders.py` | Scaffold report builders | **BYPASS_FOR_NOW** | Placeholder zeros, heavy schema | Bypass |
| `alphaforge/reports/empirical.py` | Empirical report builder | **KEEP_FOR_LATER_ML_META_FILTER** | Good for ML model evaluation | Hold for meta-filter |
| `alphaforge/reports/mht.py` | Multiple hypothesis testing | **KEEP_FOR_LATER_ML_META_FILTER** | Useful when testing many factors | Hold |
| `alphaforge/reports/collapse_detector.py` | Collapse detection | **UNKNOWN_NEEDS_INSPECTION** | Haven't inspected in detail | Inspect later |
| `alphaforge/reports/run_index.py` | Research run index | **BYPASS_FOR_NOW** | Infrastructure for run tracking | Bypass |
| `alphaforge/labels/adapter.py` | SimulationOutput → AlphaForgeLabel | **BYPASS_FOR_NOW** | Requires simulation engine output | Bypass |
| `alphaforge/datasets/candidate_outcomes.py` | Candidate outcome dataset | **BYPASS_FOR_NOW** | Heavy schema, simulation-oriented | Bypass |
| `alphaforge/datasets/baseline_targets.py` | XSMOM baseline targets | **KEEP_FOR_LATER_ML_META_FILTER** | Cross-sectional momentum | Hold |
| `alphaforge/dataset/assembler.py` | Feature + label join | **BYPASS_FOR_NOW** | Heavy pipeline, requires labels | Bypass |
| `alphaforge/data/manifest.py` | DataManifest (fixture-based) | **BYPASS_FOR_NOW** | Fixture-oriented, not real data | Bypass |
| `alphaforge/data/backfill.py` | AlphaForge backfill pipeline | **BYPASS_FOR_NOW** | Wraps lib backfill with manifest | Bypass for factor sprint |
| `alphaforge/data/scalp_manifest.py` | SCALP manifest builder | **BYPASS_FOR_NOW** | Fixture-based | Bypass |
| `alphaforge/modes/profiles.py` | Mode profiles | **KEEP_FOR_FACTOR_SPRINT** | Timeframe stacks (1h/4h/15m) | Use for config |
| `alphaforge/constants.py` | Domain constants | **KEEP_FOR_FACTOR_SPRINT** | Mode names, regimes | Use |
| `alphaforge/training/xgb_trainer.py` | XGBoost training | **KEEP_FOR_LATER_ML_META_FILTER** | ML training pipeline | Hold for meta-filter |
| `alphaforge/validation/walk_forward_runner.py` | Walk-forward w/ XGBoost | **KEEP_FOR_LATER_ML_META_FILTER** | ML walk-forward validation | Hold |
| `alphaforge/validation/walk_forward.py` | WalkForwardValidator | **KEEP_FOR_LATER_ML_META_FILTER** | Cross-validation framework | Hold |
| `alphaforge/validation/regime_eval.py` | RegimeEvaluator | **KEEP_FOR_FACTOR_SPRINT** | Per-regime breakdown | Reuse |
| `alphaforge/validation/cost_stress.py` | Cost stress testing | **KEEP_FOR_FACTOR_SPRINT** | Fee/slippage stress | Adapt for factors |
| `alphaforge/validation/stability.py` | Symbol/regime stability | **KEEP_FOR_FACTOR_SPRINT** | Stability analysis | Adapt |
| `alphaforge/handoff/builders.py` | V7 handoff package builder | **KEEP_FOR_FACTOR_SPRINT** | V7 gate mapping | Reuse for V7_HANDOFF |
| `alphaforge/handoff/dry_run.py` | Handoff dry run | **BYPASS_FOR_NOW** | Scaffold | Bypass |
| `alphaforge/train.py` | Full training pipeline | **BYPASS_FOR_NOW** | Synthetic data, XGBoost-focused | Bypass |
| `alphaforge/mine/cli.py` | Mining CLI | **BYPASS_FOR_NOW** | Autonomous mining - not current focus | Bypass |
| `alphaforge/mine/rule_scorer.py` | Rule scoring engine | **KEEP_FOR_LATER_ML_META_FILTER** | Good for factor combination | Hold |
| `alphaforge/mine/bitset_engine.py` | Bitset rule matching | **BYPASS_FOR_NOW** | Mining-specific | Bypass |
| `alphaforge/mine/bucketizer.py` | Feature bucketizer | **KEEP_FOR_LATER_ML_META_FILTER** | Useful for factor combination | Hold |
| `alphaforge/mine/beam_search.py` | Beam search over rules | **BYPASS_FOR_NOW** | Mining-specific | Bypass |
| `alphaforge/mine/multi_testing.py` | Multiple testing correction | **KEEP_FOR_LATER_ML_META_FILTER** | MHT control for many factors | Hold |
| `alphaforge/calibration/calculator.py` | Calibration metrics | **BYPASS_FOR_NOW** | For ML model calibration | Bypass |
| `alphaforge/tuning/*` | Optuna hyperparameter tuning | **KEEP_FOR_LATER_ML_META_FILTER** | ML hyperparameter search | Hold |
| `alphaforge/strategy/cross_sectional.py` | Cross-sectional strategy | **KEEP_FOR_FACTOR_SPRINT** | Rank-based portfolio simulation | Adapt for factor testing |
| `alphaforge/gates/ml_pilot.py` | ML pilot gate | **BYPASS_FOR_NOW** | Gate for ML promotion | Bypass |
| `alphaforge/lifecycle/state_machine.py` | Alpha thesis lifecycle | **BYPASS_FOR_NOW** | Heavy state machine | Bypass |
| `alphaforge/evidence_adapter.py` | Evidence adapter | **UNKNOWN_NEEDS_INSPECTION** | Haven't inspected | Inspect |
| `alphaforge/schema_loader.py` | Schema loading | **BYPASS_FOR_NOW** | Schema validation infra | Bypass |
| `alphaforge/paths.py` | Path resolution | **BYPASS_FOR_NOW** | AlphaForge paths | Bypass |
| `scripts/download_binance.py` | Binance Vision downloader | **KEEP_FOR_FACTOR_SPRINT** | Download more data as needed | Run for 4h/15m |
| `scripts/download_binance_vision.py` | Alternative downloader | **UNKNOWN_NEEDS_INSPECTION** | Older downloader | Check if still useful |

---

## 10. Minimal Deterministic Lab Proposal

### Module Layout

```
alphaforge/factors/
    __init__.py           # Expose public API
    loader.py             # Load data from data_lake via DataGateway
    factors.py            # Factor computation functions (deterministic alpha candidates)
    evaluation.py         # Forward returns, Rank-IC, decile spread, turnover, fee/slippage
    regime_breakdown.py   # Per-regime factor performance
    leaderboard.py        # Factor ranking and ALPHA_LEADERBOARD.csv output

alphaforge/evaluation/
    __init__.py
    forward_returns.py    # compute_forward_return(close, horizon_bars)
    decile_spreads.py     # compute_decile_spread(factor_signal, forward_return)
    split_consistency.py  # compute_split_consistency(per_symbol_ics, per_year_ics)

reports/alphaforge/factor_sprint/
    ALPHA_LEADERBOARD.csv
    ALPHA_REGIME_BREAKDOWN.csv
    V7_ALPHA_CANDIDATES.md
```

### Intended Files (brief descriptions — NOT implementing now)

**`alphaforge/factors/loader.py`** (~50 lines)
- Wraps `DataGateway.read_klines()` to load multi-symbol OHLCV
- Returns dict of `{symbol: pd.DataFrame}` with OHLCV columns

**`alphaforge/factors/factors.py`** (~150 lines)
- Imports existing `alphaforge.features.pipeline` functions
- Wraps them to operate per-symbol on DataFrame input
- Adds new factor-specific transformations (return ranks, z-scores, breakout signals)
- Returns DataFrame of factor signals aligned by symbol/timestamp

**`alphaforge/factors/evaluation.py`** (~200 lines)
- `compute_forward_returns(close, horizons=[1, 4, 12, 24])` → DataFrame of future returns
- `compute_rank_ic_by_symbol(factor_df, forward_ret_df)` → per-symbol Rank-IC
- `compute_top_bottom_spread(factor_series, forward_ret, n_deciles=10)` → spread perf
- `compute_turnover(factor_series)` → signal stability
- `compute_fee_adjusted_net(factor_series, forward_ret, fee_pct, slippage_pct)` → net return

**`alphaforge/factors/regime_breakdown.py`** (~80 lines)
- Uses `alphaforge.features.regime.classify_regime()` on BTC
- Groups factor performance by regime
- Produces ALPHA_REGIME_BREAKDOWN.csv

**`alphaforge/factors/leaderboard.py`** (~100 lines)
- Aggregates per-symbol Rank-IC, IC IR, decile spread, turnover
- Ranks factors by mean |Rank-IC|
- Writes ALPHA_LEADERBOARD.csv
- Writes V7_ALPHA_CANDIDATES.md with top 3-5 candidates

### Target Output Formats

**ALPHA_LEADERBOARD.csv:**
```csv
rank,factor_name,mean_rank_ic,mean_abs_rank_ic,ic_ir,top_bottom_spread,annualized_return,turnover,n_symbols,horizon
1,ret_1h_rank,0.034,0.042,1.23,0.0085,0.12,0.85,20,1h
2,volume_zscore,-0.028,0.036,-0.95,-0.0071,-0.09,0.72,20,4h
```

**ALPHA_REGIME_BREAKDOWN.csv:**
```csv
factor_name,regime,rank_ic,top_bottom_spread,sample_pct
ret_1h_rank,TREND_UP,0.052,0.012,0.35
ret_1h_rank,TREND_DOWN,-0.015,-0.003,0.25
```

**V7_ALPHA_CANDIDATES.md:**
```markdown
# V7 Alpha Candidates — Factor Sprint 001

## Top Candidate: volume_zscore
- Rank-IC: -0.028 (consistent negative, short-volume premium)
- Regime stability: strongest in RANGE
- Fee-adjusted net: 0.08% per 4h
- Suggested V7 handoff: SCALP_SHORT bias in high-volume regime
```

### Dependencies

No new dependencies beyond what's already used:
- `numpy`, `scipy` (already in `alphaforge.features`, `alphaforge.reports.ic_metrics`)
- `pandas` (already in `lib.data_lake.gateway`, `alphaforge.dataset.assembler`)
- `pyarrow` (already in `alphaforge.features.pipeline`)
- `lib.data_lake.gateway.DataFrameGateway`
- `alphaforge.features.pipeline` functions
- `alphaforge.features.regime.classify_regime`
- `alphaforge.reports.ic_metrics.compute_rank_ic`
- `lib.costs` primitives

---

## 11. First 12 Alpha Candidates

### 1. `ret_1h_rank`

| Property | Value |
|----------|-------|
| **Input columns** | `close` |
| **Timeframe** | 1h |
| **Computation** | Log return over 1 bar, cross-sectionally ranked across symbols |
| **Expected direction** | Short-term momentum: positive → buy winners |
| **Forward return horizons** | 1h (same-bar), 4h, 12h |
| **Obvious failure mode** | Reversal / bid-ask bounce noise at 1h; negative Rank-IC if short-term reversal dominates |

### 2. `ret_4h_rank`

| Property | Value |
|----------|-------|
| **Input columns** | `close` |
| **Timeframe** | 4h (resampled from 1h) |
| **Computation** | Log return over 4 bars, cross-sectionally ranked |
| **Expected direction** | Momentum: positive → continuation |
| **Forward return horizons** | 4h, 12h, 24h |
| **Obvious failure mode** | Chop / range-bound markets shred momentum |

### 3. `ret_12h_rank`

| Property | Value |
|----------|-------|
| **Input columns** | `close` |
| **Timeframe** | 12h (12 bars of 1h) |
| **Computation** | Log return over 12 bars, cross-sectionally ranked |
| **Expected direction** | Medium-term momentum: positive |
| **Forward return horizons** | 12h, 24h |
| **Obvious failure mode** | Trend exhaustion near tops/bottoms |

### 4. `ret_24h_rank`

| Property | Value |
|----------|-------|
| **Input columns** | `close` |
| **Timeframe** | 24h (24 bars of 1h) |
| **Computation** | Log return over 24 bars, cross-sectionally ranked |
| **Expected direction** | Daily momentum: positive |
| **Forward return horizons** | 24h |
| **Obvious failure mode** | Slow to react to reversals, high autocorrelation in signal |

### 5. `reversal_1h_zscore`

| Property | Value |
|----------|-------|
| **Input columns** | `close` |
| **Timeframe** | 1h |
| **Computation** | Negative of z-scored 1h return (mean-reversion signal) |
| **Expected direction** | Negative: buy recent losers, sell recent winners |
| **Forward return horizons** | 1h, 4h |
| **Obvious failure mode** | Catches falling knives in strong trends; positive correlation with momentum |

### 6. `reversal_4h_zscore`

| Property | Value |
|----------|-------|
| **Input columns** | `close` |
| **Timeframe** | 4h |
| **Computation** | Negative of z-scored 4h return |
| **Expected direction** | Negative |
| **Forward return horizons** | 4h, 12h |
| **Obvious failure mode** | Same as reversal_1h, slower to turn |

### 7. `volume_zscore`

| Property | Value |
|----------|-------|
| **Input columns** | `volume` |
| **Timeframe** | 1h |
| **Computation** | Z-score of volume relative to 20-bar rolling window |
| **Expected direction** | Negative: abnormally high volume → exhaustion / climax |
| **Forward return horizons** | 1h, 4h, 12h |
| **Obvious failure mode** | Volume spikes at news events can sustain; institutional accumulation |

### 8. `range_zscore`

| Property | Value |
|----------|-------|
| **Input columns** | `high`, `low`, `close` |
| **Timeframe** | 1h |
| **Computation** | Z-score of high-low range / close relative to 20-bar window |
| **Expected direction** | Negative: wide range → volatility mean-reversion; narrow range → expansion |
| **Forward return horizons** | 1h, 4h |
| **Obvious failure mode** | Breakouts from narrow range can be explosive (contra the signal) |

### 9. `breakout_n_high`

| Property | Value |
|----------|-------|
| **Input columns** | `high`, `close` |
| **Timeframe** | 1h |
| **Computation** | Binary: close > highest(high, 20) within last 3 bars |
| **Expected direction** | Positive: breakout above resistance → continuation |
| **Forward return horizons** | 4h, 12h |
| **Obvious failure mode** | False breakouts (trap), low sample count |

### 10. `breakdown_n_low`

| Property | Value |
|----------|-------|
| **Input columns** | `low`, `close` |
| **Timeframe** | 1h |
| **Computation** | Binary: close < lowest(low, 20) within last 3 bars |
| **Expected direction** | Negative (short): breakdown below support → continuation |
| **Forward return horizons** | 4h, 12h |
| **Obvious failure mode** | False breakdowns (bear traps), low sample count |

### 11. `trend_pullback_ema`

| Property | Value |
|----------|-------|
| **Input columns** | `close` |
| **Timeframe** | 1h |
| **Computation** | Long if price > EMA(50) and RSI < 40 (pullback in uptrend); Short if price < EMA(50) and RSI > 60 |
| **Expected direction** | Positive (long pullbacks in uptrend, short rallies in downtrend) |
| **Forward return horizons** | 4h, 12h |
| **Obvious failure mode** | Trend changes not detected fast enough; can buy into reversal |

### 12. `compression_expansion`

| Property | Value |
|----------|-------|
| **Input columns** | `high`, `low`, `close` |
| **Timeframe** | 1h |
| **Computation** | Bollinger Band width z-score: negative z-score means compressed (expect expansion) |
| **Expected direction** | Negative: compressed bands → expect volatility expansion (direction-agnostic) |
| **Forward return horizons** | 4h, 12h |
| **Obvious failure mode** | Timing: compression can persist; direction signal is absent (pure vol) |

---

## 12. Minimal Patch Plan

### P0: First ALPHA_LEADERBOARD.csv (~150-250 lines new code)

**Files to create:**

1. **`alphaforge/factors/__init__.py`** — empty
2. **`alphaforge/factors/loader.py`** — wrap `DataGateway.read_klines()` for multi-symbol
3. **`alphaforge/factors/evaluation.py`** — core: forward returns, Rank-IC, decile spread, fee-adjusted net
4. **`scripts/factor_sprint.py`** — main runner script (standalone, uses existing libs)

**Files to inspect (do not modify):**
- `lib/data_lake/gateway.py` — verify `read_klines()` signature and column names
- `lib/data_lake/storage.py` — verify path resolution
- `alphaforge/reports/ic_metrics.py` — verify `compute_rank_ic()` signature
- `alphaforge/features/pipeline.py` — verify which compute_* functions we need
- `lib/costs/` — verify fee/slippage constants

**What the script does:**
1. Load 1h OHLCV for all 20 symbols from data_lake (2023-2026)
2. For each symbol, compute factor signals (ret_1h, ret_4h, ret_12h, ret_24h, volume_zscore, etc.) using existing feature functions
3. Compute forward returns for each horizon (1h, 4h, 12h, 24h)
4. For each (factor, horizon) pair, compute cross-sectional Rank-IC at each timestamp
5. Aggregate: mean Rank-IC, IC IR, top-bottom decile spread, turnover
6. Write `ALPHA_LEADERBOARD.csv`

**Expected output:** `reports/alphaforge/factor_sprint/ALPHA_LEADERBOARD.csv`

**Command to run:**
```bash
cd /home/daskomputer/src/v7-engine
# First time: set up venv with deps
python3 -m venv .venv_factors
source .venv_factors/bin/activate
pip install numpy pandas pyarrow scipy
# Run:
PYTHONPATH=alphaforge/src:. python3 scripts/factor_sprint.py
```

**Verification:**
```bash
head -20 reports/alphaforge/factor_sprint/ALPHA_LEADERBOARD.csv
# Expect: rank,factor_name,mean_rank_ic,mean_abs_rank_ic,ic_ir,...
```

### P1: Regime Breakdown (~50 lines new code)

**Files to create/update:**
1. `alphaforge/factors/regime_breakdown.py` — use `classify_regime()` on BTC, group factors per regime

**What it does:**
1. For each (factor, horizon), compute Rank-IC within each BTC regime
2. Compute top-bottom spread per regime
3. Flag regime-concentrated or regime-dependent factors

**Expected output:** `reports/alphaforge/factor_sprint/ALPHA_REGIME_BREAKDOWN.csv`

### P2: Mini V7 Handoff (~80 lines)

**Files to create:**
1. `alphaforge/factors/leaderboard.py` — final aggregation and V7 candidate selection
2. `scripts/factor_to_v7.py` — builds `V7_ALPHA_CANDIDATES.md`

**What it does:**
1. From leaderboard, select top 3-5 factors by composite score
2. Check regime robustness (must work in ≥2 regimes)
3. Estimate fee/slippage impact using `lib/costs/`
4. Generate V7_ALPHA_CANDIDATES.md with per-candidate:
   - Factor definition
   - Rank-IC evidence
   - Regime breakdown
   - Fee-adjusted net performance
   - Suggested V7 integration point

**Expected output:** `reports/alphaforge/factor_sprint/V7_ALPHA_CANDIDATES.md`

### What NOT to do

- ❌ Do NOT modify any existing AlphaForge source file
- ❌ Do NOT import from `alphaforge.mine.*`, `alphaforge.training.*`, `alphaforge.labels.*`, `alphaforge.datasets.*`
- ❌ Do NOT touch `simulation/`, `v7/`, `runtime/`, `interface/`
- ❌ Do NOT run XGBoost
- ❌ Do NOT build manifests, datasets, or validation reports
- ❌ Do NOT try to fix the mining loop or ML pipeline

---

## 13. Commands Run

```bash
# File tree exploration
find /home/daskomputer/src/v7-engine/alphaforge -type f | head -120
ls -la /home/daskomputer/src/v7-engine/alphaforge/
find /home/daskomputer/src/v7-engine/alphaforge/src -type f -name "*.py" | sort

# Core file reads
cat /home/daskomputer/src/v7-engine/alphaforge/docs/ai_summary.md
cat /home/daskomputer/src/v7-engine/alphaforge/docs/ai_summary__v7_alphaforge_xgb.md
cat /home/daskomputer/src/v7-engine/alphaforge/src/alphaforge/paths.py
cat /home/daskomputer/src/v7-engine/alphaforge/src/alphaforge/data/__init__.py
cat /home/daskomputer/src/v7-engine/alphaforge/src/alphaforge/data/manifest.py
cat /home/daskomputer/src/v7-engine/alphaforge/src/alphaforge/data/backfill.py
cat /home/daskomputer/src/v7-engine/alphaforge/src/alphaforge/features/pipeline.py
cat /home/daskomputer/src/v7-engine/alphaforge/src/alphaforge/features/mtf.py
cat /home/daskomputer/src/v7-engine/alphaforge/src/alphaforge/features/regime.py
cat /home/daskomputer/src/v7-engine/alphaforge/src/alphaforge/features/cross_sectional_rank.py
cat /home/daskomputer/src/v7-engine/alphaforge/src/alphaforge/reports/ic_metrics.py
cat /home/daskomputer/src/v7-engine/alphaforge/src/alphaforge/reports/metrics.py
cat /home/daskomputer/src/v7-engine/alphaforge/src/alphaforge/reports/stability.py
cat /home/daskomputer/src/v7-engine/alphaforge/src/alphaforge/reports/builders.py
cat /home/daskomputer/src/v7-engine/alphaforge/src/alphaforge/reports/empirical.py
cat /home/daskomputer/src/v7-engine/alphaforge/src/alphaforge/reports/writer.py
cat /home/daskomputer/src/v7-engine/alphaforge/src/alphaforge/handoff/builders.py
cat /home/daskomputer/src/v7-engine/alphaforge/src/alphaforge/labels/adapter.py
cat /home/daskomputer/src/v7-engine/alphaforge/src/alphaforge/modes/profiles.py
cat /home/daskomputer/src/v7-engine/alphaforge/src/alphaforge/constants.py
cat /home/daskomputer/src/v7-engine/alphaforge/src/alphaforge/train.py
cat /home/daskomputer/src/v7-engine/alphaforge/src/alphaforge/dataset/assembler.py
cat /home/daskomputer/src/v7-engine/alphaforge/src/alphaforge/datasets/candidate_outcomes.py
cat /home/daskomputer/src/v7-engine/alphaforge/src/alphaforge/mine/cli.py
cat /home/daskomputer/src/v7-engine/alphaforge/src/alphaforge/mine/rule_scorer.py
cat /home/daskomputer/src/v7-engine/alphaforge/src/alphaforge/validation/regime_eval.py
cat /home/daskomputer/src/v7-engine/alphaforge/src/alphaforge/validation/walk_forward_runner.py
cat /home/daskomputer/src/v7-engine/alphaforge/src/alphaforge/strategy/cross_sectional.py
cat /home/daskomputer/src/v7-engine/alphaforge/scripts/train_swing_model.py
cat /home/daskomputer/src/v7-engine/scripts/download_binance.py
cat /home/daskomputer/src/v7-engine/lib/market_data/binance/klines_service.py
cat /home/daskomputer/src/v7-engine/lib/data_lake/gateway.py
cat /home/daskomputer/src/v7-engine/lib/data_lake/storage.py
cat /home/daskomputer/src/v7-engine/lib/data_lake/catalog.py
cat /home/daskomputer/src/v7-engine/lib/data_lake/spec.py

# Data lake inspection
find /home/daskomputer/src/v7-engine/data_lake -type d | sort
find /home/daskomputer/src/v7-engine/data_lake -name "*.parquet" | head -20
ls /home/daskomputer/src/v7-engine/data_lake/raw/binance/um/klines/BTCUSDT/
python3 -c "..."  # Parquet header inspection

# Reports inspection
find /home/daskomputer/src/v7-engine/reports -type f | sort
grep -rn "compute_ic\|compute_rank_ic\|compute_forward_return" alphaforge/src/ --include="*.py" | head -20

# Boundary check
grep -rn "data_lake" /home/daskomputer/src/v7-engine/lib/ --include="*.py" | head -20
grep -rn "rank_ic\|RankIC" /home/daskomputer/src/v7-engine/alphaforge/src/alphaforge/ --include="*.py" | head -20

# Makefile inspection
grep -n "download\|backfill\|data_lake\|load\|make" Makefile | head -30

# Test discovery
find /home/daskomputer/src/v7-engine/alphaforge/tests -name "*.py" | sort
```

---

## 14. Evidence

### Files Inspected

| File | Lines | What We Learned |
|------|-------|-----------------|
| `alphaforge/docs/ai_summary.md` | ~200 | AlphaForge architecture, authority boundaries, mode priorities |
| `alphaforge/docs/ai_summary__v7_alphaforge_xgb.md` | ~21K | Historical reference - SUPERSEDED, not authoritative |
| `alphaforge/src/alphaforge/paths.py` | 65 | Path resolution (repo_root, contracts_dir, etc.) |
| `alphaforge/src/alphaforge/constants.py` | 98 | Mode names, V7 gate IDs, regimes |
| `alphaforge/src/alphaforge/modes/profiles.py` | 70 | Mode timeframes: SCALP=1h, SWING=4h, AGGRESSIVE=15m |
| `alphaforge/src/alphaforge/data/manifest.py` | 260 | DataManifest - fixture-oriented, not for real data |
| `alphaforge/src/alphaforge/data/backfill.py` | ~800 | Backfill pipeline - wraps lib backfill with manifest |
| `alphaforge/src/alphaforge/features/pipeline.py` | ~1,950 | Causal feature computation - 50+ features, numpy-only |
| `alphaforge/src/alphaforge/features/mtf.py` | ~300 | Multi-timeframe: 4h from 1h resampling |
| `alphaforge/src/alphaforge/features/regime.py` | ~1,000 | Regime classification: TREND_UP/DOWN/RANGE/TRANSITION |
| `alphaforge/src/alphaforge/features/cross_sectional_rank.py` | ~450 | Cross-symbol rank features - HOLD (P0.9B) |
| `alphaforge/src/alphaforge/reports/ic_metrics.py` | 230 | ✅ `compute_ic()`, `compute_rank_ic()`, `compute_ic_ir()` |
| `alphaforge/src/alphaforge/reports/metrics.py` | 150 | Active trade metrics - decision-oriented |
| `alphaforge/src/alphaforge/reports/stability.py` | ~340 | Symbol/regime stability - reusable with adaptation |
| `alphaforge/src/alphaforge/reports/builders.py` | ~630 | Scaffold reports - placeholder zeros, not useful |
| `alphaforge/src/alphaforge/reports/empirical.py` | ~1,000 | Empirical reports - ML-oriented, heavy |
| `alphaforge/src/alphaforge/reports/writer.py` | 65 | JSON report writer - schema-validated |
| `alphaforge/src/alphaforge/handoff/builders.py` | ~550 | V7 handoff builder - reusable for gate mapping |
| `alphaforge/src/alphaforge/labels/adapter.py` | ~500 | SimulationOutput → AlphaForgeLabel - simulation-dependent |
| `alphaforge/src/alphaforge/train.py` | ~700 | Training pipeline - synthetic data, XGBoost |
| `alphaforge/src/alphaforge/validation/regime_eval.py` | ~460 | RegimeEvaluator - ✅ reusable |
| `alphaforge/src/alphaforge/validation/walk_forward_runner.py` | ~1,500 | XGBoost walk-forward - ML-specific |
| `alphaforge/src/alphaforge/dataset/assembler.py` | ~230 | Feature+label join - heavy pipeline |
| `alphaforge/src/alphaforge/datasets/candidate_outcomes.py` | ~630 | Candidate dataset - simulation-oriented |
| `alphaforge/src/alphaforge/mine/cli.py` | ~270 | Mining CLI - bypass for now |
| `alphaforge/src/alphaforge/strategy/cross_sectional.py` | ~350 | XSMOM strategy - reusable for rank-based portfolio |
| `alphaforge/src/alphaforge/validation/cost_stress.py` | ~200 | Cost stress - reusable |
| `lib/data_lake/gateway.py` | ~340 | ✅ `read_klines()` - clean data reader |
| `lib/data_lake/storage.py` | ~130 | ✅ Path resolution `DataLakePaths` |
| `lib/data_lake/catalog.py` | ~100 | ✅ `DataCatalog` - coverage tracking |
| `lib/data_lake/spec.py` | ~160 | DatasetSpec - valid intervals include 15m, 1h, 4h, 1d |
| `lib/market_data/binance/klines_service.py` | ~130 | KlinesService - interval support includes 15m, 30m, 1h, 4h |
| `scripts/download_binance.py` | ~500 | Downloader - supports 1h (direct), 4h (resample) |

### Tests Discovered

1,578+ tests in `alphaforge/tests/`. Key test files relevant to factor sprint:
- `test_ic_diagnosis.py` — IC/Rank-IC tests (uses `compute_rank_ic()`)
- `test_feature_pipeline.py` — Feature computation tests
- `test_regime.py` — Regime classification tests
- `test_cross_sectional_rank.py` — Cross-sectional rank tests
- `test_rule_scorer.py` — Rule scoring tests
- `test_regime_eval.py` — RegimeEvaluator tests
- `test_stability.py` — Symbol/regime stability tests

### Current Limitations

1. **No forward return computation exists** — must build `compute_forward_returns()`
2. **No top-bottom decile computation exists** — must build
3. **No factor-level fee/slippage adapter exists** — `lib/costs/` has primitives but no factor-level integration
4. **No split consistency check exists** — must build
5. **Data lake only has 1h OHLCV** — need to download 15m separately or resample 4h
6. **Python environment lacks numpy/pandas/pyarrow/scipy** — need venv setup before any execution
7. **Feature pipeline operates on numpy arrays, not DataFrames** — need adapter layer
8. **Feature pipeline expects `dict` of arrays** (`{'open': np.array, 'close': np.array, ...}`), not a DataFrame — the `train.py` and feature pipeline tests already do this conversion, so it's manageable
9. **alphaforge.mine uses an older "bucketizer→bitset" approach** that is conceptually different from factor evaluation — confirmed we should bypass it
10. **cross_sectional_rank.py is marked HOLD** (P0.9B dependency) — we can implement simple cross-sectional ranking inline in the factor script without importing from that module

### Key Decision: Import Boundaries for Factor Sprint

The new factor sprint code should:
- Import from `lib.data_lake.gateway` ✅ (shared lib, allowed)
- Import from `lib.costs` ✅ (shared lib, allowed)
- Call functions from `alphaforge.features.pipeline` ✅ (AlphaForge owns features)
- Call functions from `alphaforge.reports.ic_metrics` ✅ (AlphaForge owns metrics)
- Call functions from `alphaforge.features.regime` ✅ (AlphaForge owns regime)
- Use `alphaforge.features.mtf` for 4h resampling ✅ (AlphaForge owns features)
- **NOT** import from `alphaforge.mine.*` ❌ (bypass for now)
- **NOT** import from `alphaforge.training.*` ❌ (bypass for now)
- **NOT** import from `alphaforge.labels.*` ❌ (bypass for now)
- **NOT** import from `alphaforge.validation.walk_forward_runner` ❌ (XGBoost-specific)
- **NOT** import from `alphaforge.datasets.*` ❌ (bypass for now)
- **NOT** import from `simulation/` ❌ (truth authority boundary)

### Not Verified

- Actual parquet schema in data_lake (couldn't read without pyarrow). From the downloader code, columns are: `timestamp, open, high, low, close, volume, quote_volume, trade_count, taker_buy_base_volume, taker_buy_quote_volume, interval`
- `scripts/download_binance_vision.py` — not inspected, may have additional capabilities
- `alphaforge/evidence_adapter.py` — not inspected
- `alphaforge/reports/collapse_detector.py` — not inspected
- `alphaforge/reports/run_index.py` — not inspected
- `lib/tests/` test details — boundary tests exist but haven't examined them all
- Full AlphaForge test suite pass/fail state — confirmed 1,578 pass in ai_summary
- Whether `make download` has been run recently — data_lake has 1h data for 20 symbols through 2026, so it appears current

---

*End of audit. No AlphaForge source files were modified.*
