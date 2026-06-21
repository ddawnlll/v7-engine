"""P0.9A — AlphaForge report builder tests.

Verifies ModeResearchReport and AlphaForgeResearchReport builders
produce schema-valid placeholder payloads.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
AF_SRC = REPO / "alphaforge" / "src"
if str(AF_SRC) not in sys.path:
    sys.path.insert(0, str(AF_SRC))
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import pytest
from alphaforge.reports.builders import (
    build_mode_research_report,
    build_alphaforge_research_report,
)
from alphaforge.reports.writer import write_json_report
from alphaforge.contracts.loader import load_schema
from alphaforge.contracts.validator import validate_payload
from alphaforge.errors import ModeError, ReportBuildError


# ── Mode research reports ───────────────────────────────────────────────

def test_build_scalp_report_validates():
    report = build_mode_research_report("SCALP")
    assert report["mode"] == "SCALP"
    assert report["mode_priority"] == "PRIMARY"
    assert report["report_type"] == "primary_research_report"
    assert report["data_scope"]["primary_timeframes"] == ["1h"]
    assert report["data_scope"]["secondary_timeframes"] == ["4h", "15m"]
    assert report["verdict"] == "CONTINUE_RESEARCH"
    assert "cost_stress_verdict" in report["cost_stress"]
    assert "trade_vs_no_trade_verdict" in report["no_trade_comparison"]
    assert "regimes_tested" in report["regime_breakdown"]
    assert "v7_gate_readiness" in report
    assert "multiple_hypothesis_control" in report


def test_build_aggressive_scalp_report_validates():
    report = build_mode_research_report("AGGRESSIVE_SCALP")
    assert report["mode"] == "AGGRESSIVE_SCALP"
    assert report["mode_priority"] == "PRIMARY"
    assert report["report_type"] == "primary_research_report"
    assert report["data_scope"]["primary_timeframes"] == ["15m"]
    assert report["data_scope"]["secondary_timeframes"] == ["1h", "5m"]
    assert report["verdict"] == "CONTINUE_RESEARCH"


def test_build_swing_report_validates():
    report = build_mode_research_report("SWING")
    assert report["mode"] == "SWING"
    assert report["mode_priority"] == "SECONDARY_BASELINE"
    assert report["report_type"] == "secondary_baseline_report"
    assert report["data_scope"]["primary_timeframes"] == ["4h"]
    assert report["data_scope"]["secondary_timeframes"] == ["1d", "1h"]
    assert report["verdict"] == "BASELINE_WEAK"


def test_build_unknown_mode_raises():
    with pytest.raises(ModeError):
        build_mode_research_report("INVALID_MODE")


def test_build_report_no_fake_profitability():
    """Reports must not claim real profitability."""
    for mode in ["SCALP", "AGGRESSIVE_SCALP", "SWING"]:
        report = build_mode_research_report(mode)
        # Check that verdict is not a promotion-level verdict
        assert report["verdict"] in (
            "CONTINUE_RESEARCH", "REJECT", "CANDIDATE_FOR_V7_GATES",
            "BASELINE_WEAK", "BASELINE_VALID",
        )
        # Metrics must be zero/dummy
        assert report["metrics"]["oos_expectancy_r"]["value"] == 0.0
        # Scopes must mention HOLD or DEFERRED
        scopes_text = " ".join(report["blocked_scopes"]).lower()
        assert "hold" in scopes_text or "deferred" in scopes_text or "scaffold" in scopes_text


# ── AlphaForge aggregate report ─────────────────────────────────────────

def test_build_aggregate_report_validates():
    report = build_alphaforge_research_report()
    modes = {r["mode"] for r in report["mode_reports"]}
    assert modes == {"SCALP", "AGGRESSIVE_SCALP", "SWING"}
    assert len(report["mode_reports"]) == 3
    assert report["promoted_candidates"] == []
    assert len(report["rejected_candidates"]) >= 1


def test_build_aggregate_report_requires_all_three():
    """Passing only 2 modes must raise ReportBuildError."""
    with pytest.raises(ReportBuildError):
        build_alphaforge_research_report(mode_reports=[
            build_mode_research_report("SCALP"),
            build_mode_research_report("SWING"),
        ])


def test_build_aggregate_report_priority_correct():
    report = build_alphaforge_research_report()
    for r in report["mode_reports"]:
        if r["mode"] in ("SCALP", "AGGRESSIVE_SCALP"):
            assert r["mode_priority"] == "PRIMARY"
            assert r["report_type"] == "primary_research_report"
        else:
            assert r["mode_priority"] == "SECONDARY_BASELINE"
            assert r["report_type"] == "secondary_baseline_report"


# ── Report writer ───────────────────────────────────────────────────────

def test_write_json_report_to_tempdir(tmp_path):
    report = build_mode_research_report("SWING")
    out = tmp_path / "swing_report.json"
    schema = load_schema("mode_research_report.schema.json")
    written = write_json_report(report, out, schema=schema, schema_name="mode_research_report")
    assert written.exists()
    # Re-read and validate
    import json
    with open(written) as f:
        reloaded = json.load(f)
    assert reloaded["mode"] == "SWING"
    result = validate_payload(schema, reloaded, "reloaded")
    assert result.valid, f"Reloaded report failed validation: {result.errors}"


def test_write_json_report_creates_parent_dirs(tmp_path):
    report = build_mode_research_report("SWING")
    out = tmp_path / "nested" / "dir" / "report.json"
    schema = load_schema("mode_research_report.schema.json")
    written = write_json_report(report, out, schema=schema)
    assert written.exists()


def test_write_json_report_rejects_invalid_payload(tmp_path):
    schema = {"type": "object", "required": ["x"], "properties": {"x": {"type": "string"}}}
    payload = {}
    from alphaforge.errors import ContractValidationError
    with pytest.raises(ContractValidationError):
        write_json_report(payload, tmp_path / "bad.json", schema=schema, schema_name="test")
