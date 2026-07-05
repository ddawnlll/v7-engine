"""
Scope-compatible artifact selection for V7 Engine.

Provides:
  - ArtifactScope dataclass: structured description of a model artifact's scope.
  - SCOPE_COMPATIBILITY_MATRIX: canonical mapping from model_scope to trade_mode.
  - validate_scope_compatibility: check compatibility between two scopes.
  - select_compatible_artifacts: filter a list of artifacts by a requested scope.
  - ScopeMismatchError: exception raised on scope incompatibility.

Authority:
  - V7 router owns mode/scope dispatch rules (v7/router.py).
  - contracts/mappings/ define field-level cross-domain mapping.
  - SCOPE_COMPATIBILITY_MATRIX must stay in sync with v7/router._MODEL_SCOPE_PREFIXES.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class ScopeMismatchError(ValueError):
    """Raised when a requested scope does not match an artifact's scope.

    Attributes:
        request_scope: The scope that was requested.
        artifact_scope: The scope of the artifact that was checked.
        issues: List of human-readable compatibility issue descriptions.
    """

    def __init__(
        self,
        request_scope: str | None = None,
        artifact_scope: str | None = None,
        issues: list[str] | None = None,
    ) -> None:
        self.request_scope = request_scope
        self.artifact_scope = artifact_scope
        self.issues = issues or []
        msg = "Scope mismatch"
        if issues:
            msg += f": {'; '.join(issues)}"
        super().__init__(msg)


# ---------------------------------------------------------------------------
# ArtifactScope
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ArtifactScope:
    """Structured description of a model artifact's scope.

    Attributes:
        model_scope:    Model scope identifier, e.g. ``"swing_v1"``.
        trade_mode:     Trading mode, e.g. ``"SWING"``.
        primary_interval: Primary trading interval, e.g. ``"4h"``.
        version:        Artifact version string, e.g. ``"1.0.0"``.
    """

    model_scope: str
    trade_mode: str
    primary_interval: str
    version: str


# ---------------------------------------------------------------------------
# Scope compatibility matrix
# ---------------------------------------------------------------------------

SCOPE_COMPATIBILITY_MATRIX: dict[str, str] = {
    "swing_v1": "SWING",
    "scalp_v1": "SCALP",
    "aggressive_scalp_v1": "AGGRESSIVE_SCALP",
}

# Inverse: trade_mode -> list of compatible model_scope values.
_SCOPE_MODE_TO_SCOPES: dict[str, list[str]] = {}
for _scope, _mode in SCOPE_COMPATIBILITY_MATRIX.items():
    _SCOPE_MODE_TO_SCOPES.setdefault(_mode, []).append(_scope)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ensure_scope(
    scope: ArtifactScope | dict[str, Any],
) -> ArtifactScope:
    """Coerce a dict to an ArtifactScope if needed.

    Raises:
        TypeError: If ``scope`` is neither an ``ArtifactScope`` nor a dict.
    """
    if isinstance(scope, ArtifactScope):
        return scope
    if not isinstance(scope, dict):
        raise TypeError(
            f"Expected ArtifactScope or dict, got {type(scope).__name__}"
        )
    return ArtifactScope(
        model_scope=str(scope.get("model_scope", "")),
        trade_mode=str(scope.get("trade_mode", "")),
        primary_interval=str(scope.get("primary_interval", "")),
        version=str(scope.get("version", "")),
    )


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_scope_compatibility(
    request_scope: ArtifactScope | dict[str, Any],
    artifact_scope: ArtifactScope | dict[str, Any],
) -> list[str]:
    """Validate compatibility between a requested scope and an artifact scope.

    Checks performed:
      1. Both scopes have a known ``model_scope`` in
         ``SCOPE_COMPATIBILITY_MATRIX``.
      2. The ``trade_mode`` implied by the request's ``model_scope`` matches
         the artifact's ``trade_mode``.
      3. A warning is issued if ``primary_interval`` differs (non-blocking).

    Args:
        request_scope:  The scope being requested (ArtifactScope or dict).
        artifact_scope: The scope of the artifact being checked.

    Returns:
        A list of human-readable issue strings.  An empty list means the
        scopes are compatible.
    """
    rs = _ensure_scope(request_scope)
    art = _ensure_scope(artifact_scope)

    issues: list[str] = []

    # --- 1. Request scope model_scope is known ---
    rs_mode = SCOPE_COMPATIBILITY_MATRIX.get(rs.model_scope)
    if rs_mode is None:
        issues.append(
            f"Request model_scope '{rs.model_scope}' is not in "
            f"SCOPE_COMPATIBILITY_MATRIX"
        )

    # --- 2. Artifact scope model_scope is known ---
    art_mode = SCOPE_COMPATIBILITY_MATRIX.get(art.model_scope)
    if art_mode is None:
        issues.append(
            f"Artifact model_scope '{art.model_scope}' is not in "
            f"SCOPE_COMPATIBILITY_MATRIX"
        )

    # --- 3. Trade mode alignment ---
    if rs_mode is not None and art_mode is not None:
        if rs_mode != art_mode:
            issues.append(
                f"Trade mode mismatch: request model_scope '{rs.model_scope}' "
                f"maps to '{rs_mode}' but artifact model_scope "
                f"'{art.model_scope}' maps to '{art_mode}'"
            )

    # Also check explicit trade_mode fields if they're set
    if rs.trade_mode and art.trade_mode and rs.trade_mode != art.trade_mode:
        issues.append(
            f"Trade mode mismatch: request has '{rs.trade_mode}' "
            f"but artifact has '{art.trade_mode}'"
        )

    # --- 4. Primary interval check (warning level) ---
    if rs.primary_interval and art.primary_interval:
        if rs.primary_interval != art.primary_interval:
            issues.append(
                f"Primary interval mismatch: request has '{rs.primary_interval}' "
                f"but artifact has '{art.primary_interval}'"
            )

    return issues


# ---------------------------------------------------------------------------
# Artifact selection
# ---------------------------------------------------------------------------


def select_compatible_artifacts(
    artifacts: list[dict[str, Any]],
    requested_scope: ArtifactScope | dict[str, Any],
) -> tuple[list[dict[str, Any]], list[str]]:
    """Filter a list of artifacts to those compatible with a requested scope.

    Each artifact dict should contain a ``"scope"`` key whose value is either
    an ``ArtifactScope`` or a dict with ``model_scope`` and ``trade_mode``.

    Artifacts without a ``"scope"`` key are treated as incompatible and
    produce a warning (they are excluded from the result).

    Args:
        artifacts:       List of artifact metadata dicts.
        requested_scope: The scope to match against.

    Returns:
        A tuple ``(compatible_artifacts, warnings)`` where ``compatible`` is
        the list of artifacts that pass compatibility and ``warnings`` is a
        list of human-readable warning strings for artifacts that were skipped.
    """
    rs = _ensure_scope(requested_scope)
    compatible: list[dict[str, Any]] = []
    warnings: list[str] = []

    for i, artifact in enumerate(artifacts):
        raw_scope = artifact.get("scope")
        if raw_scope is None:
            warnings.append(
                f"Artifact at index {i} has no 'scope' key, skipping"
            )
            continue

        try:
            art_scope = _ensure_scope(raw_scope)
        except (TypeError, ValueError, AttributeError) as exc:
            warnings.append(
                f"Artifact at index {i} has invalid scope: {exc}"
            )
            continue

        issues = validate_scope_compatibility(rs, art_scope)
        if issues:
            warnings.append(
                f"Artifact at index {i} (model_scope='{art_scope.model_scope}'): "
                f"{'; '.join(issues)}"
            )
            continue

        compatible.append(artifact)

    return compatible, warnings
