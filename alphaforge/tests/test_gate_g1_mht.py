"""Test G1 gate PBO/Deflated-Sharpe guard.

P0.9F: _gate_g1 must:
- PASS when PBO in (LOW, MEDIUM) AND deflated_sharpe > 0 AND mht_computed_for_real=True
- PENDING when PBO is HIGH/CRITICAL/NOT_RUN regardless of other values
- PENDING when mht_computed_for_real=False (fail-closed on fallback identity)
"""

import pytest

from alphaforge.handoff.builders import _gate_g1


def _make_mrr(
    verdict: str = "CANDIDATE_FOR_V7_GATES",
    oos_r: float = 0.15,
    pbo_risk: str = "LOW",
    deflated_sharpe: float | None = 0.5,
    mht_real: bool = True,
) -> dict:
    """Build a minimal ModeResearchReport dict with MHT controls."""
    return {
        "report_id": "test-mrr-001",
        "verdict": verdict,
        "metrics": {
            "oos_expectancy_r": {"value": oos_r},
            "oos_sharpe": {"value": 0.5},
            "oos_trade_count": 200,
        },
        "multiple_hypothesis_control": {
            "pbo_or_backtest_overfit_risk": pbo_risk,
            "deflated_sharpe_or_equivalent": deflated_sharpe,
            "mht_computed_for_real": mht_real,
        },
    }


class TestGateG1PboDeflatedSharpe:
    """Tests for P0.9F G1 gate strengthening."""

    def test_pass_low_pbo_positive_ds(self):
        """Low PBO + positive deflated Sharpe + real MHT → PASS."""
        _, status = _gate_g1(_make_mrr(pbo_risk="LOW", deflated_sharpe=0.5))
        assert status == "PASS"

    def test_pass_medium_pbo_positive_ds(self):
        """Medium PBO + positive deflated Sharpe + real MHT → PASS."""
        _, status = _gate_g1(_make_mrr(pbo_risk="MEDIUM", deflated_sharpe=0.3))
        assert status == "PASS"

    def test_pending_high_pbo(self):
        """High PBO → PENDING regardless of other values."""
        _, status = _gate_g1(_make_mrr(pbo_risk="HIGH", deflated_sharpe=0.5))
        assert status == "PENDING"

    def test_pending_critical_pbo(self):
        """Critical PBO → PENDING."""
        _, status = _gate_g1(_make_mrr(pbo_risk="CRITICAL", deflated_sharpe=0.5))
        assert status == "PENDING"

    def test_pending_not_run_pbo(self):
        """NOT_RUN PBO → PENDING."""
        _, status = _gate_g1(_make_mrr(pbo_risk="NOT_RUN", deflated_sharpe=0.5))
        assert status == "PENDING"

    def test_pending_negative_deflated_sharpe(self):
        """Negative deflated Sharpe → PENDING even with LOW PBO."""
        _, status = _gate_g1(_make_mrr(pbo_risk="LOW", deflated_sharpe=-0.1))
        assert status == "PENDING"

    def test_pending_null_deflated_sharpe(self):
        """None deflated Sharpe → PENDING."""
        _, status = _gate_g1(_make_mrr(pbo_risk="LOW", deflated_sharpe=None))
        assert status == "PENDING"

    def test_fail_closed_no_real_mht(self):
        """mht_computed_for_real=False → PENDING regardless of PBO or DS values.
        This is the fail-closed behavior: when _MHT_AVAILABLE triggers the
        identity fallback, the gate must NOT pass."""
        _, status = _gate_g1(_make_mrr(
            pbo_risk="LOW", deflated_sharpe=0.5, mht_real=False,
        ))
        assert status == "PENDING"

    def test_pending_bad_verdict(self):
        """Bad verdict → PENDING even with good MHT."""
        _, status = _gate_g1(_make_mrr(verdict="REJECT"))
        assert status == "PENDING"

    def test_pending_inconclusive_verdict(self):
        _, status = _gate_g1(_make_mrr(verdict="BLOCKED_FOR_MHT"))
        assert status == "PENDING"

    def test_evidence_string_includes_mht_fields(self):
        """Evidence string must reference PBO, deflated Sharpe, and mht_real."""
        evidence, _ = _gate_g1(_make_mrr())
        assert "pbo_risk=LOW" in evidence
        assert "deflated_sharpe=0.5" in evidence
        assert "mht_computed_for_real=True" in evidence
