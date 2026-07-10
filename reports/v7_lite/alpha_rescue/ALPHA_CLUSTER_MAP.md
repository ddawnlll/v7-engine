# Alpha Cluster Map

**Generated:** 2026-07-08
**Total entries:** 170 | **Unique concepts:** ~25 | **Clusters:** 11

---

## Cluster Overview

| Cluster | Unique Concepts | Entries | Best R | Worst R | Cost Survivors | Independence |
|---------|----------------|---------|--------|---------|----------------|--------------|
| momentum | 4 | 32 | +0.0076 | -0.8394 | 0 | LOW — all ret_* variants |
| mean_reversion | 4 | 24 | +0.0043 | -0.7290 | 0 | MEDIUM — BB differs from reversal |
| volatility | 3 | 20 | -0.1293 | -1.3535 | 0 | LOW — all vol measures |
| breakout | 2 | 16 | -0.1221 | -1.0195 | 0 | MEDIUM — breakout ≠ breakdown |
| volume | 2 | 14 | -0.1449 | -1.2782 | 0 | MEDIUM — volume ≠ volume climax |
| BTC_dependency | 4 | 12 | -0.3611 | -1.4790 | 0 | LOW — all BTC-correlated |
| trend | 1 | 8 | -0.1033 | -0.1509 | 0 | VERY LOW — same concept, diff modes |
| spread_microstructure | 2 | 8 | -0.1101 | -0.1549 | 0 | MEDIUM — spread ≠ corwin-schultz |
| regime | 2 | 6 | -0.2439 | -0.7489 | 0 | LOW — compression ≠ session_vol |
| discovery_pipeline | 2 | 5 | +0.0515 | -0.0951 | 0 | HIGH — ML-based, different inputs |
| XGBoost | 1 | 2 | +0.0043 | +0.0076 | 0 | MEDIUM — diff configs |

---

## Cluster Details

### 1. Momentum Cluster (32 entries, 4 unique concepts)
Concepts: `ret_1h_rank`, `ret_4h_rank`, `ret_12h_rank`, `ret_24h_rank`
- Each concept appears in 3 modes × 4 horizons = 12 variants
- **Key finding:** ALL ret_rank factors have NEGATIVE IC — they are actually
  REVERSAL signals, not momentum. This is the most impactful classification error.
- Best representative: `ret_1h_rank` at 1h horizon (most responsive)
- Independence: VERY LOW — all variants are the same concept with different windows
- **True independent sources: 0** (all are correlated returns-based signals)

### 2. Mean Reversion Cluster (24 entries, 4 unique concepts)
Concepts: `bb_position` (XGBoost), `reversal_1h_zscore`, `reversal_4h_zscore`
- BB position is an XGBoost-enhanced mean-reversion signal
- Reversal z-scores are pure signal-based
- The `reversal_*` factors have aligned IC (positive) but negative R due to costs
- Best representative: BB position via XGBoost (+0.0043R real)
- **True independent sources: 1** (BB position is distinct from z-score reversal)

### 3. Volatility Cluster (20 entries, 3 unique concepts)
Concepts: `range_zscore`, `session_volatility_regime`
- range_zscore = normalized daily range (volatility breakout)
- session_volatility_regime = volatility regime classifier
- All negative. Volatility alone is not a reliable alpha source.
- **True independent sources: 0** (volatility is a risk factor, not alpha)

### 4. Breakout Cluster (16 entries, 2 unique concepts)
Concepts: `breakout_n_high`, `breakdown_n_low`
- Natural opposites: one longs breakouts, one shorts breakdowns
- Both are strongly negative in all modes
- The direction audit showed `breakout_n_high` has mixed IC alignment
- **True independent sources: 1** (breakouts and breakdowns are distinct)

### 5. Volume Cluster (14 entries, 2 unique concepts)
Concepts: `volume_zscore`, `volume_climax_reversal`
- volume_zscore and volume_climax are related but distinct concepts
- `volume_zscore` has flipped IC (should be short, declared long)
- **True independent sources: 1** (volume climax is event-based, differs from z-score)

### 6. BTC Dependency Cluster (12 entries, 4 unique concepts)
Concepts: BTC uptrend pullback, BTC lead-lag, BTC downtrend breakdown
- All BTC-dependent alphas are **systematically negative**
- This is the most dangerous cluster — BTC regime signals feel intuitive but
  are wrong in this dataset
- **True independent sources: 0** (all are the same "BTC predicts alts" hypothesis)

### 7. Trend Cluster (8 entries, 1 unique concept)
Concepts: `trend_pullback_ema`
- Single concept tested across 3 modes × multiple horizons
- Misdeclared direction (IC is negative for long declaration)
- **True independent sources: 0** (single concept)

### 8. Spread/Microstructure Cluster (8 entries, 2 unique concepts)
Concepts: `spread_contraction_signal`, `corwin_schultz_spread_proxy`
- Two different spread estimation methods
- Both negative but with different failure patterns
- **True independent sources: 1** (spread contraction ≠ corwin-schultz)

### 9. Regime Cluster (6 entries, 2 unique concepts)
Concepts: `compression_expansion`, `session_volatility_regime`
- Compression-expansion (BB width) is a regime detection
- Session volatility is a different regime concept
- **True independent sources: 1**

### 10. Discovery Pipeline (5 entries, 2 unique concepts)
Concepts: Discovery Pipeline V6, Operation SCALP 0.05
- Truth V6 is the only alpha that deserves continued attention
- Operation SCALP 0.05 is a production pipeline, not a specific alpha
- **True independent sources: 2** (Truth V6 and Op Scalp are different)

### 11. XGBoost (2 entries, 1 unique concept)
Concepts: BB Position v1 (contaminated)
- Single XGBoost model applied to BB position
- **True independent sources: 0** (covered under mean_reversion)

---

## True Independent Alpha Sources

After clustering, the effective independent alpha sources are:

| # | Source | Best R | Status |
|---|--------|--------|--------|
| 1 | Discovery Pipeline V6 | +0.0515R | WATCH |
| 2 | BB Position (XGBoost) | +0.0043R | CONTAMINATED |
| 3 | SCALP 1h Direction (XGBoost) | +0.0076R | WATCH |
| 4-9 | 6 factor concepts with inversion potential | NEGATIVE | INVERSION |
| 10+ | All others | NEGATIVE | REJECT/NOISE |

**Estimated truly independent alpha clusters: ~3-4.**
Not ~25 concepts, not 170 entries.

---

## Key Insight

170 entries × 25 concepts = false appearance of exploration.
The reality is: **~4 independent alpha approaches**, tested across multiple
mode/horizon configurations, with only 1 (Discovery V6) showing marginally
positive raw R.
