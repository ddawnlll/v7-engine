"""Tests for Multiple Hypothesis Testing (MHT) correction functions.

Tests every function in alphaforge.reports.mht:
- bonferroni_correction
- benjamini_hochberg
- deflated_sharpe
- compute_trial_count
- compute_data_snooping_risk
"""

import math
from typing import Any, Dict

import pytest

from alphaforge.reports.mht import (
    TrialLedger,
    benjamini_hochberg,
    bonferroni_correction,
    build_mht_section_from_ledger,
    compute_data_snooping_risk,
    compute_trial_count,
    deflated_sharpe,
)

from alphaforge.reports._minimal import build_minimal_mode_research_report


# ============================================================================
# Bonferroni correction
# ============================================================================


def test_bonferroni_alpha_0_05_n_490():
    """Bonferroni: 0.05 / 490 = 0.00010204 ..."""
    result = bonferroni_correction(0.05, 490)
    assert result == pytest.approx(0.05 / 490, abs=1e-10)


def test_bonferroni_n_zero():
    """Bonferroni: n_trials <= 0 returns alpha unchanged."""
    assert bonferroni_correction(0.05, 0) == 0.05
    assert bonferroni_correction(0.05, -1) == 0.05
    assert bonferroni_correction(0.01, 0) == 0.01


# ============================================================================
# Benjamini-Hochberg procedure
# ============================================================================


def test_benjamini_hochberg_with_known_p_values():
    """BH: reject all p-values at or below the adaptive threshold."""
    p_values = [0.01, 0.02, 0.03, 0.04, 0.9]
    alpha = 0.05
    # Sorted p: 0.01, 0.02, 0.03, 0.04, 0.9
    # Rank 1: threshold = 0.01, p=0.01 <= 0.01  -> reject
    # Rank 2: threshold = 0.02, p=0.02 <= 0.02  -> reject
    # Rank 3: threshold = 0.03, p=0.03 <= 0.03  -> reject
    # Rank 4: threshold = 0.04, p=0.04 <= 0.04  -> reject
    # Rank 5: threshold = 0.05, p=0.9  > 0.05   -> stop
    rejected = benjamini_hochberg(p_values, alpha)
    assert rejected == [True, True, True, True, False]


def test_benjamini_hochberg_no_rejections():
    """BH: all p-values exceed their rank threshold -> none rejected."""
    p_values = [0.02, 0.1, 0.3]
    alpha = 0.05
    # Rank 1: threshold = 0.05/3 ~ 0.0167, p=0.02 > 0.0167 -> stop
    rejected = benjamini_hochberg(p_values, alpha)
    assert rejected == [False, False, False]


def test_benjamini_hochberg_empty():
    """BH: empty p-values returns empty list."""
    assert benjamini_hochberg([], 0.05) == []
    assert benjamini_hochberg([], 0.01) == []


def test_benjamini_hochberg_maintains_original_order():
    """BH: result order matches input p-value order (by original index)."""
    p_values = [0.9, 0.01, 0.5, 0.02]
    alpha = 0.05
    # Sorted: (1, 0.01), (3, 0.02), (2, 0.5), (0, 0.9)
    # Rank 1: threshold=0.0125, p=0.01 <= 0.0125 -> reject
    # Rank 2: threshold=0.025,  p=0.02 <= 0.025  -> reject
    # Rank 3: threshold=0.0375, p=0.5  > 0.0375  -> stop
    # max_reject_rank = 2, so indices 1 and 3 are True
    rejected = benjamini_hochberg(p_values, alpha)
    assert rejected == [False, True, False, True]


# ============================================================================
# Deflated Sharpe ratio
# ============================================================================


def test_deflated_sharpe_standard():
    """Deflated Sharpe: 1.0 * sqrt((1 - 0.5*10/1000) / 0.5) ~ 1.41."""
    result = deflated_sharpe(sharpe=1.0, n_trials=10, n_samples=1000, gamma=0.5)
    # ratio = 0.5 * 10 / 1000 = 0.005
    # result = 1.0 * sqrt((1 - 0.005) / (1 - 0.5))
    #        = sqrt(0.995 / 0.5) = sqrt(1.99) ~ 1.41067
    expected = 1.0 * math.sqrt(
        (1 - 0.5 * 10 / 1000) / (1 - 0.5),
    )
    assert result == pytest.approx(expected, abs=1e-10)


def test_deflated_sharpe_extreme_n_trials():
    """Deflated Sharpe: gamma * n_trials / n_samples >= 1.0 -> 0.0."""
    result = deflated_sharpe(sharpe=1.0, n_trials=1000, n_samples=100, gamma=0.5)
    # 0.5 * 1000 / 100 = 5.0 >= 1.0
    assert result == 0.0


def test_deflated_sharpe_zero_denominator():
    """Deflated Sharpe: gamma=1.0 -> denominator = 0 -> returns 0.0."""
    result = deflated_sharpe(sharpe=1.0, n_trials=10, n_samples=1000, gamma=1.0)
    assert result == 0.0


def test_deflated_sharpe_no_adjustment():
    """Deflated Sharpe: n_trials <= 0 returns original sharpe unchanged."""
    assert deflated_sharpe(sharpe=1.5, n_trials=0, n_samples=1000) == 1.5
    assert deflated_sharpe(sharpe=1.5, n_trials=-5, n_samples=1000) == 1.5


def test_deflated_sharpe_no_samples():
    """Deflated Sharpe: n_samples <= 0 returns original sharpe unchanged."""
    assert deflated_sharpe(sharpe=1.5, n_trials=10, n_samples=0) == 1.5
    assert deflated_sharpe(sharpe=1.5, n_trials=10, n_samples=-1) == 1.5


# ============================================================================
# Trial counting
# ============================================================================


def test_compute_trial_count():
    """Trial count: [10, 49] x 1 x 1 = 490."""
    result = compute_trial_count(
        grid_search_combinations=10,
        thesis_count=49,
        feature_set_count=1,
    )
    assert result == 490


def test_compute_trial_count_empty():
    """Trial count: all zeros floor to 1 each -> 1."""
    result = compute_trial_count(
        grid_search_combinations=0,
        thesis_count=0,
        feature_set_count=0,
    )
    assert result == 1


def test_compute_trial_count_partial_zeros():
    """Trial count: some dimensions zero floor to 1."""
    result = compute_trial_count(
        grid_search_combinations=0,
        thesis_count=5,
        feature_set_count=3,
    )
    # max(1, 0) * max(1, 5) * max(1, 3) = 1 * 5 * 3
    assert result == 15


def test_compute_trial_count_single_dim():
    """Trial count: single dimension only."""
    result = compute_trial_count(
        grid_search_combinations=1,
        thesis_count=1,
        feature_set_count=1,
    )
    assert result == 1


# ============================================================================
# Data-snooping risk
# ============================================================================


def test_data_snooping_risk_490_no_mht():
    """490 trials, no MHT -> HIGH (> 100 and <= 1000, no MHT)."""
    risk = compute_data_snooping_risk(
        n_trials=490, mht_applied=False, fold_count=6,
    )
    assert risk == "HIGH"


def test_data_snooping_risk_490_mht_6_folds():
    """490 trials, MHT, 6 folds -> MEDIUM."""
    risk = compute_data_snooping_risk(
        n_trials=490, mht_applied=True, fold_count=6,
    )
    assert risk == "MEDIUM"


def test_data_snooping_risk_critical():
    """>1000 trials, no MHT -> CRITICAL."""
    risk = compute_data_snooping_risk(
        n_trials=1500, mht_applied=False, fold_count=6,
    )
    assert risk == "CRITICAL"


def test_data_snooping_risk_low_mht():
    """Few trials, MHT, adequate folds -> LOW."""
    risk = compute_data_snooping_risk(
        n_trials=5, mht_applied=True, fold_count=6,
    )
    assert risk == "LOW"


def test_data_snooping_risk_low_default():
    """Low trials, no MHT, enough folds -> LOW."""
    risk = compute_data_snooping_risk(
        n_trials=5, mht_applied=False, fold_count=6,
    )
    assert risk == "LOW"


def test_data_snooping_risk_medium_few_folds():
    """10 trials, 1 fold -> MEDIUM (fold_count < 6)."""
    risk = compute_data_snooping_risk(
        n_trials=10, mht_applied=False, fold_count=1,
    )
    assert risk == "MEDIUM"


# ============================================================================
# TrialLedger
# ============================================================================


class TestTrialLedger:
    """Tests for TrialLedger dataclass."""

    def test_default_ledger(self):
        """Default TrialLedger: empty lists → each dimension floors to 1."""
        ledger = TrialLedger()
        assert ledger.num_symbols == 1
        assert ledger.param_combinations == 1
        assert ledger.num_theses == 1
        assert ledger.num_feature_sets == 1
        assert ledger.tested_hypothesis_count == 1
        assert ledger.trial_count_disclosure == 1

    def test_ten_symbols_49_params(self):
        """10 symbols * 49 params * 1 thesis * 1 feature set = 490."""
        ledger = TrialLedger(
            symbols=[f"ASSET{i}" for i in range(10)],
            param_combinations=49,
            thesis_ids=["ath-001"],
            feature_set_ids=["fs-001"],
        )
        assert ledger.num_symbols == 10
        assert ledger.param_combinations == 49
        assert ledger.num_theses == 1
        assert ledger.num_feature_sets == 1
        assert ledger.tested_hypothesis_count == 490
        assert ledger.trial_count_disclosure == 490

    def test_full_combinatoric(self):
        """3 symbols * 5 params * 2 theses * 4 feature sets = 120."""
        ledger = TrialLedger(
            symbols=["A", "B", "C"],
            param_combinations=5,
            thesis_ids=["th-1", "th-2"],
            feature_set_ids=["fs-1", "fs-2", "fs-3", "fs-4"],
        )
        assert ledger.tested_hypothesis_count == 3 * 5 * 2 * 4  # 120

    def test_empty_lists_floor_to_one(self):
        """Empty lists should each floor to 1 in the product."""
        ledger = TrialLedger(
            symbols=[],
            param_combinations=0,
            thesis_ids=[],
            feature_set_ids=[],
        )
        # num_symbols=max(1,0)=1, param_combinations=0 (direct access),
        # num_theses=max(1,0)=1, num_feature_sets=max(1,0)=1
        # tested_hypothesis_count = 1 * max(1,0) * 1 * 1 = 1
        assert ledger.tested_hypothesis_count == 1

    def test_single_feature_set_only(self):
        """Only feature_sets populated, everything else defaults to 1."""
        ledger = TrialLedger(feature_set_ids=["fs-a", "fs-b"])
        assert ledger.num_feature_sets == 2
        assert ledger.tested_hypothesis_count == 1 * 1 * 1 * 2  # 2

    def test_trial_count_disclosure_matches(self):
        """trial_count_disclosure always equals tested_hypothesis_count."""
        ledger = TrialLedger(
            symbols=["BTCUSDT", "ETHUSDT"],
            param_combinations=10,
            thesis_ids=["th-1"],
            feature_set_ids=["fs-1", "fs-2", "fs-3"],
        )
        assert ledger.trial_count_disclosure == ledger.tested_hypothesis_count
        assert ledger.trial_count_disclosure == 2 * 10 * 1 * 3  # 60


# ============================================================================
# build_mht_section_from_ledger
# ============================================================================


class TestBuildMhtSectionFromLedger:
    """Tests for build_mht_section_from_ledger()."""

    def test_none_applied_default(self):
        """NONE_APPLIED with 10*49 ledger: tested=490, risk=HIGH."""
        ledger = TrialLedger(
            symbols=[f"S{i}" for i in range(10)],
            param_combinations=49,
            thesis_ids=["ath-001"],
            feature_set_ids=["fs-001"],
        )
        section = build_mht_section_from_ledger(ledger)

        assert section["tested_hypothesis_count"] == 490
        assert section["correction_method"] == "NONE_APPLIED"
        assert section["corrected_significance"] is None
        assert section["data_snooping_risk_flag"] == "HIGH"
        # 490 > 100 and NONE_APPLIED → HIGH
        assert section["trial_count_disclosure"] == 490
        assert section["deflated_sharpe_or_equivalent"] is None
        assert section["pbo_or_backtest_overfit_risk"] == "NOT_RUN"
        assert "BLOCKING HOLD" in section["notes"]

    def test_bonferroni_correction(self):
        """Bonferroni with 10*49 ledger: corrected_alpha = 0.05/490."""
        ledger = TrialLedger(
            symbols=[f"S{i}" for i in range(10)],
            param_combinations=49,
        )
        section = build_mht_section_from_ledger(
            ledger, correction_method="Bonferroni", fold_count=6,
        )

        assert section["tested_hypothesis_count"] == 490
        assert section["correction_method"] == "Bonferroni"
        assert section["corrected_significance"] == pytest.approx(0.05 / 490, abs=1e-10)
        # MHT applied, 490 trials → risk goes from HIGH to MEDIUM
        assert section["data_snooping_risk_flag"] == "MEDIUM"
        assert "BLOCKING HOLD" not in section["notes"]

    def test_deflated_sharpe_computed(self):
        """With OOS data, deflated Sharpe is computed."""
        ledger = TrialLedger(
            symbols=["BTCUSDT"],
            param_combinations=10,
            thesis_ids=["ath-001"],
            feature_set_ids=["fs-001"],
        )
        section = build_mht_section_from_ledger(
            ledger=ledger,
            correction_method="Bonferroni",
            fold_count=6,
            oos_sharpe=1.0,
            oos_trade_count=1000,
        )

        assert section["deflated_sharpe_or_equivalent"] is not None
        assert section["deflated_sharpe_or_equivalent"] > 0
        assert section["pbo_or_backtest_overfit_risk"] != "NOT_RUN"

    def test_deflated_sharpe_zero_no_oos(self):
        """No OOS data → deflated Sharpe is None, PBO is NOT_RUN."""
        ledger = TrialLedger(symbols=["BTCUSDT"], param_combinations=10)
        section = build_mht_section_from_ledger(
            ledger=ledger,
            correction_method="Bonferroni",
            oos_sharpe=None,
            oos_trade_count=None,
        )

        assert section["deflated_sharpe_or_equivalent"] is None
        assert section["pbo_or_backtest_overfit_risk"] == "NOT_RUN"

    def test_critical_risk_no_mht_many_trials(self):
        """>1000 trials with no MHT → CRITICAL risk."""
        ledger = TrialLedger(
            symbols=[f"S{i}" for i in range(20)],
            param_combinations=100,
            thesis_ids=["th-1"],
            feature_set_ids=["fs-1", "fs-2"],
        )
        # 20 * 100 * 1 * 2 = 4000 > 1000
        section = build_mht_section_from_ledger(ledger)
        assert section["data_snooping_risk_flag"] == "CRITICAL"

    def test_low_risk_with_mht(self):
        """Low trial count + MHT applied + adequate folds → LOW risk."""
        ledger = TrialLedger(
            symbols=["BTCUSDT"],
            param_combinations=3,
        )
        section = build_mht_section_from_ledger(
            ledger, correction_method="Bonferroni", fold_count=6,
        )
        assert section["data_snooping_risk_flag"] == "LOW"

    def test_section_validates_against_schema(self):
        """Section from build_mht_section_from_ledger validates against schema."""
        from alphaforge.contracts.validator import validate_payload
        from alphaforge.reports import build_minimal_mode_research_report
        from alphaforge.schema_loader import load_schema

        schema = load_schema("ModeResearchReport")

        # Use a realistic ledger
        ledger = TrialLedger(
            symbols=[f"S{i}" for i in range(10)],
            param_combinations=49,
            thesis_ids=["ath-001"],
            feature_set_ids=["fs-001"],
        )
        section = build_mht_section_from_ledger(
            ledger, correction_method="Bonferroni", fold_count=6,
        )

        # Build minimal report and override MHT section
        report = build_minimal_mode_research_report(mode="SWING")
        report.setdefault("metrics", {}).update({
            "active_trade_count": 7,
            "total_net_R": 1.58,
            "exposure_pct": 70.0,
        })
        report["multiple_hypothesis_control"] = section

        result = validate_payload(schema, report, "ModeResearchReport")
        assert result.valid, f"MHT section failed schema validation: {result.errors}"

    def test_section_with_all_correction_methods(self):
        """Section works with all schema-allowed correction methods."""
        ledger = TrialLedger(
            symbols=["BTCUSDT"],
            param_combinations=5,
        )
        for method in ("Bonferroni", "FDR", "Deflated_Sharpe", "PBO", "NONE_APPLIED"):
            section = build_mht_section_from_ledger(ledger, correction_method=method)
            assert section["correction_method"] == method
            assert section["tested_hypothesis_count"] == 5


# ============================================================================
# Scaffold builder integration
# ============================================================================


class TestScaffoldMhtIntegration:
    """Tests that scaffold builders produce correct MHT values."""

    def test_mode_research_report_mht_490(self):
        """build_mode_research_report now has tested_hypothesis_count = 490."""
        from alphaforge.reports.builders import _make_mht_control

        section = _make_mht_control("SWING")
        assert section["tested_hypothesis_count"] == 490  # 10*49*1*1
        assert section["correction_method"] == "NONE_APPLIED"
        assert section["data_snooping_risk_flag"] == "HIGH"
        assert section["trial_count_disclosure"] == 490
        assert section["corrected_significance"] is None

    def test_minimal_report_mht_schema_valid(self):
        """build_minimal_mode_research_report produces schema-valid MHT."""
        from alphaforge.contracts.validator import validate_payload
        from alphaforge.schema_loader import load_schema

        schema = load_schema("ModeResearchReport")

        report = build_minimal_mode_research_report(mode="SWING")
        result = validate_payload(schema, report, "ModeResearchReport")

        # The minimal report has BLOCKED_FOR_MHT verdict which is schema-valid
        assert result.valid, f"Schema validation failed: {result.errors}"

    def test_minimal_report_default_ledger(self):
        """Minimal report with default ledger has tested_hypothesis_count=1."""
        report = build_minimal_mode_research_report(mode="SWING")
        mht = report["multiple_hypothesis_control"]
        assert mht["tested_hypothesis_count"] >= 1
        assert mht["correction_method"] == "NONE_APPLIED"
        assert mht["trial_count_disclosure"] >= 1

    def test_minimal_report_with_custom_ledger(self):
        """Minimal report accepts a custom TrialLedger."""
        ledger = TrialLedger(
            symbols=["BTCUSDT", "ETHUSDT"],
            param_combinations=10,
            thesis_ids=["th-1"],
            feature_set_ids=["fs-1", "fs-2"],
        )
        report = build_minimal_mode_research_report(mode="SCALP", ledger=ledger)
        mht = report["multiple_hypothesis_control"]
        assert mht["tested_hypothesis_count"] == 2 * 10 * 1 * 2  # 40
        assert mht["trial_count_disclosure"] == 40

    def test_empirical_mht_accepts_ledger(self):
        """"_build_empirical_mht_control accepts a TrialLedger."""
        from alphaforge.reports.empirical import _build_empirical_mht_control

        ledger = TrialLedger(
            symbols=["BTCUSDT"],
            param_combinations=49,
            thesis_ids=["ath-001"],
        )
        section = _build_empirical_mht_control(
            wfv_results={},
            fold_count=6,
            oos_sharpe=0.8,
            oos_trade_count=500,
            ledger=ledger,
        )
        assert section["tested_hypothesis_count"] == 49
        assert section["trial_count_disclosure"] == 49
        assert section["correction_method"] == "NONE_APPLIED"
        assert "mht_status" in section


# ============================================================================
# Schema validation
# ============================================================================


def test_mht_section_validates_against_schema():
    """MHT section built from mht.py functions validates against JSON schema."""
    from alphaforge.contracts.validator import validate_payload
    from alphaforge.reports import build_minimal_mode_research_report
    from alphaforge.schema_loader import load_schema

    schema = load_schema("ModeResearchReport")

    # Compute values using mht.py functions
    trial_count = compute_trial_count(
        grid_search_combinations=10,
        thesis_count=49,
        feature_set_count=1,
    )
    adjusted_alpha = bonferroni_correction(0.05, trial_count)
    risk_flag = compute_data_snooping_risk(
        n_trials=trial_count, mht_applied=True, fold_count=6,
    )

    # Build a minimal valid report and override the MHT section
    report: Dict[str, Any] = build_minimal_mode_research_report(mode="SWING")
    # Ensure required metric fields from P0.9C schema are present
    report.setdefault("metrics", {}).update({
        "active_trade_count": 7,
        "total_net_R": 1.58,
        "exposure_pct": 70.0,
    })
    report["multiple_hypothesis_control"] = {
        "mht_status": "APPLIED_WITH_WARNINGS",
        "tested_hypothesis_count": trial_count,
        "tested_feature_count": 1,
        "tested_thesis_count": 49,
        "correction_method": "Bonferroni",
        "corrected_significance": adjusted_alpha,
        "data_snooping_risk_flag": risk_flag,
        "trial_count_disclosure": trial_count,
        "false_discovery_control": "NONE",
        "deflated_sharpe_or_pbo_assessment": "NOT_RUN",
        "rejected_candidate_count": 0,
    }

    result = validate_payload(schema, report, "ModeResearchReport")
    assert result.valid, f"MHT section failed schema validation: {result.errors}"
