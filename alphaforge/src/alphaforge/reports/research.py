"""AlphaForge non-ML research report analysis — P0.9C extension.

This module provides deterministic, non-ML analysis functions for
AlphaForge research reports. All functions operate on label lists
(AlphaForgeLabel dicts from TASK-04 LabeledDataset) and produce
DESCRIPTIVE-only output. No profitability claims. No model training.
No XGBoost. Verdict INCONCLUSIVE.

=== SCHEMA-TO-CONTRACT MAPPING AUDIT (WS-05-SCHEMA) ===

## ModeResearchReport (mode_research_report.schema.json)

The schema defines 18 required top-level keys. The report_contracts.md
describes 13 numbered research sections plus a Header section.

Schema required keys (18):
 1. schema_version        → infrastructure (not a research section)
 2. report_id             → Section 1: Header
 3. mode                  → Section 1: Header
 4. mode_priority         → Section 1: Header
 5. report_type           → Section 1: Header
 6. data_scope            → Section 2: Data Scope
 7. feature_set_refs      → Section 3: Feature Set References
 8. label_dataset_refs    → Section 4: Label Dataset References
 9. alpha_theses          → Section 5: Alpha Theses
10. validation_summary    → Section 6: Validation Summary
11. metrics               → Section 7: Metrics
12. cost_stress           → Section 8: Cost Stress
13. no_trade_comparison   → Section 9: NO_TRADE Comparison
14. regime_breakdown      → Section 10: Regime Breakdown
15. multiple_hypothesis_control → P0.8E addition; not yet documented
                                   in report_contracts.md section listing
16. verdict               → Section 11: Verdict
17. blocked_scopes        → Section 12: Blocked Scopes
18. limitations           → Section 13: Limitations

NOTE: The plan references 17 required keys, but the schema contains 18.
The discrepancy is schema_version (an infrastructure field counted
separately). Additionally, created_at and run_id appear in schema
properties but are NOT in the required array — they are covered under
Section 1 (Header) in the contract docs.

P0.8E Nested Required Fields (all confirmed in schema):
  cost_stress:
    - baseline_fee_pct: REQUIRED (P0.8E) -- confirmed
    - combined_stress_edge_survives: REQUIRED (P0.8E) -- confirmed
  no_trade_comparison:
    - active_beats_no_trade: REQUIRED (P0.8E) -- confirmed
    - summary: REQUIRED (P0.8E) -- confirmed
  regime_breakdown:
    - regimes: REQUIRED (P0.8E) -- confirmed
    - edge_only_in_rare_regime: REQUIRED (P0.8E) -- confirmed
  metrics:
    - oos_expectancy_r: REQUIRED (P0.8E) -- confirmed
    - oos_sharpe: REQUIRED (P0.8E) -- confirmed
    - oos_trade_count: REQUIRED (P0.8E) -- confirmed
  multiple_hypothesis_control:
    - tested_hypothesis_count: REQUIRED (P0.8E) -- confirmed
    - correction_method: REQUIRED (P0.8E) -- confirmed
    - data_snooping_risk_flag: REQUIRED (P0.8E) -- confirmed

Verdict Enum Coupling:
  PRIMARY modes (SCALP, AGGRESSIVE_SCALP):
    Schema allows: REJECT, CONTINUE_RESEARCH, CANDIDATE_FOR_V7_GATES,
                   BASELINE_VALID, BASELINE_WEAK, BLOCKED_FOR_MHT
    Contract docs: REJECT, CONTINUE_RESEARCH, CANDIDATE_FOR_V7_GATES
    GAP: Schema is more permissive than contract docs. Schema allows
         BASELINE verdicts for PRIMARY modes, but contract docs restrict
         PRIMARY to REJECT/CONTINUE_RESEARCH/CANDIDATE_FOR_V7_GATES.
         BLOCKED_FOR_MHT is a schema-level addition not in contract docs.

  SECONDARY_BASELINE modes (SWING):
    Schema allows: REJECT, CONTINUE_RESEARCH, CANDIDATE_FOR_V7_GATES,
                   BASELINE_VALID, BASELINE_WEAK, BLOCKED_FOR_MHT
    Contract docs: REJECT, BASELINE_WEAK, BASELINE_VALID,
                   CANDIDATE_FOR_V7_GATES
    GAP: Schema allows CONTINUE_RESEARCH for BASELINE modes, but
         contract docs do not. BLOCKED_FOR_MHT is a schema-level
         addition not in contract docs.

## AlphaForgeResearchReport (alphaforge_research_report.schema.json)

Schema required keys (10):
 1. schema_version                → infrastructure
 2. alphaforge_report_id          → Section 1: Header
 3. run_id                        → Section 1: Header
 4. created_at                    → Section 1: Header
 5. mode_reports                  → Section 2: Mode Reports (minItems: 3)
 6. promoted_candidates           → Section 3: Promoted Candidates
 7. rejected_candidates           → Section 4: Rejected Candidates
 8. multiple_hypothesis_control   → P0.8E addition
 9. global_limitations            → Section 5: Global Limitations
10. v7_handoff_packages           → Section 6: V7 Handoff Packages

NOTE: The plan references 9 required keys, but the schema contains 10.
The discrepancy is multiple_hypothesis_control (P0.8E addition).

## Extension Points for research.py

This module feeds into the ModeResearchReport sections:
  - analyze_label_distribution()  → label_dataset_refs section
  - analyze_no_trade_quality()    → no_trade_comparison section
  - cost_impact_summary()         → cost_stress section
  - mht_hold_summary()            → multiple_hypothesis_control section
  - assemble_non_ml_research_context() → P0.9A extension point consumed
                                          by builders.py
"""

from __future__ import annotations

from typing import Any, Dict


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

NO_TRADE_SUBCATEGORIES = [
    {
        "name": "NO_EDGE",
        "description": (
            "Simulation found no directional edge above noise for this bar. "
            "Neither LONG nor SHORT was profitable after costs."
        ),
    },
    {
        "name": "COST_DOMINATED",
        "description": (
            "Gross edge positive but net edge negative after costs. "
            "Fees and slippage consume the theoretical edge."
        ),
    },
    {
        "name": "AMBIGUOUS",
        "description": (
            "Label validity insufficient to assign a directional action. "
            "Simulation could not determine LONG vs SHORT vs NO_TRADE."
        ),
    },
    {
        "name": "EXCLUDED",
        "description": (
            "Data quality or scope filter excluded this bar from analysis. "
            "No trade decision could be formed."
        ),
    },
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_best_action(label: dict) -> str:
    """Extract best_action_label from a label dict.

    Handles missing keys gracefully by returning 'UNKNOWN'.
    """
    if not isinstance(label, dict):
        return "UNKNOWN"
    return label.get("best_action_label", "UNKNOWN")


def _parse_label_validity(label: dict) -> str:
    """Extract label_validity from a label dict.

    Handles missing keys gracefully by returning 'UNKNOWN'.
    """
    if not isinstance(label, dict):
        return "UNKNOWN"
    return label.get("label_validity", "UNKNOWN")


def _parse_numeric(label: dict, key: str, default: float = 0.0) -> float:
    """Safely extract a numeric value from a label dict."""
    if not isinstance(label, dict):
        return default
    val = label.get(key, default)
    if val is None:
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# WS-05-LABEL-DISTRIBUTION: analyze_label_distribution
# ---------------------------------------------------------------------------


def analyze_label_distribution(labels: list[dict], mode: str) -> dict:
    """Compute label distribution analysis from AlphaForgeLabel dicts.

    Determines the proportion of LONG, SHORT, NO_TRADE, and AMBIGUOUS
    labels in a dataset. Also computes best_action_counts and
    label_validity_distribution.

    Args:
        labels: List of AlphaForgeLabel dicts (from TASK-04 LabeledDataset).
        mode: Mode identifier ('SCALP', 'AGGRESSIVE_SCALP', 'SWING').

    Returns:
        Dict with keys:
            total_count (int): Total number of labels.
            long_pct (float): Percentage LONG labels, rounded to 1 decimal.
            short_pct (float): Percentage SHORT labels, rounded to 1 decimal.
            no_trade_pct (float): Percentage NO_TRADE labels, rounded to 1 decimal.
            ambiguous_pct (float): Percentage AMBIGUOUS labels, rounded to 1 decimal.
            best_action_counts (dict[str, int]): Count per best_action_label.
            label_validity_distribution (dict[str, int]): Count per validity.
    """
    if not labels:
        return {
            "total_count": 0,
            "long_pct": 0.0,
            "short_pct": 0.0,
            "no_trade_pct": 0.0,
            "ambiguous_pct": 0.0,
            "best_action_counts": {},
            "label_validity_distribution": {},
        }

    total = len(labels)
    action_counts: dict[str, int] = {}
    validity_counts: dict[str, int] = {}

    for label in labels:
        action = _parse_best_action(label)
        action_counts[action] = action_counts.get(action, 0) + 1

        validity = _parse_label_validity(label)
        validity_counts[validity] = validity_counts.get(validity, 0) + 1

    # Classify into LONG, SHORT, NO_TRADE, AMBIGUOUS
    # LONG: any action starting with "LONG" (LONG_NOW, LONG_AGGRESSIVE, etc.)
    # SHORT: any action starting with "SHORT" (SHORT_NOW, etc.)
    # NO_TRADE: any action containing "NO_TRADE" or "NO TRADE"
    # AMBIGUOUS: any action containing "AMBIGUOUS" or "UNKNOWN"
    long_count = sum(c for a, c in action_counts.items() if a.upper().startswith("LONG"))
    short_count = sum(c for a, c in action_counts.items() if a.upper().startswith("SHORT"))
    no_trade_count = sum(c for a, c in action_counts.items()
                         if "NO_TRADE" in a.upper() or "NO TRADE" in a.upper()
                         or a.upper() == "NO_TRADE")
    ambiguous_count = sum(c for a, c in action_counts.items()
                          if "AMBIGUOUS" in a.upper() or a == "UNKNOWN")

    # If any labels don't fit the four buckets, classify them as AMBIGUOUS
    classified = long_count + short_count + no_trade_count + ambiguous_count
    if classified < total:
        ambiguous_count += (total - classified)

    def _pct(count: int) -> float:
        return round((count / total) * 100.0, 1) if total > 0 else 0.0

    return {
        "total_count": total,
        "long_pct": _pct(long_count),
        "short_pct": _pct(short_count),
        "no_trade_pct": _pct(no_trade_count),
        "ambiguous_pct": _pct(ambiguous_count),
        "best_action_counts": action_counts,
        "label_validity_distribution": validity_counts,
    }


# ---------------------------------------------------------------------------
# WS-05-NO-TRADE: analyze_no_trade_quality
# ---------------------------------------------------------------------------


def analyze_no_trade_quality(
    labels: list[dict],
    mode: str,
    threshold: float = 0.5,
) -> dict:
    """Analyze NO_TRADE quality including subcategory breakdown.

    Enumerates the 4 NO_TRADE subcategories:
      - NO_EDGE: No directional edge above noise
      - COST_DOMINATED: Gross positive but net negative after costs
      - AMBIGUOUS: Label validity insufficient
      - EXCLUDED: Data quality or scope filter exclusion

    Determines whether NO_TRADE dominates directional labels.

    Args:
        labels: List of AlphaForgeLabel dicts.
        mode: Mode identifier.
        threshold: NO_TRADE dominance threshold (default 0.5).

    Returns:
        Dict with keys:
            total_no_trade (int), no_trade_pct (float),
            subcategories (list[dict] — exactly 4 entries),
            dominates_directional (bool), directional_pct (float),
            summary (str).
    """
    if not labels:
        subcategories = [
            {"name": sc["name"], "count": 0, "pct": 0.0}
            for sc in NO_TRADE_SUBCATEGORIES
        ]
        return {
            "total_no_trade": 0,
            "no_trade_pct": 0.0,
            "subcategories": subcategories,
            "dominates_directional": False,
            "directional_pct": 0.0,
            "summary": "No label data available for NO_TRADE quality analysis.",
        }

    total = len(labels)

    # Identify NO_TRADE labels and directional labels
    no_trade_indices: list[int] = []
    long_count = 0
    short_count = 0

    for i, label in enumerate(labels):
        action = _parse_best_action(label)
        if "NO_TRADE" in action.upper() or "NO TRADE" in action.upper() or action.upper() == "NO_TRADE":
            no_trade_indices.append(i)
        elif action.upper().startswith("LONG"):
            long_count += 1
        elif action.upper().startswith("SHORT"):
            short_count += 1

    total_no_trade = len(no_trade_indices)
    no_trade_pct = round((total_no_trade / total) * 100.0, 1) if total > 0 else 0.0
    directional_count = long_count + short_count
    directional_pct = round((directional_count / total) * 100.0, 1) if total > 0 else 0.0

    # Subcategory breakdown: try to use no_trade_quality field from labels.
    # When label data lacks subcategory detail (scaffold fixture case),
    # assign all NO_TRADE labels to NO_EDGE.
    subcat_counts: dict[str, int] = {sc["name"]: 0 for sc in NO_TRADE_SUBCATEGORIES}
    has_subcategory_detail = False

    for idx in no_trade_indices:
        label = labels[idx]
        quality = label.get("no_trade_quality", "")
        if quality:
            # Try to map quality string to a subcategory
            mapped = False
            quality_upper = quality.upper()
            if "COST" in quality_upper or "FEE" in quality_upper:
                subcat_counts["COST_DOMINATED"] += 1
                mapped = True
                has_subcategory_detail = True
            elif "AMBIGUOUS" in quality_upper or "UNCERTAIN" in quality_upper:
                subcat_counts["AMBIGUOUS"] += 1
                mapped = True
                has_subcategory_detail = True
            elif "EXCLUDE" in quality_upper or "FILTER" in quality_upper or "SCOPE" in quality_upper:
                subcat_counts["EXCLUDED"] += 1
                mapped = True
                has_subcategory_detail = True
            elif "EDGE" in quality_upper or "NOISE" in quality_upper:
                subcat_counts["NO_EDGE"] += 1
                mapped = True
                has_subcategory_detail = True
            elif "SAVED" in quality_upper or "CORRECT" in quality_upper:
                # SAVED_LOSS or CORRECT_NO_TRADE → correct no-trade decision
                # These don't clearly map to one subcategory, assign to NO_EDGE
                subcat_counts["NO_EDGE"] += 1
                mapped = True
                has_subcategory_detail = True
            elif "MISSED" in quality_upper:
                # MISSED_OPPORTUNITY → could be AMBIGUOUS
                subcat_counts["AMBIGUOUS"] += 1
                mapped = True
                has_subcategory_detail = True
            if not mapped:
                subcat_counts["NO_EDGE"] += 1
        else:
            subcat_counts["NO_EDGE"] += 1

    subcategories = [
        {
            "name": sc["name"],
            "count": subcat_counts[sc["name"]],
            "pct": round((subcat_counts[sc["name"]] / total_no_trade) * 100.0, 1)
            if total_no_trade > 0 else 0.0,
        }
        for sc in NO_TRADE_SUBCATEGORIES
    ]

    # Determine dominance
    dominates_directional = (
        no_trade_pct > (threshold * 100.0)
        and no_trade_pct > max(long_count / total * 100.0 if total > 0 else 0,
                              short_count / total * 100.0 if total > 0 else 0)
    )

    # Summary
    if not has_subcategory_detail and total_no_trade > 0:
        summary = (
            f"Scaffold placeholder — all {total_no_trade} NO_TRADE labels "
            f"assigned to NO_EDGE subcategory. No subcategory detail available "
            f"in label data. This limitation prevents fine-grained NO_TRADE "
            f"quality analysis. Requires real simulation output with per-bar "
            f"no_trade_quality annotations."
        )
    elif total_no_trade == 0:
        summary = (
            f"No NO_TRADE labels found in dataset ({total} labels). "
            f"All labels have directional best_action_label."
        )
    else:
        summary = (
            f"Of {total_no_trade} NO_TRADE labels ({no_trade_pct}%): "
            f"{subcat_counts['NO_EDGE']} NO_EDGE, "
            f"{subcat_counts['COST_DOMINATED']} COST_DOMINATED, "
            f"{subcat_counts['AMBIGUOUS']} AMBIGUOUS, "
            f"{subcat_counts['EXCLUDED']} EXCLUDED. "
            f"NO_TRADE {'dominates' if dominates_directional else 'does not dominate'} "
            f"directional labels."
        )

    return {
        "total_no_trade": total_no_trade,
        "no_trade_pct": no_trade_pct,
        "subcategories": subcategories,
        "dominates_directional": dominates_directional,
        "directional_pct": directional_pct,
        "summary": summary,
    }


# ---------------------------------------------------------------------------
# WS-05-COST-MHT: cost_impact_summary
# ---------------------------------------------------------------------------


def cost_impact_summary(labels: list[dict], mode: str) -> dict:
    """Compute cost impact summary from label R-values.

    Extracts gross_R and net_R values from label rows to compute
    cost drag. Cost drag = mean_gross_R - mean_net_R.
    cost_drag_pct = (cost_drag / abs(mean_gross_R)) * 100.

    Args:
        labels: List of AlphaForgeLabel dicts.
        mode: Mode identifier.

    Returns:
        Dict with keys:
            gross_r_mean (float), net_r_mean (float), cost_drag (float),
            cost_drag_pct (float), sample_count (int),
            has_sufficient_sample (bool), summary (str).
    """
    if not labels:
        return {
            "gross_r_mean": 0.0,
            "net_r_mean": 0.0,
            "cost_drag": 0.0,
            "cost_drag_pct": 0.0,
            "sample_count": 0,
            "has_sufficient_sample": False,
            "summary": "No label data available for cost analysis.",
        }

    gross_values: list[float] = []
    net_values: list[float] = []

    for label in labels:
        # Try gross_r or gross_r_multiple
        gross = _parse_numeric(label, "gross_r", None)  # type: ignore[arg-type]
        if gross is None or gross == 0.0:
            gross = _parse_numeric(label, "gross_r_multiple", 0.0)
        # Try net_r or net_r_multiple
        net = _parse_numeric(label, "net_r", None)  # type: ignore[arg-type]
        if net is None or net == 0.0:
            net = _parse_numeric(label, "net_r_multiple", 0.0)

        gross_values.append(gross)
        net_values.append(net)

    sample_count = len(gross_values)
    has_sufficient_sample = sample_count >= 100

    gross_r_mean = sum(gross_values) / sample_count if sample_count > 0 else 0.0
    net_r_mean = sum(net_values) / sample_count if sample_count > 0 else 0.0
    cost_drag = gross_r_mean - net_r_mean

    if abs(gross_r_mean) > 1e-10:
        cost_drag_pct = round((cost_drag / abs(gross_r_mean)) * 100.0, 1)
    else:
        cost_drag_pct = 0.0

    if sample_count == 0:
        summary = "No label data available for cost analysis."
    elif not has_sufficient_sample:
        summary = (
            f"Insufficient sample ({sample_count} labels) for reliable cost "
            f"analysis. Minimum 100 labels required. Observed cost drag: "
            f"{cost_drag:.4f} (gross R mean {gross_r_mean:.4f}, net R mean "
            f"{net_r_mean:.4f})."
        )
    else:
        summary = (
            f"Cost impact analysis over {sample_count} labels: gross R mean "
            f"{gross_r_mean:.4f}, net R mean {net_r_mean:.4f}, cost drag "
            f"{cost_drag:.4f} ({cost_drag_pct}% of gross edge). "
            f"Sample is {'sufficient' if has_sufficient_sample else 'insufficient'} "
            f"for statistical reliability."
        )

    return {
        "gross_r_mean": round(gross_r_mean, 4),
        "net_r_mean": round(net_r_mean, 4),
        "cost_drag": round(cost_drag, 4),
        "cost_drag_pct": cost_drag_pct,
        "sample_count": sample_count,
        "has_sufficient_sample": has_sufficient_sample,
        "summary": summary,
    }


# ---------------------------------------------------------------------------
# WS-05-COST-MHT: mht_hold_summary
# ---------------------------------------------------------------------------


def mht_hold_summary(
    tested_hypothesis_count: int,
    correction_method: str = "NONE_APPLIED",
) -> dict:
    """Produce MHT hold summary for non-ML phase.

    When correction_method is NONE_APPLIED (the default for non-ML
    research phase), returns a blocking hold. The hold can only be
    lifted by running model training with proper MHT correction.

    Args:
        tested_hypothesis_count: Number of hypotheses tested.
        correction_method: MHT correction method. Default NONE_APPLIED.

    Returns:
        Dict with keys:
            correction_method (str), corrected_significance (float|null),
            hold_active (bool), hold_reason (str),
            requires_model_training (bool), tested_hypothesis_count (int),
            notes (str).
    """
    if correction_method == "NONE_APPLIED":
        hold_reason = (
            f"MHT correction requires model training which is not performed "
            f"in this non-ML research phase. {tested_hypothesis_count} "
            f"hypotheses were tested without multiple comparison correction. "
            f"Data-snooping risk is elevated. The hold will remain active "
            f"until a proper MHT correction (Bonferroni, Holm-Bonferroni, "
            f"Benjamini-Hochberg, DeflatedSharpeRatio, or PBO) is applied "
            f"to trained model outputs."
        )
        notes = (
            f"To lift this MHT hold, the following training artifacts are "
            f"required: (1) trained model(s) with recorded hyperparameter "
            f"search space, (2) walk-forward OOS predictions across all "
            f"folds, (3) per-fold performance metrics, (4) application of "
            f"a vetted MHT correction method to the aggregate results, "
            f"(5) Deflated Sharpe Ratio or PBO assessment for the final "
            f"candidate. Until these artifacts are produced and validated, "
            f"no edge or profitability claims may be made. This is a "
            f"BLOCKING hold — reports with NONE_APPLIED MHT cannot carry "
            f"CANDIDATE_FOR_V7_GATES verdict."
        )
        return {
            "correction_method": "NONE_APPLIED",
            "corrected_significance": None,
            "hold_active": True,
            "hold_reason": hold_reason,
            "requires_model_training": True,
            "tested_hypothesis_count": tested_hypothesis_count,
            "notes": notes,
        }
    else:
        return {
            "correction_method": correction_method,
            "corrected_significance": None,
            "hold_active": False,
            "hold_reason": f"MHT correction applied: {correction_method}.",
            "requires_model_training": False,
            "tested_hypothesis_count": tested_hypothesis_count,
            "notes": "MHT correction applied — hold lifted.",
        }


# ---------------------------------------------------------------------------
# WS-05-COST-MHT: assemble_non_ml_research_context
# ---------------------------------------------------------------------------


def assemble_non_ml_research_context(labels: list[dict], mode: str) -> dict:
    """Aggregate all non-ML analysis into a single context dict.

    This is the P0.9A extension point consumed by builders.py.
    Aggregates label_distribution, no_trade_quality, cost_impact,
    and mht_hold into one context.

    Args:
        labels: List of AlphaForgeLabel dicts.
        mode: Mode identifier.

    Returns:
        Dict with keys:
            label_distribution (dict),
            no_trade_quality (dict),
            cost_impact (dict),
            mht_hold (dict).
    """
    label_dist = analyze_label_distribution(labels, mode)
    no_trade = analyze_no_trade_quality(labels, mode)
    cost = cost_impact_summary(labels, mode)

    # MHT hold: count tested hypotheses from label distribution
    tested_count = label_dist["total_count"] if label_dist["total_count"] > 0 else 0
    mht = mht_hold_summary(tested_count, "NONE_APPLIED")

    return {
        "label_distribution": label_dist,
        "no_trade_quality": no_trade,
        "cost_impact": cost,
        "mht_hold": mht,
    }
