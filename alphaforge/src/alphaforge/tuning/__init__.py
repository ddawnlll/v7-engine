"""AlphaForge Tuning — hyperparameter optimization and multi-objective tuning.

This subpackage provides:
1. Objective functions (Sharpe ratio, Profit Factor) for Optuna studies.
2. NSGAII-based multi-objective optimization with Pareto frontier extraction.
3. Visualization support for Pareto-optimal trade fronts.

Domain boundary: AlphaForge owns hyperparameter search and evidence collection.
V7 owns final model acceptance decisions.
"""

from alphaforge.tuning.objectives import (
    compute_profit_factor,
    compute_sharpe_ratio,
    make_moo_objective,
)
from alphaforge.tuning.optuna_tuner import (
    create_moo_study,
    extract_pareto_front,
    optimize_moo_study,
    pareto_front_summary,
)

__all__ = [
    "compute_profit_factor",
    "compute_sharpe_ratio",
    "create_moo_study",
    "extract_pareto_front",
    "make_moo_objective",
    "optimize_moo_study",
    "pareto_front_summary",
]
