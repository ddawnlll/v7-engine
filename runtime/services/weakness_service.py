"""Weakness aggregation service for failure intelligence."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from runtime.db.repos.failure_repo import FailureRepository
from runtime.db.repos.runtime_profile_repo import PAPER_PROFILE_ID
from runtime.db.session import session_scope


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_date_from(lookback_days: int) -> str:
    days = max(1, int(lookback_days))
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


class WeaknessService:
    def __init__(self, failure_repo: FailureRepository | None = None) -> None:
        self.failure_repo = failure_repo or FailureRepository()

    def get_weakness_profile(
        self,
        lookback_days: int = 30,
        min_confidence: float = 0.6,
        profile_id: str = PAPER_PROFILE_ID,
    ) -> dict[str, Any]:
        with session_scope() as session:
            rows, _total = self.failure_repo.list_failures(
                session,
                limit=10_000,
                offset=0,
                date_from=_normalize_date_from(lookback_days),
                profile_id=profile_id,
            )

        filtered = [row for row in rows if float(row.get("confidence") or 0.0) >= float(min_confidence)]
        source_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        component_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)

        for row in filtered:
            source_groups[str(row.get("failure_source") or "UNKNOWN")].append(row)
            component_groups[str(row.get("blamed_component") or "UNKNOWN")].append(row)

        ranked_sources = [
            self._build_source_row(source, items)
            for source, items in source_groups.items()
        ]
        ranked_components = [
            self._build_component_row(component, items)
            for component, items in component_groups.items()
        ]
        ranked_sources.sort(key=lambda row: float(row["weight_score"]), reverse=True)
        ranked_components.sort(key=lambda row: float(row["weight_score"]), reverse=True)

        return {
            "generated_at": _utc_now_iso(),
            "lookback_days": max(1, int(lookback_days)),
            "min_confidence": float(min_confidence),
            "profile_id": profile_id,
            "total_losses_analyzed": len(filtered),
            "top_failure_source": ranked_sources[0]["failure_source"] if ranked_sources else None,
            "top_blamed_component": ranked_components[0]["blamed_component"] if ranked_components else None,
            "ranked_sources": ranked_sources,
            "ranked_components": ranked_components,
        }

    def _build_source_row(self, failure_source: str, items: list[dict[str, Any]]) -> dict[str, Any]:
        count = len(items)
        avg_severity = self._average(float(item.get("severity_score") or 0.0) for item in items)
        grouped_components: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for item in items:
            grouped_components[str(item.get("blamed_component") or "UNKNOWN")].append(item)
        component_rows = [
            self._build_component_row(component, component_items)
            for component, component_items in grouped_components.items()
        ]
        component_rows.sort(key=lambda row: float(row["weight_score"]), reverse=True)
        best_component = component_rows[0] if component_rows else None
        highest_confidence = max(items, key=lambda item: float(item.get("confidence") or 0.0))
        return {
            "failure_source": failure_source,
            "count": count,
            "avg_severity": avg_severity,
            "weight_score": round(count * avg_severity, 4),
            "top_component": best_component["blamed_component"] if best_component else None,
            "best_improvement": str(highest_confidence.get("improvement") or ""),
            "components": component_rows,
        }

    def _build_component_row(self, blamed_component: str, items: list[dict[str, Any]]) -> dict[str, Any]:
        count = len(items)
        avg_severity = self._average(float(item.get("severity_score") or 0.0) for item in items)
        avg_confidence = self._average(float(item.get("confidence") or 0.0) for item in items)
        highest_confidence = max(items, key=lambda item: float(item.get("confidence") or 0.0))
        top_source = self._most_common([str(item.get("failure_source") or "UNKNOWN") for item in items])
        return {
            "blamed_component": blamed_component,
            "count": count,
            "avg_severity": avg_severity,
            "avg_confidence": avg_confidence,
            "weight_score": round(count * avg_severity, 4),
            "top_failure_source": top_source,
            "best_improvement": str(highest_confidence.get("improvement") or ""),
        }

    @staticmethod
    def _average(values) -> float:
        values = list(values)
        if not values:
            return 0.0
        return round(sum(values) / len(values), 4)

    @staticmethod
    def _most_common(values: list[str]) -> str | None:
        if not values:
            return None
        counts: dict[str, int] = {}
        for value in values:
            counts[value] = counts.get(value, 0) + 1
        return max(counts.items(), key=lambda item: item[1])[0]
