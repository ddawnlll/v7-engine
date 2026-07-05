# Validation Framework — Research Archive

## Source Papers
- Lopez de Prado — Combinatorial Purged Cross-Validation (CPCV)
- Gort et al. (2022) arXiv 2209.05559 — DRL overfitting via hypothesis testing
- Harvey, Liu & Zhu (2016) — t-stat > 3.0 for factor significance

## Implemented (AlphaForge v0.1)
- CPCV splitter in walk_forward.py
- Purge/embargo gap in nested_wfv.py _OptunaObjective
- Hypothesis testing framework (t-stat > 3.0)
- Overfit gap < 0.10 acceptance criterion

## Gate Protocol (from v7/docs/pipeline/evaluation.md)
- G0-G3: Data integrity, no leakage, chronological order
- G4-G6: Backtest integrity, walk-forward correctness
- G7-G9: Full cross-validation, significance testing
- G10: Final model acceptance
