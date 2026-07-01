"""AlphaForge Tuning — Autotune Engine with Nested Walk-Forward Validation.

Replaces grid search with nested WFV:
- Inner fold: hyperparameter tuning via walk-forward validation
- Outer fold: held-out validation on unseen chronological data
- Multi-objective scoring based on economic metrics, not accuracy
- MHT-corrected candidate selection
- NO_TRADE collapse penalty
- Min active trade, cost survival, and regime stability constraints
- Primary objective: maximize cost_adjusted_active_expectancy_R

Domain boundary:
  AlphaForge owns tuning. V7 owns final acceptance of tuned models.
  This subpackage imports xgboost and numpy — it is for the training
  environment, not the gate-check environment.
"""

from alphaforge.tuning.autotune import (
    AutotuneResult,
    DEFAULT_GRID,
    HyperparameterGrid,
    InnerTrialResult,
    NestedWFVConfig,
    NestedWFVAutotune,
    OuterFoldResult,
    run_nested_wfv_autotune,
)

__all__ = [
    "AutotuneResult",
    "DEFAULT_GRID",
    "HyperparameterGrid",
    "InnerTrialResult",
    "NestedWFVConfig",
    "NestedWFVAutotune",
    "OuterFoldResult",
    "run_nested_wfv_autotune",
]
