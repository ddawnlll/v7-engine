"""AlphaForge report builder interfaces — schema-valid placeholder report generation."""

from alphaforge.reports.research import (
    analyze_label_distribution,
    analyze_no_trade_quality,
    assemble_non_ml_research_context,
    cost_impact_summary,
    mht_hold_summary,
)

# Re-export legacy report builders (previously in orphaned reports.py)
# P0.9B repair: resolves package-vs-module conflict
from alphaforge.reports._minimal import (
    build_minimal_validation_report,
    build_minimal_mode_research_report,
    build_minimal_handoff_package,
)
# P0.9C empirical report builder
from alphaforge.reports.empirical import (
    build_empirical_mode_research_report,
)
# P0.9D: cross-mode aggregate research report
from alphaforge.reports.builders import (
    build_alphaforge_research_report,
)
# P0.9E: stability metrics (Issue #116)
from alphaforge.reports.stability import (
    build_stability_section,
    classify_symbol_regimes_from_ohlcv,
    compute_regime_concentration,
    compute_symbol_concentration,
    compute_symbol_metrics,
)
# P0.9F: active trade metrics (Issue #117)
from alphaforge.reports.metrics import (
    compute_oos_metrics,
)
# P0.9G: collapse detector (Issue #120)
from alphaforge.reports.collapse_detector import (
    build_collapse_report,
    build_collapse_root_cause_tree,
    compute_no_trade_trend,
    counterfactual_analysis,
    detect_no_trade_collapse,
)
from alphaforge.constants import CANONICAL_V7_GATES, FORBIDDEN_GATE_NAMES

__all__ = [
    "analyze_label_distribution",
    "analyze_no_trade_quality",
    "assemble_non_ml_research_context",
    "cost_impact_summary",
    "mht_hold_summary",
    "build_minimal_validation_report",
    "build_minimal_mode_research_report",
    "build_minimal_handoff_package",
    "build_empirical_mode_research_report",
    "build_alphaforge_research_report",
    "build_stability_section",
    "classify_symbol_regimes_from_ohlcv",
    "compute_regime_concentration",
    "compute_symbol_concentration",
    "compute_symbol_metrics",
    "compute_oos_metrics",
    "build_collapse_report",
    "build_collapse_root_cause_tree",
    "compute_no_trade_trend",
    "counterfactual_analysis",
    "detect_no_trade_collapse",
    "CANONICAL_V7_GATES",
    "FORBIDDEN_GATE_NAMES",
]
