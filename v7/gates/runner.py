"""
Automated gate runner — orchestrates G0-G10 evaluation with configurable
filtering, stop-on-fail, and structured JSON report output.

Usage:
    from v7.gates.runner import run_gates, to_json_report, write_report
    from v7.gates.config import DEFAULT_GATE_CONFIG

    results = run_gates(candidate, context, config=DEFAULT_GATE_CONFIG)
    report = to_json_report(results)
    write_report(results, "reports/gate-report.json")
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from v7.gates.config import GateConfig, resolve_gate_configs
from v7.gates.evaluator import (
    GATE_DEFINITIONS,
    GateResult,
    GateStatus,
    evaluate_candidate,
    get_promotion_summary,
)


def run_gates(
    candidate: dict[str, Any],
    context: dict[str, Any] | None = None,
    *,
    config: list[GateConfig] | None = None,
    candidate_label: str | None = None,
) -> dict[str, Any]:
    """Run configured gates against a candidate and produce a full report.

    Args:
        candidate:      The candidate dict (mode, symbol, model_scope, etc.).
        context:        Evaluation context dict (backtest metrics, regime data, etc.).
        config:         Optional gate configuration list. Uses DEFAULT_GATE_CONFIG
                        if not provided. Only enabled gates are evaluated.
        candidate_label: Optional human-readable label for the candidate (e.g. "swing_v1@abc123").

    Returns:
        A dict with keys:
            meta:           Metadata (candidate_id, label, timestamp, config_summary)
            gate_results:   Dict of gate_id -> GateResult (as dict)
            summary:        Promotion summary (passed, score, recommendation, etc.)
            passed:         Overall pass/fail (bool)

    Raises:
        ValueError: If candidate is missing required fields.
    """
    resolved_config = resolve_gate_configs(config)
    ctx = context or {}

    # Extract a candidate identifier
    candidate_id = candidate.get("request_id") or candidate.get("id", "unknown")

    # Build config summary
    enabled_gates = [c.gate_id for c in resolved_config if c.enabled]
    stop_on_fail_gates = [c.gate_id for c in resolved_config if c.stop_on_fail]

    # Filter to only enabled gates
    enabled_set = set(enabled_gates)

    # Use evaluate_candidate with stop_on_fail if any gate has it enabled
    # (the overall stop_on_fail is True if the first enabled gate has stop_on_fail)
    overall_stop_on_fail = any(c.stop_on_fail for c in resolved_config if c.enabled)

    raw_results = evaluate_candidate(candidate, ctx, stop_on_fail=overall_stop_on_fail)

    # Filter to only enabled gates, preserving G0-G10 order
    results: dict[str, GateResult] = {}
    for gate_id, _name, _fn in GATE_DEFINITIONS:
        if gate_id in enabled_set and gate_id in raw_results:
            results[gate_id] = raw_results[gate_id]

    summary = get_promotion_summary(results)

    # Serialize GateResults to dict
    gate_results_dict: dict[str, dict[str, Any]] = {}
    for gate_id, result in results.items():
        gate_results_dict[gate_id] = {
            "gate_id": result.gate_id,
            "name": result.name,
            "status": result.status.value,
            "score": result.score,
            "threshold": result.threshold,
            "detail": result.detail,
        }

    meta = {
        "candidate_id": candidate_id,
        "candidate_label": candidate_label or candidate.get("model_scope", ""),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mode": candidate.get("mode", "unknown"),
        "symbol": candidate.get("symbol", "unknown"),
        "config_summary": {
            "enabled_gates": enabled_gates,
            "stop_on_fail_gates": stop_on_fail_gates,
            "total_enabled": len(enabled_gates),
        },
    }

    return {
        "meta": meta,
        "gate_results": gate_results_dict,
        "summary": summary,
        "passed": summary["passed"],
    }


def to_json_report(results: dict[str, Any]) -> dict[str, Any]:
    """Convert a run_gates results dict to a structured JSON report dict.

    Args:
        results: The dict returned by run_gates().

    Returns:
        A JSON-serializable dict ready for write_report().
    """
    # Ensure all values are JSON-safe
    report: dict[str, Any] = {
        "report_version": "1.0.0",
        "report_type": "gate_evaluation",
        **results,
    }

    # Add a pass/fail summary at the top for quick scanning
    report["passed"] = results.get("passed", False)
    report["recommendation"] = results.get("summary", {}).get("recommendation", "UNKNOWN")

    return report


def write_report(results: dict[str, Any], path: str) -> str:
    """Write a gate evaluation report to a JSON file.

    Args:
        results: The results dict from run_gates() or to_json_report().
        path:    Filesystem path to write the JSON report.

    Returns:
        The absolute path to the written report file.

    Raises:
        OSError: If the file cannot be written (e.g. directory not found).
    """
    import os

    # Convert to JSON report if not already
    if "report_version" not in results:
        results = to_json_report(results)

    # Ensure the output directory exists
    out_dir = os.path.dirname(path)
    if out_dir and not os.path.exists(out_dir):
        os.makedirs(out_dir, exist_ok=True)

    with open(path, "w") as f:
        json.dump(results, f, indent=2, default=str)

    return os.path.abspath(path)
