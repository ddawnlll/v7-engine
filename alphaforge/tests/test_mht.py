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
    benjamini_hochberg,
    bonferroni_correction,
    compute_data_snooping_risk,
    compute_trial_count,
    deflated_sharpe,
)


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
