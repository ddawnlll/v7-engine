"""Test canonical mode profiles match P0.8E timeframe alignment."""

import pytest


def test_swing_profile():
    from alphaforge.modes import SWING
    assert SWING.primary_interval == "4h"
    assert SWING.context_interval == "1d"
    assert SWING.refinement_interval == "1h"
    assert SWING.priority == "SECONDARY_BASELINE"
    assert SWING.threshold_status == "LOCKED_INITIAL_BASELINE"


def test_scalp_profile():
    from alphaforge.modes import SCALP
    assert SCALP.primary_interval == "1h", "SCALP primary must be 1h, not 15m"
    assert SCALP.context_interval == "4h"
    assert SCALP.refinement_interval == "15m"
    assert SCALP.priority == "PRIMARY"
    assert SCALP.threshold_status == "HOLD"


def test_aggressive_scalp_profile():
    from alphaforge.modes import AGGRESSIVE_SCALP
    assert AGGRESSIVE_SCALP.primary_interval == "15m"
    assert AGGRESSIVE_SCALP.context_interval == "1h"
    assert AGGRESSIVE_SCALP.refinement_interval == "5m"
    assert AGGRESSIVE_SCALP.priority == "PRIMARY"
    assert AGGRESSIVE_SCALP.threshold_status == "HOLD"


def test_canonical_profiles_registered():
    from alphaforge.modes import CANONICAL_PROFILES, ALLOWED_MODES
    assert set(CANONICAL_PROFILES.keys()) == {"SWING", "SCALP", "AGGRESSIVE_SCALP"}
    assert ALLOWED_MODES == frozenset(["SWING", "SCALP", "AGGRESSIVE_SCALP"])


def test_get_profile_valid():
    from alphaforge.modes import get_profile
    assert get_profile("SWING").name == "SWING"


def test_get_profile_invalid_raises():
    from alphaforge.modes import get_profile
    from alphaforge.errors import ConfigError
    with pytest.raises(ConfigError):
        get_profile("INVALID_MODE")


def test_validate_all_profiles():
    from alphaforge.modes import validate_all_profiles
    validate_all_profiles()


def test_timeframe_stack():
    from alphaforge.modes import SWING
    assert SWING.timeframe_stack == {"primary": "4h", "context": "1d", "refinement": "1h"}


def test_mode_profile_frozen():
    from alphaforge.modes import SWING
    with pytest.raises(Exception):
        SWING.primary_interval = "1h"  # type: ignore[misc]
