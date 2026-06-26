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
    "CANONICAL_V7_GATES",
    "FORBIDDEN_GATE_NAMES",
]
