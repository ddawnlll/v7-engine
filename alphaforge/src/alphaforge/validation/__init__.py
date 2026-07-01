"""AlphaForge Validation — walk-forward validation and report assembly.

Contracts and dataclasses are defined in contracts.py.
The WalkForwardValidator implementation lives in walk_forward.py.
Cross-timeframe edge comparison lives in cross_timeframe.py.

This subpackage does NOT:
- Train models (no xgboost, sklearn, tensorflow, torch imports)
- Compute performance metrics (all metrics are NOT_EVALUATED)
- Make profitability claims
- Execute trades

Domain boundary: AlphaForge owns validation design and execution.
V7 owns final trade decisions and promotion gate authority.
"""

from alphaforge.validation.contracts import (
    NOT_EVALUATED,
    CostStressResult,
    DEFAULT_FOLD_CONFIGS,
    DEFAULT_PURGE_POLICIES,
    Fold,
    FoldResult,
    MHTControls,
    Mode,
    OOSSummary,
    PurgePolicy,
    RegimeBreakdown,
    SymbolStability,
    ValidationError,
    ValidationReport,
    ValidationVerdict,
    WalkForwardConfig,
    WindowType,
    embargo_distance,
    purge_gap,
)
from alphaforge.validation.cross_timeframe import (
    CrossTimeframeComparison,
    TimeframeEdge,
    build_timeframe_edge,
    compare_timeframes,
    compare_timeframes_to_dict,
    compute_pairwise_correlation,
)
from alphaforge.validation.regime_eval import RegimeEvaluator
from alphaforge.validation.target_validator import (
    AlphaTargetValidator,
    TargetValidatorReport,
)
from alphaforge.validation.walk_forward import WalkForwardValidator

__all__ = [
    "NOT_EVALUATED",
    "AlphaTargetValidator",
    "CostStressResult",
    "CrossTimeframeComparison",
    "DEFAULT_FOLD_CONFIGS",
    "DEFAULT_PURGE_POLICIES",
    "Fold",
    "FoldResult",
    "MHTControls",
    "Mode",
    "OOSSummary",
    "PurgePolicy",
    "RegimeBreakdown",
    "RegimeEvaluator",
    "SymbolStability",
    "TargetValidatorReport",
    "TimeframeEdge",
    "ValidationError",
    "ValidationReport",
    "ValidationVerdict",
    "WalkForwardConfig",
    "WalkForwardValidator",
    "WindowType",
    "build_timeframe_edge",
    "compare_timeframes",
    "compare_timeframes_to_dict",
    "compute_pairwise_correlation",
    "embargo_distance",
    "purge_gap",
]
