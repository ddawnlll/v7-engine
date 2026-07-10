# Next Specialist Discovery Plan

Generated: 2026-07-09T07:09:52Z

## Priority Order

### Phase 6A: Symbol-Specialist Discovery (IMMEDIATE)

**Goal:** Find cost-adjusted positive alpha per symbol.

**Method:**
1. Load expanded panel cache (56 symbols × 1h × OHLCV)
2. For each symbol, run factor signal generation (reuse P0.2 script)
3. Apply cost model (Truth V6 costs)
4. Identify cost-surviving candidates per symbol
5. Rank by Sharpe ratio and maximum drawdown

**Expected output:**
- Per-symbol alpha candidates with cost-adjusted metrics
- Symbol ranking by alpha quality
- Identification of specialist candidates (like SOLUSDT)

**Scripts to run:**
```bash
# Reuse existing factor signal generator
python3 scripts/v7_lite/generate_factor_signal_events.py

# New: per-symbol cost-adjusted evaluation
python3 scripts/v7_lite/symbol_specialist_scan.py  # TO BE CREATED
```

### Phase 6B: Cluster-Specialist Discovery (SHORT-TERM)

**Goal:** Find cluster-level alpha that works across correlated symbols.

**Method:**
1. Aggregate signals within each cluster (MAJORS, HIGH_BETA_L1, etc.)
2. Test cross-symbol factor combinations
3. Validate cluster-level strategies with cost model

**Expected output:**
- Cluster-level alpha candidates
- Cross-symbol correlation analysis
- Cluster specialization recommendations

### Phase 6C: Multi-Timeframe Expansion (SHORT-TERM)

**Goal:** Add 4h data for swing strategy validation.

**Command:**
```bash
python3 scripts/download_binance.py \
  --symbols BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT,XRPUSDT,DOGEUSDT,ADAUSDT,AVAXUSDT,DOTUSDT,LINKUSDT,LTCUSDT,UNIUSDT,OPUSDT,ARBUSDT \
  --intervals 4h
```

### Phase 6D: Missing Token Fetch (MEDIUM-TERM)

**Goal:** Complete MEME_RETAIL and AI_DATA clusters.

**Command:**
```bash
python3 scripts/download_binance.py \
  --symbols SHIBUSDT,PEPEUSDT,FLOKIUSDT,FETUSDT,RENDERUSDT,OCEANUSDT,WLDUSDT \
  --intervals 1h
```

### Phase 6E: Regime Label Computation (MEDIUM-TERM)

**Goal:** Add regime labels to enable regime-specialist discovery.

**Method:**
1. Compute rolling volatility regimes (high/low)
2. Compute trend regimes (up/down/sideways)
3. Label each candle with regime state
4. Test regime-conditional alpha

### Phase 6F: Session Analysis (LONG-TERM)

**Goal:** Enable session-specialist discovery.

**Prerequisites:** 15m data download

**Command:**
```bash
python3 scripts/download_binance.py \
  --symbols BTCUSDT,ETHUSDT,SOLUSDT \
  --intervals 15m
```

## Success Criteria

| Phase | Success Metric |
|-------|----------------|
| 6A | ≥3 symbols with cost-adjusted positive alpha |
| 6B | ≥2 clusters with positive aggregate alpha |
| 6C | 4h panel cache built for 14+ symbols |
| 6D | MEME_RETAIL and AI_DATA clusters complete |
| 6E | Regime labels computed for all 56 symbols |
| 6F | 15m data available for top 3 symbols |

## Timeline

- **Week 1:** Phase 6A (symbol-specialist scan)
- **Week 2:** Phase 6B + 6C (cluster discovery + 4h download)
- **Week 3:** Phase 6D + 6E (missing tokens + regime labels)
- **Week 4:** Phase 6F (session analysis)
