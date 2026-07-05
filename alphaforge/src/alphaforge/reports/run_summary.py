"""Centralized research run summary builder with report consistency validation.

Scans a directory for ``mode_research_report_*.json`` files, extracts
key fields, runs cross-report consistency checks, builds root-cause
analyses, and generates a consolidated summary JSON + Markdown report.

Usage::

    from alphaforge.reports.run_summary import ResearchRunSummary

    summary = ResearchRunSummary.build_run_summary(
        report_dir="data/reports/swing",
        output_path="data/reports/swing/research_run_summary.json",
    )

    # Access consistency issues
    for issue in summary["consistency_issues"]:
        print(issue["severity"], issue["check"], issue["message"])

    # Access root cause trees per report
    for rc in summary["root_cause_trees"]:
        print(rc["mode"], rc["primary_cause"])
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

from alphaforge.reports.collapse_detector import build_collapse_root_cause_tree

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REPORT_GLOB: str = "mode_research_report_*.json"

ROOT_CAUSE_KEYS: Tuple[str, ...] = (
    "feature_failure",
    "label_failure",
    "model_failure",
    "cost_failure",
    "no_trade_collapse",
    "mht_failure",
    "fold_instability",
    "symbol_instability",
)

CONSISTENCY_SEVERITY_ORDER: Dict[str, int] = {"ERROR": 0, "WARN": 1, "INFO": 2}

# Default report directories relative to repo root for auto-generate mode
REPORT_DIRS: Tuple[str, ...] = (
    "data/reports/models",
    "data/reports/reports",
    "data/reports/",
)

# Failure layer mapping — maps primary_cause to failure_layer
FAILURE_LAYER_MAP: Dict[str, str] = {
    "feature_failure": "feature",
    "model_failure": "model",
    "cost_failure": "cost",
    "no_trade_collapse": "decision",
    "mht_failure": "statistics",
    "fold_instability": "validation",
    "symbol_instability": "coverage",
    "NO_FAILURE": "none",
}

# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

ConsistencyIssue = Dict[str, str]  # {severity, check, message, report_id}


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------


def _safe_get(d: Any, *keys: str, default: Any = None) -> Any:
    """Traverse nested dict safely, returning *default* on missing keys."""
    for k in keys:
        if not isinstance(d, dict):
            return default
        d = d.get(k, {})
    return d if d != {} else default


def _resolve_symbol_count(report: dict) -> int:
    """Return the number of symbols in ``data_scope.symbols``."""
    symbols = _safe_get(report, "data_scope", "symbols", default=[])
    return len(symbols) if isinstance(symbols, list) else 0


def _resolve_trade_counts(report: dict) -> Dict[str, int]:
    """Sum long / short label counts across all folds.

    Returns ``{"long": ..., "short": ..., "active": ...}``.
    """
    per_fold = _safe_get(report, "metrics", "per_fold_metrics", default=[])
    total_long = 0
    total_short = 0

    for fold in per_fold:
        ld = fold.get("label_distribution", {})
        if isinstance(ld, dict):
            total_long += ld.get("LONG_NOW", 0)
            total_short += ld.get("SHORT_NOW", 0)

    return {"long": total_long, "short": total_short, "active": total_long + total_short}


def _resolve_mht_status(report: dict) -> Dict[str, Any]:
    """Extract multiple-hypothesis-testing metadata."""
    mht = report.get("multiple_hypothesis_control", {})
    return {
        "trial_count": mht.get("trial_count_disclosure", 0),
        "correction_method": mht.get("correction_method", "UNKNOWN"),
        "data_snooping_risk": mht.get("data_snooping_risk_flag", "UNKNOWN"),
        "tested_hypotheses": mht.get("tested_hypothesis_count", 0),
    }


def _diagnose_primary_cause(report: dict) -> Tuple[str, List[str]]:
    """Determine primary failure cause and secondary causes + evidence.

    Returns ``(primary_cause, secondary_causes)`` where
    *secondary_causes* may include both cause labels and evidence strings.
    """
    verdict = report.get("verdict", "UNKNOWN")
    if verdict != "REJECT":
        return ("NO_FAILURE", [])

    cost_verdict = _safe_get(report, "cost_stress", "cost_stress_verdict", default="")
    regimes = _safe_get(report, "regime_breakdown", "regimes", default=[])
    no_trade = _safe_get(report, "no_trade_comparison", "active_beats_no_trade", default=True)
    mht = report.get("multiple_hypothesis_control", {})
    fold_count = _safe_get(report, "validation_summary", "fold_count", default=1)
    test_hyp_count = mht.get("tested_hypothesis_count", 0)
    trial_count = mht.get("trial_count_disclosure", 0)
    trade_count = _safe_get(report, "metrics", "oos_trade_count", default=0)
    expectancy_r = _safe_get(report, "metrics", "oos_expectancy_r", "value", default=0.0)
    symbol_count = _resolve_symbol_count(report)
    blocked = report.get("blocked_scopes", [])

    evidence: List[str] = []
    causes: List[str] = []

    # Cost failure
    if "FAIL" in cost_verdict:
        causes.append("cost_failure")
        evidence.append(f"Cost stress verdict: {cost_verdict}")

    # No-trade collapse
    if not no_trade:
        causes.append("no_trade_collapse")
        evidence.append("Active does not beat no-trade baseline")

        # Enrich no-trade collapse with root cause from collapse detector
        # when no_trade_comparison has saved/missed counts
        nt_comp = report.get("no_trade_comparison", {})
        saved = nt_comp.get("saved_loss_count", 0)
        missed = nt_comp.get("missed_opportunity_count", 0)
        if saved > 0 or missed > 0:
            evidence.append(
                f"Counterfactual: {saved} losses saved, {missed} opportunities missed"
            )
        if saved > 0 and missed > 0:
            ratio = round(saved / missed, 2) if missed > 0 else "inf"
            evidence.append(f"saved/missed ratio: {ratio}")

    # Model failure (expectancy_r <= 0)
    if expectancy_r is not None and expectancy_r <= 0:
        causes.append("model_failure")
        evidence.append(f"OOS expectancy_r={expectancy_r}")

    # Fold instability
    if fold_count <= 1:
        causes.append("fold_instability")
        evidence.append(f"fold_count={fold_count}")

    # Symbol instability
    if any("single symbol" in b.lower() for b in blocked):
        causes.append("symbol_instability")
        evidence.append("Single symbol limitation flagged in blocked_scopes")

    # MHT failure
    if trial_count == 0 and test_hyp_count > 0:
        causes.append("mht_failure")
        evidence.append(
            f"tested_hypotheses={test_hyp_count} but trial_count_disclosure=0"
        )

    # Feature failure (no edge across symbols)
    if expectancy_r is not None and expectancy_r <= 0 and symbol_count > 0:
        if not any("cost" in c for c in causes):
            causes.append("feature_failure")
            evidence.append("Zero/negative expectancy across symbols")

    # Deduplicate while preserving insertion order
    seen: set = set()
    unique_causes: List[str] = []
    for c in causes:
        if c not in seen:
            seen.add(c)
            unique_causes.append(c)

    # First cause matching priority order wins as primary
    primary: str = "model_failure"
    for p in ROOT_CAUSE_KEYS:
        if p in unique_causes:
            primary = p
            break

    secondary = [c for c in unique_causes if c != primary]

    return (primary, secondary + evidence)


# ===================================================================
# Public class
# ===================================================================


class ResearchRunSummary:
    """Consolidated research run summary builder with consistency validation.

    Static methods only — no instance state.  Designed for one-shot
    batch analysis of mode research reports.
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @staticmethod
    def build_run_summary(
        report_dir: str | Path,
        output_path: str | Path | None = None,
    ) -> Dict[str, Any]:
        """Scan *report_dir* for mode research reports and build summary.

        Args:
            report_dir:
                Directory containing ``mode_research_report_*.json``
                files.  Subdirectories are **not** scanned recursively.
            output_path:
                If provided, the summary JSON is written here
                **and** a companion Markdown file (same stem, ``.md``
                extension) is created.

        Returns:
            Summary dict with these top-level keys:

            - ``metadata`` — run timestamp, source directory, report count
            - ``reports`` — list of extracted per-report fields
            - ``consistency_issues`` — list of issues from
              :meth:`validate_consistency`
            - ``root_cause_trees`` — per-report root-cause analyses
            - ``recommendations`` — list of next-step recommendations
            - ``aggregate`` — rollup counts (verdicts, modes, MHT, no-trade)
        """
        report_dir = Path(report_dir)
        if not report_dir.is_dir():
            raise NotADirectoryError(
                f"Report directory does not exist: {report_dir}"
            )

        # ---- 1. Scan and load reports --------------------------------
        report_files = sorted(report_dir.glob(REPORT_GLOB))
        if not report_files:
            logger.warning("No %s files found in %s", REPORT_GLOB, report_dir)
            return ResearchRunSummary._empty_summary(
                ResearchRunSummary._build_metadata(report_dir, 0, [])
            )

        raw_reports: List[dict] = []
        load_errors: List[str] = []
        for rf in report_files:
            try:
                with open(rf, "r", encoding="utf-8") as fh:
                    raw_reports.append(json.load(fh))
            except (json.JSONDecodeError, OSError) as exc:
                load_errors.append(f"{rf.name}: {exc}")
                logger.warning("Skipping unreadable report %s: %s", rf.name, exc)

        if not raw_reports:
            logger.error("No valid reports could be loaded from %s", report_dir)
            empty = ResearchRunSummary._empty_summary(
                ResearchRunSummary._build_metadata(report_dir, len(report_files), load_errors)
            )
            empty["consistency_issues"].append({
                "severity": "ERROR",
                "check": "load",
                "message": f"All {len(report_files)} report file(s) failed to parse",
                "report_id": "N/A",
            })
            return empty

        # ---- 2. Extract per-report fields ----------------------------
        extracted = [
            ResearchRunSummary._extract_report_fields(r) for r in raw_reports
        ]

        # ---- 3. Validate consistency ---------------------------------
        consistency_issues = ResearchRunSummary.validate_consistency(raw_reports)

        # ---- 4. Build root-cause trees -------------------------------
        root_trees = [
            ResearchRunSummary.build_root_cause_tree(r) for r in raw_reports
        ]

        # ---- 5. Generate recommendations -----------------------------
        recommendations = ResearchRunSummary._generate_recommendations(raw_reports)

        # ---- 6. Aggregate --------------------------------------------
        aggregate = ResearchRunSummary._aggregate(extracted)

        summary: Dict[str, Any] = {
            "metadata": ResearchRunSummary._build_metadata(
                report_dir, len(raw_reports), load_errors
            ),
            "reports": extracted,
            "consistency_issues": ResearchRunSummary._sorted_issues(consistency_issues),
            "root_cause_trees": root_trees,
            "recommendations": recommendations,
            "aggregate": aggregate,
            "trial_ledger": ResearchRunSummary.build_trial_ledger(raw_reports),
        }

        # ---- 7. Write outputs ----------------------------------------
        if output_path is not None:
            output = Path(output_path)
            output.parent.mkdir(parents=True, exist_ok=True)
            with open(output, "w", encoding="utf-8") as fh:
                json.dump(summary, fh, indent=2, ensure_ascii=False, default=str)
            logger.info("Wrote summary JSON to %s", output)

            md_path = output.with_suffix(".md")
            ResearchRunSummary.generate_summary_report(summary, md_path)

        return summary

    # ------------------------------------------------------------------
    # Consistency validation
    # ------------------------------------------------------------------

    @staticmethod
    def validate_consistency(reports: List[dict]) -> List[ConsistencyIssue]:
        """Run cross-report and per-report consistency checks.

        Checks performed:

        1. **report_id uniqueness** — error on duplicate IDs.
        2. **edge_only_in_rare_regime vs actual regimes** — if every
           regime has ``edge_present=false`` but the report claims edge
           is rare, flag ``CONTRADICTION`` (no edge exists anywhere, so
           it cannot be rare).
        3. **cost_stress verdict vs stress levels** — empty stress levels
           with a ``FAIL`` verdict is **correct** (the test wasn't
           properly run).  Empty levels with
           ``combined_stress_edge_survives`` set true is inconsistent.
        4. **Single symbol limitation text vs symbol count** — if the
           report covers multiple symbols but ``blocked_scopes`` still
           mentions a single-symbol limitation, flag ``STALE_TEXT``.
        5. **Active trade count = long + short** — verifies the
           arithmetic.
        6. **Verdict vs metric consistency** — a non-REJECT verdict
           should have metrics that support it.
        7. **no_trade_comparison vs verdict** — REJECT verdict with
           ``active_beats_no_trade=true`` is contradictory.

        Returns:
            List of issues, each with ``severity`` (``ERROR`` /
            ``WARN`` / ``INFO``), ``check``, ``message``, and
            ``report_id``.
        """
        issues: List[ConsistencyIssue] = []

        if not reports:
            return issues

        # ---- Check 1: report_id uniqueness ---------------------------
        ids = [r.get("report_id", "UNKNOWN") for r in reports]
        dupe_counts = {rid: cnt for rid, cnt in Counter(ids).items() if cnt > 1}
        for dup_id, count in dupe_counts.items():
            issues.append({
                "severity": "ERROR",
                "check": "report_id_uniqueness",
                "message": f"Duplicate report_id '{dup_id}' appears {count} times",
                "report_id": dup_id,
            })

        # ---- Per-report checks ---------------------------------------
        for report in reports:
            rid = report.get("report_id", "UNKNOWN")

            # ---- Check 2: edge_only_in_rare_regime vs regimes --------
            regime_breakdown = report.get("regime_breakdown", {})
            regimes = regime_breakdown.get("regimes", [])
            edge_only_rare = regime_breakdown.get("edge_only_in_rare_regime", False)

            if regimes and edge_only_rare:
                all_no_edge = all(
                    not r.get("edge_present", False) for r in regimes
                )
                if all_no_edge:
                    issues.append({
                        "severity": "ERROR",
                        "check": "edge_rare_regime_contradiction",
                        "message": (
                            f"All {len(regimes)} regimes have "
                            "edge_present=false but "
                            "edge_only_in_rare_regime=true — CONTRADICTION "
                            "(no edge exists in any regime, so it cannot "
                            "be rare)"
                        ),
                        "report_id": rid,
                    })

            # ---- Check 3: cost_stress vs stress levels ---------------
            cost = report.get("cost_stress", {})
            fee_levels = cost.get("fee_stress_levels", [])
            slip_levels = cost.get("slippage_stress_levels", [])
            cost_verdict = cost.get("cost_stress_verdict", "")
            combined_survives = cost.get("combined_stress_edge_survives", False)

            levels_empty = not fee_levels and not slip_levels

            # Empty levels + FAIL verdict = correct (test wasn't run)
            # No issue to emit.

            # Empty levels but combined_stress_edge_survives is set
            if levels_empty and combined_survives:
                issues.append({
                    "severity": "WARN",
                    "check": "cost_stress_levels_empty_edge_survives",
                    "message": (
                        "fee_stress_levels and slippage_stress_levels are "
                        "both empty, yet combined_stress_edge_survives is "
                        "set — inconsistent (no stress levels were tested)"
                    ),
                    "report_id": rid,
                })

            # ---- Check 4: single symbol limitation vs symbol count ---
            symbol_count = _resolve_symbol_count(report)
            blocked = report.get("blocked_scopes", [])
            single_sym_mention = any(
                "single symbol" in b.lower() for b in blocked
            )

            if symbol_count > 1 and single_sym_mention:
                issues.append({
                    "severity": "WARN",
                    "check": "stale_single_symbol_text",
                    "message": (
                        f"data_scope contains {symbol_count} symbols but "
                        "blocked_scopes still references a 'single symbol "
                        "limitation' — STALE_TEXT, should be updated"
                    ),
                    "report_id": rid,
                })

            # ---- Check 5: active trade count = long + short ----------
            trade_counts = _resolve_trade_counts(report)
            expected_active = trade_counts["long"] + trade_counts["short"]
            if trade_counts["active"] != expected_active:
                issues.append({
                    "severity": "ERROR",
                    "check": "trade_count_mismatch",
                    "message": (
                        f"active_trade_count ({trade_counts['active']}) != "
                        f"long ({trade_counts['long']}) + short "
                        f"({trade_counts['short']}) = {expected_active}"
                    ),
                    "report_id": rid,
                })

            # ---- Check 6: verdict vs metric consistency --------------
            verdict = report.get("verdict", "UNKNOWN")
            oos_sharpe = _safe_get(
                report, "metrics", "oos_sharpe", "value", default=None
            )
            oos_expectancy = _safe_get(
                report, "metrics", "oos_expectancy_r", "value", default=None
            )

            if verdict in ("PASS", "CONDITIONAL_PASS", "PROMOTE"):
                if oos_sharpe is not None and oos_sharpe <= 0:
                    issues.append({
                        "severity": "WARN",
                        "check": "verdict_metric_mismatch",
                        "message": (
                            f"Verdict is '{verdict}' but oos_sharpe="
                            f"{oos_sharpe} — metric does not support a "
                            "passing verdict"
                        ),
                        "report_id": rid,
                    })
                if oos_expectancy is not None and oos_expectancy <= 0:
                    issues.append({
                        "severity": "WARN",
                        "check": "verdict_metric_mismatch",
                        "message": (
                            f"Verdict is '{verdict}' but "
                            f"oos_expectancy_r={oos_expectancy} — metric "
                            "does not support a passing verdict"
                        ),
                        "report_id": rid,
                    })

            # ---- Check 7: no_trade vs verdict ------------------------
            no_trade = report.get("no_trade_comparison", {})
            active_beats = no_trade.get("active_beats_no_trade")
            if verdict == "REJECT" and active_beats is True:
                issues.append({
                    "severity": "WARN",
                    "check": "no_trade_contradiction",
                    "message": (
                        "Verdict is REJECT but no_trade_comparison says "
                        "active_beats_no_trade=true — contradictory"
                    ),
                    "report_id": rid,
                })

        return issues

    # ------------------------------------------------------------------
    # Root cause analysis
    # ------------------------------------------------------------------

    @staticmethod
    def build_root_cause_tree(report: dict) -> Dict[str, Any]:
        """Build a root-cause tree for a single report.

        Returns a dict with ``verdict``, ``mode``, ``report_id``, and
        ``root_cause_tree`` containing boolean flags for each failure
        mode, ``primary_cause``, ``secondary_causes``, and ``evidence``.
        """
        primary, secondary = _diagnose_primary_cause(report)

        # Build failure-mode boolean flags
        failure_flags: Dict[str, bool] = {
            k: (k == primary or k in secondary) for k in ROOT_CAUSE_KEYS
        }

        # Partition secondary into cause labels vs evidence strings
        secondary_causes = [s for s in secondary if s in ROOT_CAUSE_KEYS]
        evidence_list = [s for s in secondary if s not in ROOT_CAUSE_KEYS]

        return {
            "verdict": report.get("verdict", "UNKNOWN"),
            "mode": report.get("mode", "UNKNOWN"),
            "report_id": report.get("report_id", "UNKNOWN"),
            "root_cause_tree": {
                **failure_flags,
                "primary_cause": primary,
                "secondary_causes": secondary_causes,
                "evidence": evidence_list,
            },
        }

    # ------------------------------------------------------------------
    # Recommendations
    # ------------------------------------------------------------------

    @staticmethod
    def next_experiment_recommendation(report: dict) -> str:
        """Return a single next-step recommendation based on root cause.

        Root-cause to recommendation mapping:

        ===================  ===========================================
        Primary cause        Recommendation
        ===================  ===========================================
        ``cost_failure``     *Reduce stop_mult or increase target_mult,
                             re-run*
        ``fold_instability`` *Increase training data or reduce model
                             complexity*
        ``no_trade_collapse`` *Check label balance, reduce min_edge_r*
        ``mht_failure``      *Reduce grid search space or increase
                             samples*
        ``model_failure``    *Review feature engineering for better
                             signal extraction; increase data quality or
                             sample size*
        ``feature_failure``  *Add or transform features; explore non-
                             linear interactions; check for data leakage*
        ``symbol_instability`` *Expand symbol coverage; validate cross-
                             symbol robustness*
        ``label_failure``    *Review label construction methodology and
                             class balance*
        ===================  ===========================================
        """
        primary = _diagnose_primary_cause(report)[0]

        # For no_trade_collapse, enrich recommendation with
        # saved/missed counterfactual detail when available
        no_trade_detail = ""
        if primary == "no_trade_collapse":
            nt_comp = report.get("no_trade_comparison", {})
            saved = nt_comp.get("saved_loss_count", 0)
            missed = nt_comp.get("missed_opportunity_count", 0)
            if saved > 0 and missed > 0 and missed > saved:
                no_trade_detail = (
                    " Counterfactual shows more missed opportunities "
                    "than saved losses — reduce min_edge_r or relax "
                    "label threshold."
                )
            elif saved > 0 and missed > 0 and saved >= missed:
                no_trade_detail = (
                    " Counterfactual shows saved losses exceed missed "
                    "opportunities — model is correctly risk-averse, "
                    "but evaluate if over-cautious."
                )

        RECOMMENDATIONS: Dict[str, str] = {
            "cost_failure": "Reduce stop_mult or increase target_mult, re-run",
            "fold_instability": "Increase training data or reduce model complexity",
            "no_trade_collapse": f"Check label balance, reduce min_edge_r.{no_trade_detail}",
            "mht_failure": "Reduce grid search space or increase samples",
            "model_failure": (
                "Review feature engineering for better signal extraction; "
                "increase data quality or sample size"
            ),
            "feature_failure": (
                "Add or transform features; explore non-linear "
                "interactions; check for data leakage"
            ),
            "symbol_instability": (
                "Expand symbol coverage; validate cross-symbol robustness"
            ),
            "label_failure": (
                "Review label construction methodology and class balance"
            ),
        }

        return RECOMMENDATIONS.get(
            primary,
            "Run diagnostics: verify data pipeline and label construction",
        )

    # ------------------------------------------------------------------
    # Markdown summary report
    # ------------------------------------------------------------------

    @staticmethod
    def generate_summary_report(summary: dict, output_path: str | Path) -> Path:
        """Write a human-readable Markdown summary of the run.

        Args:
            summary: The dict returned by :meth:`build_run_summary`.
            output_path: Destination ``.md`` file path.

        Returns:
            Path to the written file.
        """
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)

        lines: List[str] = []
        meta = summary.get("metadata", {})
        agg = summary.get("aggregate", {})
        reports = summary.get("reports", [])
        issues = summary.get("consistency_issues", [])
        trees = summary.get("root_cause_trees", [])
        recs = summary.get("recommendations", [])

        # ---- Header ------------------------------------------------
        lines.append("# Research Run Summary\n")
        lines.append(f"- **Generated:** {meta.get('created_at', 'unknown')}")
        lines.append(
            f"- **Source directory:** `{meta.get('report_dir', 'unknown')}`"
        )
        lines.append(f"- **Reports found:** {meta.get('report_count', 0)}")
        load_errors = meta.get("load_errors", [])
        if load_errors:
            lines.append(f"- **Load errors:** {len(load_errors)}")
            for err in load_errors:
                lines.append(f"  - `{err}`")
        lines.append("")

        # ---- Aggregate ---------------------------------------------
        lines.append("## Aggregate\n")
        verdicts = agg.get("verdict_counts", {})
        if verdicts:
            lines.append("### Verdicts\n")
            for v, c in sorted(verdicts.items()):
                lines.append(f"- **{v}:** {c}")
            lines.append("")

        modes = agg.get("mode_counts", {})
        if modes:
            lines.append("### Modes\n")
            for m, c in sorted(modes.items()):
                lines.append(f"- **{m}:** {c}")
            lines.append("")

        lines.append(
            f"- **MHT high risk:** {agg.get('mht_high_risk_count', 0)}"
        )
        lines.append(
            f"- **No-trade failures (zero-trade reports):** "
            f"{agg.get('no_trade_fail_count', 0)}"
        )
        lines.append("")

        # ---- Consistency Issues ------------------------------------
        lines.append("## Consistency Issues\n")
        if issues:
            for issue in issues:
                tag = {"ERROR": "[E]", "WARN": "[W]", "INFO": "[I]"}.get(
                    issue.get("severity", ""), "[?]"
                )
                lines.append(
                    f"- {tag} **{issue['check']}** "
                    f"(report: `{issue.get('report_id', '?')}`): "
                    f"{issue['message']}"
                )
        else:
            lines.append("No consistency issues found.\n")
        lines.append("")

        # ---- Per-Report Detail -------------------------------------
        lines.append("## Reports\n")
        for i, rep in enumerate(reports):
            rid = rep.get("report_id", "?")
            mode = rep.get("mode", "?")
            verdict = rep.get("verdict", "?")
            lines.append(f"### {i + 1}. {rid} ({mode})\n")
            lines.append(f"- **Verdict:** {verdict}")
            lines.append(f"- **Fold count:** {rep.get('fold_count', '?')}")
            lines.append(
                f"- **OOS trade count:** {rep.get('oos_trade_count', '?')}"
            )
            lines.append(
                f"- **OOS Sharpe:** {rep.get('oos_sharpe', '?')}"
            )
            lines.append(
                f"- **OOS expectancy R:** "
                f"{rep.get('oos_expectancy_r', '?')}"
            )
            lines.append(
                f"- **MHT trial count:** {rep.get('trial_count', '?')}"
            )
            lines.append(
                f"- **MHT correction:** "
                f"{rep.get('correction_method', '?')}"
            )
            lines.append("")

            # Root cause for this report
            tree = trees[i] if i < len(trees) else {}
            rc = tree.get("root_cause_tree", {})
            if rc:
                lines.append("**Root cause analysis:**\n")
                lines.append(
                    f"- Primary cause: `{rc.get('primary_cause', '?')}`"
                )
                sec = rc.get("secondary_causes", [])
                if sec:
                    lines.append(
                        f"- Secondary causes: {', '.join(sec)}"
                    )
                ev = rc.get("evidence", [])
                if ev:
                    lines.append("- Evidence:")
                    for e in ev:
                        lines.append(f"  - {e}")
                lines.append("")

            # Recommendation for this report
            rec = (
                recs[i]
                if i < len(recs)
                else "No recommendation available"
            )
            lines.append(f"**Recommended next step:** {rec}\n")

        # ---- Recommendations (deduplicated) -------------------------
        lines.append("## Deduplicated Recommendations\n")
        if recs:
            for idx, rec in enumerate(recs, 1):
                lines.append(f"{idx}. {rec}")
        else:
            lines.append("No recommendations generated.\n")
        lines.append("")

        # ---- Footer ------------------------------------------------
        lines.append("---")
        lines.append(
            "_Generated by `ResearchRunSummary` from "
            "`alphaforge.reports.run_summary`._"
        )
        lines.append("")

        output.write_text("\n".join(lines), encoding="utf-8")
        logger.info("Wrote summary Markdown to %s", output)
        return output

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_metadata(
        report_dir: Path,
        report_count: int = 0,
        load_errors: List[str] | None = None,
    ) -> dict:
        return {
            "created_at": datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            ),
            "report_dir": str(report_dir.resolve()),
            "report_count": report_count,
            "load_errors": load_errors or [],
        }

    @staticmethod
    def _empty_summary(metadata: dict) -> Dict[str, Any]:
        return {
            "metadata": metadata,
            "reports": [],
            "consistency_issues": [],
            "root_cause_trees": [],
            "recommendations": [],
            "aggregate": {
                "verdict_counts": {},
                "mode_counts": {},
                "total_reports": 0,
                "mht_high_risk_count": 0,
                "no_trade_fail_count": 0,
            },
            "trial_ledger": {
                "total_candidates": 0,
                "promoted_count": 0,
                "rejected_count": 0,
                "research_count": 0,
                "candidates": [],
            },
        }

    @staticmethod
    def _extract_report_fields(report: dict) -> Dict[str, Any]:
        """Extract the canonical field set from a single report dict."""
        trade_counts = _resolve_trade_counts(report)
        mht = _resolve_mht_status(report)

        return {
            "report_id": report.get("report_id", "UNKNOWN"),
            "mode": report.get("mode", "UNKNOWN"),
            "mode_priority": report.get("mode_priority", "UNKNOWN"),
            "report_type": report.get("report_type", "UNKNOWN"),
            "created_at": report.get("created_at", "UNKNOWN"),
            "run_id": report.get("run_id", "UNKNOWN"),
            "verdict": report.get("verdict", "UNKNOWN"),
            "fold_count": _safe_get(
                report, "validation_summary", "fold_count", default=0
            ),
            "oos_trade_count": _safe_get(
                report, "metrics", "oos_trade_count", default=0
            ),
            "oos_sharpe": _safe_get(
                report, "metrics", "oos_sharpe", "value", default=None
            ),
            "oos_expectancy_r": _safe_get(
                report,
                "metrics",
                "oos_expectancy_r",
                "value",
                default=None,
            ),
            "long_trade_count": trade_counts["long"],
            "short_trade_count": trade_counts["short"],
            "active_trade_count": trade_counts["active"],
            "trial_count": mht["trial_count"],
            "correction_method": mht["correction_method"],
            "data_snooping_risk": mht["data_snooping_risk"],
            "tested_hypotheses": mht["tested_hypotheses"],
        }

    @staticmethod
    def _sorted_issues(
        issues: List[ConsistencyIssue],
    ) -> List[ConsistencyIssue]:
        """Sort issues by severity (ERROR first) then check name."""
        return sorted(
            issues,
            key=lambda x: (
                CONSISTENCY_SEVERITY_ORDER.get(
                    x.get("severity", "INFO"), 99
                ),
                x.get("check", ""),
            ),
        )

    @staticmethod
    def _aggregate(extracted: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Roll up verdict, mode, MHT, and no-trade counts."""
        verdict_counts: Dict[str, int] = {}
        mode_counts: Dict[str, int] = {}
        mht_high_risk = 0
        no_trade_fails = 0

        for rep in extracted:
            v = rep.get("verdict", "UNKNOWN")
            verdict_counts[v] = verdict_counts.get(v, 0) + 1

            m = rep.get("mode", "UNKNOWN")
            mode_counts[m] = mode_counts.get(m, 0) + 1

            if rep.get("data_snooping_risk") == "HIGH":
                mht_high_risk += 1

            if rep.get("oos_trade_count", 0) == 0:
                no_trade_fails += 1

        return {
            "verdict_counts": verdict_counts,
            "mode_counts": mode_counts,
            "total_reports": len(extracted),
            "mht_high_risk_count": mht_high_risk,
            "no_trade_fail_count": no_trade_fails,
        }

    @staticmethod
    def _generate_recommendations(reports: List[dict]) -> List[str]:
        """Collect unique next-step recommendations across all reports."""
        seen: set = set()
        recs: List[str] = []
        for report in reports:
            rec = ResearchRunSummary.next_experiment_recommendation(report)
            if rec not in seen:
                seen.add(rec)
                recs.append(rec)
        return recs

    # ------------------------------------------------------------------
    # Trial ledger
    # ------------------------------------------------------------------

    @staticmethod
    def build_trial_ledger(reports: List[dict]) -> Dict[str, Any]:
        """Build a trial ledger from a list of reports.

        Maps each report to a candidate entry with verdict, root cause,
        failure layer, and key metrics. Counts promoted / rejected /
        research candidates.

        Args:
            reports: List of report dicts.

        Returns:
            Dict with ``total_candidates``, ``promoted_count``,
            ``rejected_count``, ``research_count``, and ``candidates`` list.
        """
        PROMOTED_VERDICTS = {"CANDIDATE_FOR_V7_GATES", "BASELINE_VALID"}
        REJECTED_VERDICTS = {"REJECT"}
        RESEARCH_VERDICTS = {"CONTINUE_RESEARCH"}

        candidates: List[Dict[str, Any]] = []
        promoted = 0
        rejected = 0
        research = 0

        for rank, report in enumerate(reports, start=1):
            verdict = report.get("verdict", "UNKNOWN")
            tree = ResearchRunSummary.build_root_cause_tree(report)
            rc_tree = tree.get("root_cause_tree", {})
            primary_cause = rc_tree.get("primary_cause", "NO_FAILURE")

            is_promoted = verdict in PROMOTED_VERDICTS
            is_rejected = verdict in REJECTED_VERDICTS
            is_research = verdict in RESEARCH_VERDICTS

            if is_promoted:
                promoted += 1
            elif is_rejected:
                rejected += 1
            elif is_research:
                research += 1

            # Determine failure_layer from primary cause
            failure_layer = FAILURE_LAYER_MAP.get(primary_cause, "none")

            # Build evidence list from root cause tree + diagnostics
            evidence = list(rc_tree.get("evidence", []))

            # Extract key metrics
            oos_expectancy_r = _safe_get(
                report, "metrics", "oos_expectancy_r", "value", default=0.0
            )
            oos_sharpe = _safe_get(
                report, "metrics", "oos_sharpe", "value", default=0.0
            )
            oos_trade_count = _safe_get(
                report, "metrics", "oos_trade_count", default=0
            )

            candidate: Dict[str, Any] = {
                "rank": rank,
                "report_id": report.get("report_id", "UNKNOWN"),
                "verdict": verdict,
                "is_promoted": is_promoted,
                "is_rejected": is_rejected,
                "is_research": is_research,
                "primary_cause": primary_cause,
                "failure_layer": failure_layer,
                "evidence": evidence,
                "next_recommendation": (
                    ResearchRunSummary.next_experiment_recommendation(report)
                ),
                "oos_expectancy_r": oos_expectancy_r,
                "oos_sharpe": oos_sharpe,
                "oos_trade_count": oos_trade_count,
            }
            candidates.append(candidate)

        return {
            "total_candidates": len(candidates),
            "promoted_count": promoted,
            "rejected_count": rejected,
            "research_count": research,
            "candidates": candidates,
        }

    # ------------------------------------------------------------------
    # Auto-generate summary (multi-directory)
    # ------------------------------------------------------------------

    @staticmethod
    def auto_generate_summary(
        report_dirs: List[str | Path],
        output_path: str | Path,
    ) -> Dict[str, Any]:
        """Scan one or more report directories and produce a consolidated
        summary with trial ledger.

        Args:
            report_dirs: List of report directory paths to scan.
            output_path: Destination for the consolidated summary JSON.
                A companion Markdown file (same stem) is also written.

        Returns:
            Consolidated summary dict with merged reports, consistency
            issues, root cause trees, recommendations, aggregate, and
            trial ledger.
        """
        all_reports: List[dict] = []
        all_consistency_issues: List[ConsistencyIssue] = []
        all_root_trees: List[dict] = []
        all_recommendations: List[str] = []

        for d in report_dirs:
            p = Path(d)
            if not p.is_dir():
                logger.warning("Report directory does not exist: %s", p)
                continue

            try:
                summary = ResearchRunSummary.build_run_summary(
                    report_dir=p, output_path=None
                )
                all_reports.extend(summary.get("reports", []))
                all_consistency_issues.extend(
                    summary.get("consistency_issues", [])
                )
                all_root_trees.extend(summary.get("root_cause_trees", []))
                all_recommendations.extend(
                    summary.get("recommendations", [])
                )
            except Exception as exc:
                logger.error("Failed to process %s: %s", p, exc)
                continue

        # De-duplicate recommendations while preserving order
        seen_recs: set = set()
        deduped_recs: List[str] = []
        for rec in all_recommendations:
            if rec not in seen_recs:
                seen_recs.add(rec)
                deduped_recs.append(rec)

        # Build trial ledger from raw reports (we need to load them again)
        # Use build_run_summary outputs — we already have the loaded reports
        # from the scan. Re-load from disk to get the raw report dicts.
        raw_reports: List[dict] = []
        for d in report_dirs:
            p = Path(d)
            if not p.is_dir():
                continue
            for rf in sorted(p.glob(REPORT_GLOB)):
                try:
                    with open(rf, "r", encoding="utf-8") as fh:
                        raw_reports.append(json.load(fh))
                except (json.JSONDecodeError, OSError):
                    continue

        trial_ledger = ResearchRunSummary.build_trial_ledger(raw_reports)

        # Build aggregate from extracted report fields
        aggregate = ResearchRunSummary._aggregate(
            [ResearchRunSummary._extract_report_fields(r) for r in raw_reports]
        )

        merged: Dict[str, Any] = {
            "metadata": {
                "created_at": datetime.now(timezone.utc).strftime(
                    "%Y-%m-%dT%H:%M:%SZ"
                ),
                "report_dirs": [str(Path(d).resolve()) for d in report_dirs],
                "report_count": len(all_reports),
                "source_count": len(report_dirs),
            },
            "reports": all_reports,
            "consistency_issues": ResearchRunSummary._sorted_issues(
                all_consistency_issues
            ),
            "root_cause_trees": all_root_trees,
            "recommendations": deduped_recs,
            "aggregate": aggregate,
            "trial_ledger": trial_ledger,
        }

        # Write output
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        with open(output, "w", encoding="utf-8") as fh:
            json.dump(merged, fh, indent=2, ensure_ascii=False, default=str)
        logger.info("Wrote auto-generated summary JSON to %s", output)

        md_path = output.with_suffix(".md")
        ResearchRunSummary.generate_summary_report(merged, md_path)

        return merged
