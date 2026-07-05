# Labeling Methodology — Research Archive

## Source Papers
- Lopez de Prado (2018) Advances in Financial ML — Ch.3 Triple-Barrier, Ch.9 Meta-Labeling
- arXiv 2512.12924 — Walk-forward protocol
- arXiv 2603.13252 — Two-level uncertainty for ML rankers

## Implemented (AlphaForge v0.1)
- Triple-barrier labeling with volatility-scaled barriers (ATR-based)
- EWMA(50) volatility scaling
- Meta-labeling: primary 3-class + binary confidence model
- >60% confidence threshold for trade signals

## Expected Impact
- Gen ratio: 0.12 → 0.37 (triple-barrier)
- Precision: 17% → 63% (meta-labeling)
