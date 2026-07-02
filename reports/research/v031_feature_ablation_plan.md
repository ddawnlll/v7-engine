# v0.31A — Feature-Family Ablation Plan

## 1. Current Feature Set
- **60 features** across all groups
- Feature names: ['amihud_illiquidity_N', 'atr_N', 'atr_expansion_N', 'atr_pct_N', 'bb_position', 'bb_width', 'consecutive_dn_N', 'consecutive_up_N', 'cusum_negative', 'cusum_positive', 'cusum_signal', 'depth_ratio_N', 'doji_N', 'engulfing_N', 'gap_N', 'garman_klass_vol_N', 'hammer_N', 'high_low_range_N', 'highest_N', 'hmm_vol_probability']

## 2. Proposed Families

| Family | Estimated Count | Hypothesis |
|--------|----------------|------------|
| Returns/Price Action | ~10 | Short-term mean reversion signal |
| Momentum | ~8 | Trend following on multiple horizons |
| Volatility/ATR | ~6 | Regime detection, position sizing |
| Volume | ~6 | Volume confirmation / divergence |
| Trend (MA/EMA) | ~8 | Directional bias on multiple resolutions |
| Regime | ~5 | Market regime classification |
| Candle Patterns | ~6 | Single-candle pattern recognition |
| Cross-symbol | ~4 | Lead-lag relationships |
| All Features | ~60 | Full set (current baseline) |
| Shuffled (null) | 60 | Permuted labels — control for data snooping |

## 3. Methodology

1. Train with each family ALONE using same config (6-fold WFV, SCALP 1h)
2. Record OOS accuracy, net_R, fold stability
3. Compare against null (shuffled labels) baseline
4. If NO family beats null → features are not predictive → back to feature engineering
5. If 1-2 families beat null → feature set reduction is the right path
6. If ALL families beat null but combined set does not → interference / multicollinearity

## 4. Stop Condition

Ablation concludes when we have a clear answer to:

> Does any feature family carry economically meaningful OOS signal?

If yes → feature reduction + regularization.
If no → feature engineering redesign.