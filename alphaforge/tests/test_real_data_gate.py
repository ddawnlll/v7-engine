"""
Tests for RealDataGate --- claim-level real-data provenance gating.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import os
import tempfile

import pytest

pytestmark = pytest.mark.integration

from lib.evidence_engine.hard_caps import (
    REAL_DATA_REQUIRED_CLAIMS,
    RealDataGate,
    RealDataGateResult as GateResult,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_passport(is_real_data=True, checksum_pass=True):
    """Build a minimal DataPassport-like object for testing."""
    passport = MagicMock()
    passport.is_real_data = is_real_data
    passport.source = "binance" if is_real_data else "custom"
    passport.is_trustworthy_for_context.return_value = is_real_data and checksum_pass
    return passport


# ---------------------------------------------------------------------------
# GateResult
# ---------------------------------------------------------------------------


class TestGateResult:
    """GateResult dataclass defaults."""

    def test_defaults(self):
        """Default GateResult is passing."""
        r = GateResult(passed=True)
        assert r.passed is True
        assert r.max_alpha_score == 100
        assert r.alpha_candidate is True
        assert r.reason == ""

    def test_failure(self):
        """Failure sets score cap and alpha_candidate."""
        r = GateResult(
            passed=False,
            max_alpha_score=15,
            alpha_candidate=False,
            reason="no real data",
        )
        assert r.passed is False
        assert r.max_alpha_score == 15
        assert r.alpha_candidate is False
        assert r.reason == "no real data"


# ---------------------------------------------------------------------------
# REAL_DATA_REQUIRED_CLAIMS
# ---------------------------------------------------------------------------


class TestRealDataRequiredClaims:
    """The claim constants."""

    def test_set_contains_expected_claims(self):
        """All expected claim types are present."""
        expected = {
            "ALPHA_HAS_EDGE",
            "MODEL_BEATS_BASELINES",
            "FEATURE_FAMILY_HAS_SIGNAL",
            "V7_RESEARCH_BACKTEST_READY",
            "V7_WALK_FORWARD_READY",
            "V7_PROMOTION_CANDIDATE",
        }
        assert REAL_DATA_REQUIRED_CLAIMS == expected


# ---------------------------------------------------------------------------
# RealDataGate.evaluate
# ---------------------------------------------------------------------------


class TestRealDataGateEvaluate:
    """RealDataGate.evaluate behavior."""

    def setup_method(self):
        self.gate = RealDataGate()

    # -- Unchecked claims ------------------------------------------------

    @pytest.mark.parametrize("claim", [
        "COST_AWARE_FILTER_IMPROVES_NET_R",
        "HARD_CAPS_BLOCKED",
        "V7_COST_STRESS_READY",
        "V7_SHADOW_READY",
        "UNKNOWN_CLAIM",
    ])
    def test_unchecked_claims_pass(self, claim):
        """Claims not in REAL_DATA_REQUIRED_CLAIMS always pass."""
        result = self.gate.evaluate(claim, passport=None)
        assert result.passed is True
        assert result.max_alpha_score == 100
        assert result.alpha_candidate is True

    # -- No passport -----------------------------------------------------

    @pytest.mark.parametrize("claim", list(REAL_DATA_REQUIRED_CLAIMS))
    def test_no_passport_fails(self, claim):
        """Required claims fail when no passport is provided."""
        result = self.gate.evaluate(claim, passport=None)
        assert result.passed is False
        assert result.max_alpha_score == 15
        assert result.alpha_candidate is False
        assert "no DataPassport was provided" in result.reason

    # -- Not real data ---------------------------------------------------

    @pytest.mark.parametrize("claim", list(REAL_DATA_REQUIRED_CLAIMS))
    def test_not_real_data_fails(self, claim):
        """Required claims fail when passport has is_real_data=False."""
        passport = _make_passport(is_real_data=False)
        result = self.gate.evaluate(claim, passport=passport)
        assert result.passed is False
        assert result.max_alpha_score == 15
        assert result.alpha_candidate is False
        assert "does not provide real data" in result.reason

    # -- Not trustworthy for context -------------------------------------

    @pytest.mark.parametrize("claim", list(REAL_DATA_REQUIRED_CLAIMS))
    def test_not_trustworthy_fails(self, claim):
        """Required claims fail when passport fails context trust."""
        passport = _make_passport(is_real_data=True, checksum_pass=False)
        result = self.gate.evaluate(claim, passport=passport)
        assert result.passed is False
        assert result.max_alpha_score == 15
        assert result.alpha_candidate is False
        assert "not trustworthy" in result.reason

    # -- Passing cases ---------------------------------------------------

    @pytest.mark.parametrize("claim", list(REAL_DATA_REQUIRED_CLAIMS))
    def test_passes_with_valid_passport(self, claim):
        """Required claims pass with a valid, trustworthy passport."""
        passport = _make_passport(is_real_data=True, checksum_pass=True)
        result = self.gate.evaluate(claim, passport=passport)
        assert result.passed is True
        assert result.max_alpha_score == 100
        assert result.alpha_candidate is True
        assert result.reason == ""


# ---------------------------------------------------------------------------
# Integration with DataPassport
# ---------------------------------------------------------------------------


class TestWithRealDataPassport:
    """RealDataGate evaluated against a real DataPassport."""

    def test_with_real_data_passport(self):
        """A real binance passport satisfies the gate."""
        from lib.data_lake.passport import DataPassport
        from lib.data_lake.spec import DatasetSpec
        from lib.data_lake.catalog import DataCatalog

        spec = DatasetSpec(
            dataset_id="int-test-001",
            source="binance",
            market="um_futures",
            symbols=("BTCUSDT",),
            intervals=("1h",),
            data_types=("klines",),
            start=datetime(2022, 1, 1, tzinfo=timezone.utc),
            end=datetime(2022, 1, 3, tzinfo=timezone.utc),
        )
        cat = DataCatalog(catalog_path=os.path.join(tempfile.mkdtemp(), "int_catalog.json"))
        cat.add_entry(
            symbol="BTCUSDT",
            interval="1h",
            start_ts=int(spec.start.timestamp() * 1000),
            end_ts=int(spec.end.timestamp() * 1000),
            row_count=100,
            checksum="dummysum",
        )
        from lib.data_lake.checksum import ChecksumReport
        cr = ChecksumReport(
            total_files=1, files_checked=1, files_passed=1,
            algorithm="sha256",
            generated_at=datetime.now(timezone.utc).isoformat(),
        )
        dp = DataPassport.from_spec(spec, cat, checksum_report=cr)

        gate = RealDataGate()
        result = gate.evaluate("ALPHA_HAS_EDGE", passport=dp)
        assert result.passed is True


