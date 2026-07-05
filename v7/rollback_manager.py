"""
Rollback and kill-switch hardening — artifact version management,
rollback per scope, compatibility validation, and kill-switch lifecycle.

Domain rules:
- Each artifact has a version, scope, and compatible_with set.
- Rollback restores the last-known-good artifact for a scope.
- Kill switch can be activated/deactivated per scope.
- Compatibility must be validated before migration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class ArtifactBundle:
    """A versioned artifact bundle with scope and compatibility metadata.

    Attributes:
        version: Artifact version string (e.g. '1.0.0').
        scope: Model scope this artifact belongs to (e.g. 'swing_v1').
        gates_results: Dict of gate_id -> GateResult dict (status, score, etc.).
        compatible_with: Set of artifact versions this is compatible with.
        metadata: Optional additional metadata dict.
    """

    version: str
    scope: str
    gates_results: dict[str, dict[str, Any]] = field(default_factory=dict)
    compatible_with: set[str] = field(default_factory=set)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class KillSwitch:
    """Kill switch status for a model scope.

    Attributes:
        active: True if the kill switch is active (trading halted).
        scope: The model scope this switch applies to.
        reason: Reason for activation (empty if not active).
        activated_at: ISO timestamp of activation.
        activated_by: Who/what activated the switch.
    """

    active: bool = False
    scope: str = ""
    reason: str = ""
    activated_at: str = ""
    activated_by: str = ""


def _now_ts() -> str:
    return datetime.now(timezone.utc).isoformat()


class RollbackManager:
    """Manages artifact versions and rollback operations per scope.

    Maintains a version history per scope and supports rollback
    to any previously registered version.
    """

    def __init__(self) -> None:
        self._artifacts: dict[str, list[ArtifactBundle]] = {}
        self._active_versions: dict[str, str] = {}

    def register_artifact(self, bundle: ArtifactBundle) -> None:
        """Register an artifact bundle for its scope.

        Args:
            bundle: The ArtifactBundle to register.

        Raises:
            ValueError: If bundle version is empty.
        """
        if not bundle.version:
            raise ValueError("ArtifactBundle must have a non-empty version")

        scope = bundle.scope
        if scope not in self._artifacts:
            self._artifacts[scope] = []
        self._artifacts[scope].append(bundle)
        self._active_versions[scope] = bundle.version

    def rollback(self, scope: str, target_version: str) -> ArtifactBundle | None:
        """Rollback a scope to a specific version.

        Args:
            scope: The model scope to rollback.
            target_version: The version to rollback to.

        Returns:
            The ArtifactBundle of the target version, or None if not found.
        """
        artifacts = self._artifacts.get(scope, [])
        for bundle in artifacts:
            if bundle.version == target_version:
                self._active_versions[scope] = target_version
                return bundle
        return None

    def get_active_version(self, scope: str) -> str | None:
        """Get the currently active version for a scope.

        Args:
            scope: The model scope.

        Returns:
            The active version string, or None if no artifact registered.
        """
        return self._active_versions.get(scope)

    def get_version_history(self, scope: str) -> list[ArtifactBundle]:
        """Get all artifact versions registered for a scope.

        Args:
            scope: The model scope.

        Returns:
            List of ArtifactBundles in registration order.
        """
        return list(self._artifacts.get(scope, []))

    def get_last_known_good(self, scope: str) -> ArtifactBundle | None:
        """Get the last known good (non-rolled-back) version for a scope.

        Returns the artifact before the currently active one in registration
        order, or the same one if only one exists.

        Args:
            scope: The model scope.

        Returns:
            The last-known-good ArtifactBundle, or None if no history.
        """
        artifacts = self._artifacts.get(scope, [])
        if len(artifacts) <= 1:
            return artifacts[0] if artifacts else None

        active = self._active_versions.get(scope)
        # Walk backwards from the end to find the artifact before the active
        for i, bundle in enumerate(artifacts):
            if bundle.version == active and i > 0:
                return artifacts[i - 1]
        return artifacts[-2] if len(artifacts) >= 2 else artifacts[0]

    @staticmethod
    def validate_compatibility(
        b1: ArtifactBundle,
        b2: ArtifactBundle,
    ) -> dict[str, Any]:
        """Validate compatibility between two artifact bundles.

        Checks:
          - b2 is in b1's compatible_with set (or vice versa)
          - Both bundles have the same scope
          - Gate score compatibility (no critical regression)

        Args:
            b1: First artifact bundle.
            b2: Second artifact bundle.

        Returns:
            Dict with compatible (bool), reason (str), and regressions (list).
        """
        regressions: list[str] = []

        # Check scope compatibility
        if b1.scope != b2.scope:
            return {
                "compatible": False,
                "reason": f"Scope mismatch: '{b1.scope}' vs '{b2.scope}'",
                "regressions": ["scope_mismatch"],
            }

        # Check explicit compatibility declarations
        if b2.version not in b1.compatible_with and b1.version not in b2.compatible_with:
            # This is a warning, not a hard block — compatibility may be implicit
            regressions.append("no_explicit_compatibility_declaration")

        # Check gate score regressions in critical gates
        CRITICAL_GATES = {"G2", "G6", "G7"}
        for gate_id in CRITICAL_GATES:
            g1 = b1.gates_results.get(gate_id, {})
            g2 = b2.gates_results.get(gate_id, {})
            if isinstance(g1, dict) and isinstance(g2, dict):
                score1 = g1.get("score", 0.0)
                score2 = g2.get("score", 0.0)
                if score2 < score1 - 0.15:
                    regressions.append(
                        f"{gate_id} score dropped from {score1:.2f} to {score2:.2f}"
                    )

        compatible = len([r for r in regressions if r != "no_explicit_compatibility_declaration"]) == 0
        reason = "Compatible" if compatible else "; ".join(regressions)

        return {
            "compatible": compatible,
            "reason": reason,
            "regressions": regressions,
        }


class KillSwitchManager:
    """Manages kill-switch activation/deactivation per scope.

    Kill switches halt trading for specific model scopes.
    """

    def __init__(self) -> None:
        self._switches: dict[str, KillSwitch] = {}

    def activate(
        self,
        scope: str,
        reason: str = "",
        activated_by: str = "system",
    ) -> KillSwitch:
        """Activate the kill switch for a scope.

        Args:
            scope: The model scope to halt.
            reason: Reason for activation.
            activated_by: Who/what activated the switch.

        Returns:
            The activated KillSwitch.
        """
        switch = KillSwitch(
            active=True,
            scope=scope,
            reason=reason,
            activated_at=_now_ts(),
            activated_by=activated_by,
        )
        self._switches[scope] = switch
        return switch

    def deactivate(self, scope: str) -> KillSwitch | None:
        """Deactivate the kill switch for a scope.

        Args:
            scope: The model scope to resume.

        Returns:
            The deactivated KillSwitch, or None if no switch existed.
        """
        existing = self._switches.get(scope)
        if existing is None:
            return None
        switch = KillSwitch(
            active=False,
            scope=scope,
            reason="Deactivated",
            activated_at=existing.activated_at,
            activated_by=existing.activated_by,
        )
        self._switches[scope] = switch
        return switch

    def is_active(self, scope: str) -> bool:
        """Check if kill switch is active for a scope.

        Args:
            scope: The model scope.

        Returns:
            True if the kill switch is active.
        """
        switch = self._switches.get(scope)
        return switch.active if switch else False

    def get_switch(self, scope: str) -> KillSwitch | None:
        """Get the current kill switch state for a scope.

        Args:
            scope: The model scope.

        Returns:
            The KillSwitch, or None if not registered.
        """
        return self._switches.get(scope)

    def active_scopes(self) -> list[str]:
        """Get list of scopes with active kill switches.

        Returns:
            List of scope strings where kill switch is active.
        """
        return [s for s, sw in self._switches.items() if sw.active]
