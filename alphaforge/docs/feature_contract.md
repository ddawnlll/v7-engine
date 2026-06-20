# AlphaForge Feature Contract

**Purpose:** Define the FeatureSetSpec format, feature groups, required metadata, and leakage prevention rules.

**Authority:** AlphaForge owns feature research and specification. This document is LOCKED.

---

## FeatureSetSpec

The canonical feature set specification. Schema: [feature_set_spec.schema.json](../../contracts/schemas/alphaforge/feature_set_spec.schema.json)

**Required fields:**
- `feature_set_id` — unique identifier
- `mode` — SCALP, AGGRESSIVE_SCALP, or SWING
- `timeframe_stack` — array of timeframes used
- `feature_groups` — array of feature group identifiers
- `features` — array of individual feature specifications
- `leakage_policy` — leakage prevention rules
- `source_dataset_refs` — references to normalized data sources
- `created_at` — ISO 8601 timestamp

---

## Feature Groups

### Returns Group
Purpose: Raw and normalized return measures.

| Feature | Description |
|---------|-------------|
| log_return_1 | 1-bar log return |
| log_return_N | N-bar log return (mode-dependent) |
| return_volatility_N | Rolling return volatility |
| return_zscore_N | Z-score of returns over window |

### Volatility Group
Purpose: Market volatility and uncertainty measures.

| Feature | Description |
|---------|-------------|
| realized_volatility_N | N-bar realized volatility |
| high_low_range_N | Normalized high-low range |
| garman_klass_vol_N | Garman-Klass volatility estimator |
| parkinson_vol_N | Parkinson volatility estimator |

### ATR Group
Purpose: Average True Range features for stop/target sizing context.

| Feature | Description |
|---------|-------------|
| atr_N | Average True Range over period N |
| atr_pct_N | ATR as percentage of price |
| atr_expansion_N | ATR vs. its own moving average |

### Momentum Group
Purpose: Trend, momentum, and rate-of-change features.

| Feature | Description |
|---------|-------------|
| momentum_N | Price change over N bars |
| roc_N | Rate of change over N bars |
| rsi_N | Relative Strength Index |
| macd | MACD line |
| macd_signal | MACD signal line |
| macd_histogram | MACD histogram |

### Volume Group
Purpose: Volume and volume-price interaction features.

| Feature | Description |
|---------|-------------|
| volume_ratio_N | Volume vs. N-bar average |
| volume_trend_N | Volume trend direction |
| vwap_deviation | Deviation from VWAP |
| obv_N | On-Balance Volume over N bars |

### Breakout Group
Purpose: Support/resistance and breakout detection.

| Feature | Description |
|---------|-------------|
| bb_position | Bollinger Band position (0-1) |
| bb_width | Bollinger Band width |
| highest_N | N-bar highest high |
| lowest_N | N-bar lowest low |
| range_breakout_N | Breakout signal relative to N-bar range |

### Lead-Lag Group
Purpose: Cross-timeframe and intermarket relationships.

| Feature | Description |
|---------|-------------|
| tf_alignment | Higher timeframe trend alignment |
| correlation_N | Correlation between related symbols |
| lead_lag_score | Lead-lag relationship score |

### Regime Group
Purpose: Market regime classification features.

| Feature | Description |
|---------|-------------|
| trend_strength_N | ADX or similar trend strength |
| volatility_regime | High/low volatility classification |
| volume_regime | High/low volume classification |
| market_hour | Session/time-of-day encoding |

### Cost Proxy Group
Purpose: Features related to expected trading costs.

| Feature | Description |
|---------|-------------|
| spread_estimate | Estimated bid-ask spread |
| liquidity_score | Composite liquidity measure |
| slippage_risk | Estimated slippage risk |
| depth_signal | Order book depth signal (if available) |

---

## Required Feature Metadata

Every individual feature must carry:

| Metadata Field | Description |
|----------------|-------------|
| feature_id | Unique feature identifier |
| name | Human-readable name |
| group | Feature group assignment |
| timeframe | Primary timeframe used |
| lookback_bars | Number of bars in lookback window |
| description | What the feature measures |
| unit | Unit of measurement |
| missing_policy | How missing values are handled |
| normalization | Normalization method if applicable |

---

## Feature Leakage Rules

### FORBIDDEN: Future-Looking Features
Any feature that uses information not available at the decision timestamp is FORBIDDEN.

Examples of leakage:
- Using the close price of the current bar when the decision is made at bar open.
- Using a rolling window that includes future bars.
- Using any feature computed from labels.
- Using target encoding without proper purging.
- Cross-sectional normalization that includes the test sample.

### REQUIRED: Leakage Policy
Every FeatureSetSpec must include a `leakage_policy` section that documents:
- Purge window (bars between train and test).
- Embargo policy (minimum gap between training and test observations).
- Point-in-time verification (how features were confirmed to be time-consistent).
- Audit trail (who reviewed and when).

---

## Mode-Specific Feature Needs

### SCALP (PRIMARY)
- Primary timeframes: 1m, 5m.
- Emphasize: momentum, breakout, cost_proxy, volume.
- Minimal lookback to avoid staleness.
- High sensitivity to spread and slippage features.

### AGGRESSIVE_SCALP (PRIMARY)
- Primary timeframes: 1m, 3m, 5m.
- Emphasize: momentum, breakout, atr, cost_proxy.
- Strong leakage controls (high dimensionality risk).
- Liquidity and spread features are critical.

### SWING (SECONDARY_BASELINE)
- Primary timeframes: 1h, 4h.
- Emphasize: returns, volatility, atr, regime, momentum.
- Standard lookback windows.
- Standard leakage controls.

---

## Related Docs

- [ai_summary.md](ai_summary.md)
- [data_contract.md](data_contract.md)
- [label_contract.md](label_contract.md)
- [report_contracts.md](report_contracts.md)
- [validation_contract.md](validation_contract.md)

## Related Contracts

- [../../contracts/schemas/alphaforge/feature_set_spec.schema.json](../../contracts/schemas/alphaforge/feature_set_spec.schema.json)

## Forbidden Assumptions

- Features do NOT guarantee alpha. They are inputs to research, not outcomes.
- No feature set is "optimal" without validation.

## Open Holds

- Exact feature formulas may be refined during implementation.
- SCALP/AGGRESSIVE_SCALP feature sets require empirical tuning.
