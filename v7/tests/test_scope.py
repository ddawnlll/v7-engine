"""
Tests for v7.scope — scope-compatible artifact selection and validation.

Covers:
  1. ArtifactScope dataclass construction and immutability
  2. SCOPE_COMPATIBILITY_MATRIX values and completeness
  3. validate_scope_compatibility — happy path and all error modes
  4. select_compatible_artifacts — filtering, warnings, edge cases
  5. ScopeMismatchError exception
  6. Dict coercion (dict input converted to ArtifactScope)
"""

from __future__ import annotations

from typing import Any

import pytest

from v7.scope import (
    SCOPE_COMPATIBILITY_MATRIX,
    ArtifactScope,
    ScopeMismatchError,
    select_compatible_artifacts,
    validate_scope_compatibility,
)


# ===========================================================================
# Fixtures
# ===========================================================================


@pytest.fixture()
def swing_scope() -> ArtifactScope:
    return ArtifactScope(
        model_scope="swing_v1",
        trade_mode="SWING",
        primary_interval="4h",
        version="1.0.0",
    )


@pytest.fixture()
def scalp_scope() -> ArtifactScope:
    return ArtifactScope(
        model_scope="scalp_v1",
        trade_mode="SCALP",
        primary_interval="1h",
        version="1.0.0",
    )


@pytest.fixture()
def aggressive_scalp_scope() -> ArtifactScope:
    return ArtifactScope(
        model_scope="aggressive_scalp_v1",
        trade_mode="AGGRESSIVE_SCALP",
        primary_interval="15m",
        version="1.0.0",
    )


# ===========================================================================
# 1. ArtifactScope dataclass
# ===========================================================================


class TestArtifactScope:
    """ArtifactScope construction and properties."""

    def test_minimal(self) -> None:
        """Create with all required fields."""
        s = ArtifactScope(
            model_scope="swing_v1",
            trade_mode="SWING",
            primary_interval="4h",
            version="1.0.0",
        )
        assert s.model_scope == "swing_v1"
        assert s.trade_mode == "SWING"
        assert s.primary_interval == "4h"
        assert s.version == "1.0.0"

    def test_frozen(self) -> None:
        """ArtifactScope is immutable."""
        s = ArtifactScope(
            model_scope="swing_v1",
            trade_mode="SWING",
            primary_interval="4h",
            version="1.0.0",
        )
        with pytest.raises(AttributeError):
            s.model_scope = "scalp_v1"  # type: ignore[misc]


# ===========================================================================
# 2. SCOPE_COMPATIBILITY_MATRIX
# ===========================================================================


class TestScopeCompatibilityMatrix:
    """Verify SCOPE_COMPATIBILITY_MATRIX values."""

    def test_swing_mapping(self) -> None:
        assert SCOPE_COMPATIBILITY_MATRIX["swing_v1"] == "SWING"

    def test_scalp_mapping(self) -> None:
        assert SCOPE_COMPATIBILITY_MATRIX["scalp_v1"] == "SCALP"

    def test_aggressive_scalp_mapping(self) -> None:
        assert SCOPE_COMPATIBILITY_MATRIX["aggressive_scalp_v1"] == "AGGRESSIVE_SCALP"

    def test_all_three_modes(self) -> None:
        """Matrix contains exactly three entries."""
        assert len(SCOPE_COMPATIBILITY_MATRIX) == 3

    def test_unknown_scope_not_in_matrix(self) -> None:
        assert "swing_v2" not in SCOPE_COMPATIBILITY_MATRIX
        assert "day_trade" not in SCOPE_COMPATIBILITY_MATRIX


# ===========================================================================
# 3. validate_scope_compatibility
# ===========================================================================


class TestValidateScopeCompatibility:
    """validate_scope_compatibility — happy path and error modes."""

    def test_swing_with_swing(self, swing_scope: ArtifactScope) -> None:
        """SWING request and SWING artifact are compatible."""
        issues = validate_scope_compatibility(swing_scope, swing_scope)
        assert issues == []

    def test_scalp_with_scalp(self, scalp_scope: ArtifactScope) -> None:
        """SCALP request and SCALP artifact are compatible."""
        issues = validate_scope_compatibility(scalp_scope, scalp_scope)
        assert issues == []

    def test_aggressive_scalp_self_compatible(
        self, aggressive_scalp_scope: ArtifactScope,
    ) -> None:
        """AGGRESSIVE_SCALP request and artifact are compatible."""
        issues = validate_scope_compatibility(
            aggressive_scalp_scope, aggressive_scalp_scope,
        )
        assert issues == []

    def test_swing_request_with_scalp_artifact(
        self, swing_scope: ArtifactScope, scalp_scope: ArtifactScope,
    ) -> None:
        """SWING request with SCALP artifact is incompatible."""
        issues = validate_scope_compatibility(swing_scope, scalp_scope)
        assert len(issues) > 0
        assert any("mismatch" in i.lower() for i in issues)

    def test_scalp_request_with_swing_artifact(
        self, swing_scope: ArtifactScope, scalp_scope: ArtifactScope,
    ) -> None:
        """SCALP request with SWING artifact is incompatible."""
        issues = validate_scope_compatibility(scalp_scope, swing_scope)
        assert len(issues) > 0
        assert any("mismatch" in i.lower() for i in issues)

    def test_unknown_request_model_scope(
        self, swing_scope: ArtifactScope,
    ) -> None:
        """Unknown request model_scope triggers a matrix-not-found issue."""
        unknown = ArtifactScope(
            model_scope="unknown_v1",
            trade_mode="SWING",
            primary_interval="4h",
            version="1.0.0",
        )
        issues = validate_scope_compatibility(unknown, swing_scope)
        assert any("not in SCOPE_COMPATIBILITY_MATRIX" in i for i in issues)

    def test_unknown_artifact_model_scope(
        self, swing_scope: ArtifactScope,
    ) -> None:
        """Unknown artifact model_scope triggers a matrix-not-found issue."""
        unknown = ArtifactScope(
            model_scope="unknown_v1",
            trade_mode="SWING",
            primary_interval="4h",
            version="1.0.0",
        )
        issues = validate_scope_compatibility(swing_scope, unknown)
        assert any("not in SCOPE_COMPATIBILITY_MATRIX" in i for i in issues)

    def test_interval_mismatch(self) -> None:
        """Different primary_intervals generate a (non-fatal) issue."""
        request = ArtifactScope(
            model_scope="swing_v1",
            trade_mode="SWING",
            primary_interval="4h",
            version="1.0.0",
        )
        artifact = ArtifactScope(
            model_scope="swing_v1",
            trade_mode="SWING",
            primary_interval="1h",
            version="1.0.0",
        )
        issues = validate_scope_compatibility(request, artifact)
        assert any("interval mismatch" in i.lower() for i in issues)

    def test_trade_mode_field_mismatch(self) -> None:
        """Explicit trade_mode fields are checked even when model_scope matches.

        If both have trade_mode set and they differ, an issue is raised.
        """
        request = ArtifactScope(
            model_scope="swing_v1",
            trade_mode="SWING",
            primary_interval="4h",
            version="1.0.0",
        )
        artifact = ArtifactScope(
            model_scope="swing_v1",
            trade_mode="SCALP",
            primary_interval="4h",
            version="1.0.0",
        )
        issues = validate_scope_compatibility(request, artifact)
        # model_scope maps to SWING for both, but trade_mode field differs
        assert any("trade mode mismatch" in i.lower() for i in issues)

    def test_dict_input(self) -> None:
        """Dict input is coerced to ArtifactScope."""
        request = {
            "model_scope": "swing_v1",
            "trade_mode": "SWING",
            "primary_interval": "4h",
            "version": "1.0.0",
        }
        artifact = {
            "model_scope": "swing_v1",
            "trade_mode": "SWING",
            "primary_interval": "4h",
            "version": "1.0.0",
        }
        issues = validate_scope_compatibility(request, artifact)
        assert issues == []

    def test_dict_input_mismatch(self) -> None:
        """Dict input correctly detects mismatches."""
        request = {
            "model_scope": "swing_v1",
            "trade_mode": "SWING",
            "primary_interval": "4h",
        }
        artifact = {
            "model_scope": "scalp_v1",
            "trade_mode": "SCALP",
            "primary_interval": "1h",
        }
        issues = validate_scope_compatibility(request, artifact)
        assert len(issues) > 0

    def test_mixed_dict_and_scope(
        self, swing_scope: ArtifactScope,
    ) -> None:
        """Mixed ArtifactScope and dict input works."""
        request_dict = {
            "model_scope": "swing_v1",
            "trade_mode": "SWING",
            "primary_interval": "4h",
            "version": "1.0.0",
        }
        issues = validate_scope_compatibility(request_dict, swing_scope)
        assert issues == []

    def test_empty_trade_mode_no_false_positive(self) -> None:
        """Empty trade_mode fields do not trigger false mismatch."""
        request = ArtifactScope(
            model_scope="swing_v1",
            trade_mode="",
            primary_interval="4h",
            version="1.0.0",
        )
        artifact = ArtifactScope(
            model_scope="swing_v1",
            trade_mode="",
            primary_interval="4h",
            version="1.0.0",
        )
        issues = validate_scope_compatibility(request, artifact)
        assert issues == []


# ===========================================================================
# 4. ScopeMismatchError
# ===========================================================================


class TestScopeMismatchError:
    """ScopeMismatchError exception."""

    def test_default_message(self) -> None:
        """Default message is 'Scope mismatch'."""
        err = ScopeMismatchError()
        assert str(err) == "Scope mismatch"

    def test_with_issues(self) -> None:
        """Issues are joined into the message."""
        err = ScopeMismatchError(
            request_scope="swing_v1",
            artifact_scope="scalp_v1",
            issues=["Trade mode mismatch", "Interval mismatch"],
        )
        assert "Trade mode mismatch" in str(err)
        assert "Interval mismatch" in str(err)
        assert err.request_scope == "swing_v1"
        assert err.artifact_scope == "scalp_v1"
        assert len(err.issues) == 2

    def test_no_issues(self) -> None:
        """No issues results in bare message."""
        err = ScopeMismatchError(request_scope="swing_v1")
        assert str(err) == "Scope mismatch"
        assert err.issues == []


# ===========================================================================
# 5. select_compatible_artifacts
# ===========================================================================


class TestSelectCompatibleArtifacts:
    """select_compatible_artifacts filtering and warnings."""

    def test_all_compatible(
        self, swing_scope: ArtifactScope,
    ) -> None:
        """All artifacts compatible with request pass through."""
        artifacts = [
            {"id": "model_1", "scope": swing_scope},
            {"id": "model_2", "scope": swing_scope},
        ]
        compatible, warnings = select_compatible_artifacts(artifacts, swing_scope)
        assert len(compatible) == 2
        assert warnings == []

    def test_some_incompatible(
        self, swing_scope: ArtifactScope, scalp_scope: ArtifactScope,
    ) -> None:
        """Incompatible artifacts are excluded with warnings."""
        artifacts = [
            {"id": "m1", "scope": swing_scope},
            {"id": "m2", "scope": scalp_scope},
        ]
        compatible, warnings = select_compatible_artifacts(artifacts, swing_scope)
        assert len(compatible) == 1
        assert compatible[0]["id"] == "m1"
        assert len(warnings) == 1
        assert "mismatch" in warnings[0].lower()

    def test_all_incompatible(
        self, swing_scope: ArtifactScope, scalp_scope: ArtifactScope,
    ) -> None:
        """All artifacts incompatible returns empty list."""
        artifacts = [
            {"id": "m1", "scope": scalp_scope},
            {"id": "m2", "scope": scalp_scope},
        ]
        compatible, warnings = select_compatible_artifacts(artifacts, swing_scope)
        assert compatible == []
        assert len(warnings) == 2

    def test_empty_artifacts(
        self, swing_scope: ArtifactScope,
    ) -> None:
        """Empty artifact list returns empty result."""
        compatible, warnings = select_compatible_artifacts([], swing_scope)
        assert compatible == []
        assert warnings == []

    def test_missing_scope_key(
        self, swing_scope: ArtifactScope,
    ) -> None:
        """Artifact without 'scope' key is skipped with warning."""
        artifacts = [
            {"id": "m1"},
            {"id": "m2", "scope": swing_scope},
        ]
        compatible, warnings = select_compatible_artifacts(artifacts, swing_scope)
        assert len(compatible) == 1
        assert len(warnings) == 1
        assert "no 'scope' key" in warnings[0]

    def test_scope_is_dict(
        self, swing_scope: ArtifactScope,
    ) -> None:
        """Artifact with dict scope is handled correctly."""
        artifacts = [
            {
                "id": "m1",
                "scope": {
                    "model_scope": "swing_v1",
                    "trade_mode": "SWING",
                    "primary_interval": "4h",
                    "version": "1.0.0",
                },
            },
        ]
        compatible, warnings = select_compatible_artifacts(artifacts, swing_scope)
        assert len(compatible) == 1
        assert compatible[0]["id"] == "m1"
        assert warnings == []

    def test_requested_scope_is_dict(
        self, swing_scope: ArtifactScope,
    ) -> None:
        """Requested scope passed as dict works."""
        request_dict = {
            "model_scope": "swing_v1",
            "trade_mode": "SWING",
            "primary_interval": "4h",
            "version": "1.0.0",
        }
        artifacts = [
            {"id": "m1", "scope": swing_scope},
        ]
        compatible, warnings = select_compatible_artifacts(artifacts, request_dict)
        assert len(compatible) == 1
        assert warnings == []

    def test_interval_mismatch_produces_warning(
        self,
    ) -> None:
        """Interval mismatch generates warning but artifact is still excluded."""
        request = ArtifactScope(
            model_scope="swing_v1",
            trade_mode="SWING",
            primary_interval="4h",
            version="1.0.0",
        )
        artifact_scope = ArtifactScope(
            model_scope="swing_v1",
            trade_mode="SWING",
            primary_interval="1h",
            version="1.0.0",
        )
        artifacts = [
            {"id": "m1", "scope": artifact_scope},
        ]
        compatible, warnings = select_compatible_artifacts(artifacts, request)
        assert compatible == []
        assert len(warnings) == 1
        assert "interval mismatch" in warnings[0].lower()

    def test_invalid_scope_value(
        self, swing_scope: ArtifactScope,
    ) -> None:
        """Artifact with invalid scope (non-dict) is skipped with warning."""
        artifacts = [
            {"id": "m1", "scope": "not_a_scope"},
        ]
        compatible, warnings = select_compatible_artifacts(artifacts, swing_scope)
        assert compatible == []
        assert len(warnings) == 1
        assert "invalid" in warnings[0].lower()

    def test_mixed_scopes(
        self,
        swing_scope: ArtifactScope,
        scalp_scope: ArtifactScope,
        aggressive_scalp_scope: ArtifactScope,
    ) -> None:
        """Multiple scopes are correctly filtered."""
        artifacts = [
            {"id": "swing_model", "scope": swing_scope},
            {"id": "scalp_model", "scope": scalp_scope},
            {"id": "aggressive_model", "scope": aggressive_scalp_scope},
        ]
        # Filter for SWING
        compatible, warnings = select_compatible_artifacts(artifacts, swing_scope)
        assert len(compatible) == 1
        assert compatible[0]["id"] == "swing_model"
        assert len(warnings) == 2

        # Filter for SCALP
        compatible, warnings = select_compatible_artifacts(artifacts, scalp_scope)
        assert len(compatible) == 1
        assert compatible[0]["id"] == "scalp_model"
        assert len(warnings) == 2

    def test_result_types(
        self, swing_scope: ArtifactScope,
    ) -> None:
        """Result types match the signature."""
        compatible, warnings = select_compatible_artifacts([], swing_scope)
        assert isinstance(compatible, list)
        assert isinstance(warnings, list)

    def test_no_scope_field_no_error(
        self, swing_scope: ArtifactScope,
    ) -> None:
        """Artifacts with no scope field are skipped gracefully."""
        artifacts = [
            {"id": "m1", "some_other_key": "value"},
        ]
        compatible, warnings = select_compatible_artifacts(artifacts, swing_scope)
        assert compatible == []
        assert len(warnings) == 1
        assert "no 'scope' key" in warnings[0]
