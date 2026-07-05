"""
Shadow mode implementation — execute shadow decisions alongside proposed
decisions, detect degradation, and produce shadow records.

Domain rules:
- Shadow execution observes live market without placing orders.
- Each shadow record compares proposed vs shadow decisions.
- Degradation detection triggers when shadow diverges materially from proposed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class ShadowRecord:
    """Record of a single shadow execution.

    Attributes:
        timestamp: When the shadow was executed.
        model_scope: The model scope being shadowed.
        proposed_decision: The decision the model would have made.
        shadow_decision: The actual shadow observation decision.
        comparison: Comparison result: 'MATCH', 'DIVERGE', or 'ERROR'.
        divergence_r: Magnitude of divergence in R units (0 if match).
        proposed_confidence: Confidence of the proposed decision.
        shadow_confidence: Confidence of the shadow decision.
        detail: Human-readable detail about this shadow record.
    """

    timestamp: str = ""
    model_scope: str = ""
    proposed_decision: str = ""
    shadow_decision: str = ""
    comparison: str = "MATCH"
    divergence_r: float = 0.0
    proposed_confidence: float = 0.0
    shadow_confidence: float = 0.0
    detail: str = ""


@dataclass(frozen=True)
class ShadowDegradationReport:
    """Report of shadow degradation analysis.

    Attributes:
        total_records: Number of shadow records analyzed.
        match_count: Number of records where proposed == shadow.
        diverge_count: Number of records where proposed != shadow.
        match_rate: Fraction of records that matched.
        avg_divergence_r: Average divergence magnitude in R.
        max_divergence_r: Maximum divergence magnitude in R.
        degradation_detected: True if degradation threshold exceeded.
        detail: Human-readable summary.
    """

    total_records: int = 0
    match_count: int = 0
    diverge_count: int = 0
    match_rate: float = 0.0
    avg_divergence_r: float = 0.0
    max_divergence_r: float = 0.0
    degradation_detected: bool = False
    detail: str = ""


def _default_ts() -> str:
    return datetime.now(timezone.utc).isoformat()


class ShadowModeManager:
    """Manages shadow execution for model scopes.

    Maintains shadow records per model_scope and provides
    degradation detection.
    """

    def __init__(self) -> None:
        self._records: dict[str, list[ShadowRecord]] = {}

    def execute_shadow(
        self,
        proposed_decision: dict[str, Any],
        model_scope: str,
        *,
        shadow_pipeline: Any = None,
    ) -> ShadowRecord:
        """Execute a shadow observation for a proposed decision.

        In the current implementation, the shadow decision is derived
        from the proposed decision's metadata. When a real shadow pipeline
        is provided, it is used for actual market observation.

        Args:
            proposed_decision: Dict with decision fields (decision, confidence,
                              expected_r, symbol, etc.).
            model_scope: The model scope being shadowed.
            shadow_pipeline: Optional shadow observation pipeline (reserved).

        Returns:
            A ShadowRecord with the comparison result.
        """
        proposed_decision_value = proposed_decision.get("decision", "NO_TRADE")
        proposed_confidence = proposed_decision.get("confidence", 0.0)

        # In baseline, shadow mirrors the proposed decision (no real pipeline)
        # A real shadow pipeline would observe the market and produce an
        # independent decision.
        if shadow_pipeline is not None:
            shadow_result = shadow_pipeline.observe(proposed_decision)
            shadow_decision = shadow_result.get("decision", proposed_decision_value)
            shadow_confidence = shadow_result.get("confidence", proposed_confidence)
        else:
            shadow_decision = proposed_decision_value
            shadow_confidence = proposed_confidence

        # Compare decisions
        if proposed_decision_value == shadow_decision:
            comparison = "MATCH"
            divergence_r = 0.0
            detail = "Shadow decision matches proposed decision"
        else:
            comparison = "DIVERGE"
            # Estimate divergence from expected R difference
            proposed_expected_r = proposed_decision.get("expected_r", 0.0)
            shadow_expected_r = proposed_decision.get("shadow_expected_r", 0.0)
            divergence_r = abs(proposed_expected_r - shadow_expected_r)
            detail = (
                f"Shadow diverged: proposed={proposed_decision_value}, "
                f"shadow={shadow_decision}, "
                f"divergence_r={divergence_r:.4f}"
            )

        record = ShadowRecord(
            timestamp=_default_ts(),
            model_scope=model_scope,
            proposed_decision=proposed_decision_value,
            shadow_decision=shadow_decision,
            comparison=comparison,
            divergence_r=round(divergence_r, 4),
            proposed_confidence=round(proposed_confidence, 4),
            shadow_confidence=round(shadow_confidence, 4),
            detail=detail,
        )

        if model_scope not in self._records:
            self._records[model_scope] = []
        self._records[model_scope].append(record)
        return record

    def get_records(
        self,
        model_scope: str,
        *,
        limit: int = 0,
    ) -> list[ShadowRecord]:
        """Get shadow records for a model scope.

        Args:
            model_scope: The model scope.
            limit: Max records to return (0 = all).

        Returns:
            List of ShadowRecords, newest first.
        """
        records = list(self._records.get(model_scope, []))
        records.reverse()
        if limit > 0:
            return records[:limit]
        return records

    def clear_records(self, model_scope: str) -> None:
        """Clear all shadow records for a model scope.

        Args:
            model_scope: The model scope.
        """
        self._records[model_scope] = []

    def detect_shadow_degradation(
        self,
        records: list[ShadowRecord] | None = None,
        *,
        model_scope: str = "",
        divergence_threshold: float = 0.3,
        max_diverge_rate: float = 0.2,
    ) -> ShadowDegradationReport:
        """Detect shadow degradation from a set of records.

        Degradation is detected when:
          - Divergence rate exceeds max_diverge_rate
          - Average divergence exceeds divergence_threshold
          - Max divergence is critically high (> 2.0 R)

        Args:
            records: List of ShadowRecords. If None, uses stored records.
            model_scope: If set and records is None, uses stored records for scope.
            divergence_threshold: Avg divergence R threshold for degradation.
            max_diverge_rate: Max allowed divergence rate.

        Returns:
            A ShadowDegradationReport with degradation analysis.
        """
        if records is None:
            if model_scope:
                records = self._records.get(model_scope, [])
            else:
                # Flatten all records across all scopes
                all_records: list[ShadowRecord] = []
                for recs in self._records.values():
                    all_records.extend(recs)
                records = all_records

        total = len(records)
        if total == 0:
            return ShadowDegradationReport(
                detail="No shadow records available for degradation analysis",
            )

        matches = [r for r in records if r.comparison == "MATCH"]
        diverges = [r for r in records if r.comparison == "DIVERGE"]
        match_count = len(matches)
        diverge_count = len(diverges)
        match_rate = match_count / total if total > 0 else 0.0

        divergence_r_values = [r.divergence_r for r in diverges] if diverges else [0.0]
        avg_divergence = sum(divergence_r_values) / len(divergence_r_values)
        max_divergence = max(divergence_r_values)

        diverge_rate = diverge_count / max(total, 1)
        degradation_detected = (
            diverge_rate > max_diverge_rate
            or avg_divergence > divergence_threshold
            or max_divergence > 2.0
        )

        detail_parts: list[str] = [
            f"match_rate={match_rate:.1%}",
            f"diverge_rate={diverge_rate:.1%}",
            f"avg_divergence_r={avg_divergence:.4f}",
            f"max_divergence_r={max_divergence:.4f}",
        ]
        if degradation_detected:
            detail_parts.append("DEGRADATION DETECTED")

        return ShadowDegradationReport(
            total_records=total,
            match_count=match_count,
            diverge_count=diverge_count,
            match_rate=round(match_rate, 4),
            avg_divergence_r=round(avg_divergence, 4),
            max_divergence_r=round(max_divergence, 4),
            degradation_detected=degradation_detected,
            detail=" | ".join(detail_parts),
        )
