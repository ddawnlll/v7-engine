"""
Evidence Engine — shared evidence pipeline for AlphaForge discovery and
V7 policy acceptance.

Sub-packages
------------
claims       Claim types and status enums.
hypothesis   HypothesisCard lifecycle (DRAFT → REGISTERED → APPROVED / REJECTED).
baselines    BaselineLibrary for model-vs-baseline comparison.
metrics      Core metric computations (net_expectancy, net_sharpe, …).
hard_caps    V1-V10 hard-cap rules (score caps, anomaly flags, blocked actions).

evidence_passport   Shared evidence passsport: AlphaForge produces it, V7 consumes it.
gate_mapping        Maps evidence dimensions to V7 canonical gates (G0-G10).
decisions           Central decision engine — ``is_implementation_allowed()``.
reports             Evidence report generation (dict, markdown, summary).
"""

from lib.evidence_engine.claims import (
    Claim,
    ClaimStatus,
    ClaimType,
)
from lib.evidence_engine.hypothesis import (
    HypothesisCard,
    HypothesisRegistry,
)
from lib.evidence_engine.baselines import (
    BaselineLibrary,
    BaselineResult,
)
from lib.evidence_engine.metrics import (
    compute_net_expectancy,
    compute_net_sharpe,
    compute_net_profit_factor,
    compute_cost_decomposition,
    compute_max_drawdown_r,
)
from lib.evidence_engine.hard_caps import (
    HardCapResult,
    apply_hard_caps,
)

# -- New integration modules --
from lib.evidence_engine.evidence_passport import (
    EvidencePassport,
    EvidencePassportBuilder,
)
from lib.evidence_engine.gate_mapping import (
    GateResult,
    GateMapper,
)
from lib.evidence_engine.decisions import (
    Decision,
    DecisionEngine,
)
from lib.evidence_engine.reports import (
    evidence_report_to_dict,
    evidence_report_to_markdown,
    generate_evidence_summary,
)

__all__ = [
    # claims
    "Claim",
    "ClaimStatus",
    "ClaimType",
    # hypothesis
    "HypothesisCard",
    "HypothesisRegistry",
    # baselines
    "BaselineLibrary",
    "BaselineResult",
    # metrics
    "compute_net_expectancy",
    "compute_net_sharpe",
    "compute_net_profit_factor",
    "compute_cost_decomposition",
    "compute_max_drawdown_r",
    # hard caps
    "HardCapResult",
    "apply_hard_caps",
    # evidence passport
    "EvidencePassport",
    "EvidencePassportBuilder",
    # gate mapping
    "GateResult",
    "GateMapper",
    # decisions
    "Decision",
    "DecisionEngine",
    # reports
    "evidence_report_to_dict",
    "evidence_report_to_markdown",
    "generate_evidence_summary",
]
