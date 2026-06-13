"""Composite failure analytics service for the dedicated failures page."""

from __future__ import annotations

import csv
import io
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from runtime.db.models import Order, TradeFailure
from runtime.db.repos._helpers import loads_json
from runtime.db.repos.runtime_profile_repo import PAPER_PROFILE_ID
from runtime.db.session import session_scope


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _lookback_start(lookback_days: int | None) -> str | None:
    if lookback_days is None or int(lookback_days) <= 0:
        return None
    return (datetime.now(timezone.utc) - timedelta(days=int(lookback_days))).isoformat()


def _norm_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


class FailureAnalyticsService:
    def _base_rows(
        self,
        session: Session,
        *,
        lookback_days: int = 30,
        mode_filter: str | None = None,
        profile_id: str = PAPER_PROFILE_ID,
    ) -> list[dict[str, Any]]:
        query = (
            session.query(TradeFailure, Order)
            .outerjoin(Order, Order.order_id == TradeFailure.order_id)
            .filter(TradeFailure.profile_id == profile_id)
        )
        date_from = _lookback_start(lookback_days)
        if date_from:
            query = query.filter(TradeFailure.created_at_utc >= date_from)
        query = query.order_by(TradeFailure.created_at_utc.desc())

        rows: list[dict[str, Any]] = []
        for failure, order in query.all():
            payload = loads_json(order.payload_json, {}) if order is not None else {}
            fallback = self._simulation_context_fallback(failure)
            row = {
                    "order_id": failure.order_id,
                    "profile_id": getattr(failure, "profile_id", PAPER_PROFILE_ID),
                    "signal_id": failure.signal_id,
                    "symbol": order.symbol if order is not None else fallback.get("symbol"),
                    "interval": order.interval if order is not None else fallback.get("interval"),
                    "mode": order.mode if order is not None else fallback.get("mode"),
                    "realized_r": payload.get("realized_r") if order is not None else fallback.get("realized_r"),
                    "failure_source": failure.failure_source,
                    "blamed_component": failure.blamed_component,
                    "severity_score": failure.severity_score,
                    "confidence": failure.confidence,
                    "classification": failure.classification,
                    "explanation": failure.explanation,
                    "improvement": failure.improvement,
                    "created_at_utc": failure.created_at_utc,
                }
            if not mode_filter or row.get("mode") == mode_filter:
                rows.append(row)
        return rows

    @staticmethod
    def _simulation_context_fallback(failure: TradeFailure) -> dict[str, Any]:
        """Recover simulation trade context for synthetic failure rows.

        Live failures join to v4_orders for symbol/interval/mode/realized_r. Simulation
        analyzer rows do not have matching orders, so the analyzer stores compact context
        in signal_id for new rows and older rows can still recover partial context from
        explanation/order_id.
        """
        signal_id = str(getattr(failure, "signal_id", None) or "")
        if signal_id.startswith("simctx|"):
            parts = signal_id.split("|", 6)
            if len(parts) >= 7:
                return {
                    "symbol": parts[1] or None,
                    "interval": parts[2] or None,
                    "mode": parts[3] or None,
                    "direction": parts[4] or None,
                    "realized_r": FailureAnalyticsService._safe_float(parts[5]),
                    "pnl": FailureAnalyticsService._safe_float(parts[6]),
                }

        explanation = str(getattr(failure, "explanation", "") or "")
        match = re.search(
            r"losing\s+(?P<mode>[A-Z_]+)\s+(?P<direction>[A-Z]+)\s+trade\s+on\s+(?P<symbol>[A-Z0-9_\-]+);\s+pnl=(?P<pnl>-?[0-9.]+)",
            explanation,
            flags=re.IGNORECASE,
        )
        if match:
            pnl = FailureAnalyticsService._safe_float(match.group("pnl"))
            return {
                "symbol": match.group("symbol").upper(),
                "interval": None,
                "mode": match.group("mode").upper(),
                "direction": match.group("direction").upper(),
                "realized_r": pnl,
                "pnl": pnl,
            }

        order_id = str(getattr(failure, "order_id", "") or "")
        order_match = re.search(r"sim-\d+-[^-]+-(?P<symbol>[A-Z0-9_]+)-(?P<mode>[A-Z_]+)-(?P<direction>[A-Z]+)$", order_id)
        if order_match:
            return {
                "symbol": order_match.group("symbol"),
                "interval": None,
                "mode": order_match.group("mode"),
                "direction": order_match.group("direction"),
                "realized_r": None,
            }
        return {}

    @staticmethod
    def _safe_float(value: Any) -> float | None:
        try:
            parsed = float(value)
            return parsed if parsed == parsed else None
        except Exception:
            return None

    def _filtered_rows(
        self,
        session: Session,
        *,
        lookback_days: int = 30,
        mode_filter: str | None = None,
        min_confidence: float = 0.6,
        profile_id: str = PAPER_PROFILE_ID,
    ) -> list[dict[str, Any]]:
        rows = self._base_rows(session, lookback_days=lookback_days, mode_filter=mode_filter, profile_id=profile_id)
        return [row for row in rows if float(row.get("confidence") or 0.0) >= float(min_confidence)]

    def get_page_summary(self, lookback_days: int = 30, mode_filter: str | None = None, profile_id: str = PAPER_PROFILE_ID) -> dict[str, Any]:
        with session_scope() as session:
            rows = self._base_rows(session, lookback_days=lookback_days, mode_filter=mode_filter, profile_id=profile_id)
        return self._build_page_summary(rows)

    def get_source_breakdown(self, lookback_days: int = 30, mode_filter: str | None = None, profile_id: str = PAPER_PROFILE_ID) -> list[dict[str, Any]]:
        with session_scope() as session:
            rows = self._base_rows(session, lookback_days=lookback_days, mode_filter=mode_filter, profile_id=profile_id)
        return self._breakdown(rows, "failure_source")

    def get_component_breakdown(self, lookback_days: int = 30, mode_filter: str | None = None, profile_id: str = PAPER_PROFILE_ID) -> list[dict[str, Any]]:
        with session_scope() as session:
            rows = self._base_rows(session, lookback_days=lookback_days, mode_filter=mode_filter, profile_id=profile_id)
        return self._breakdown(rows, "blamed_component")

    def get_source_component_matrix(self, lookback_days: int = 30, mode_filter: str | None = None, profile_id: str = PAPER_PROFILE_ID) -> dict[str, Any]:
        with session_scope() as session:
            rows = self._base_rows(session, lookback_days=lookback_days, mode_filter=mode_filter, profile_id=profile_id)
        return self._build_source_component_matrix(rows)

    def get_severity_distribution(self, lookback_days: int = 30, mode_filter: str | None = None, profile_id: str = PAPER_PROFILE_ID) -> dict[str, Any]:
        with session_scope() as session:
            rows = self._base_rows(session, lookback_days=lookback_days, mode_filter=mode_filter, profile_id=profile_id)
        return self._build_severity_distribution(rows)

    def get_ranked_improvements(
        self,
        lookback_days: int = 30,
        mode_filter: str | None = None,
        min_confidence: float = 0.6,
        profile_id: str = PAPER_PROFILE_ID,
    ) -> list[dict[str, Any]]:
        with session_scope() as session:
            rows = self._filtered_rows(session, lookback_days=lookback_days, mode_filter=mode_filter, min_confidence=min_confidence, profile_id=profile_id)
        return self._build_ranked_improvements(rows)

    def get_recent_failures(
        self,
        lookback_days: int = 30,
        mode_filter: str | None = None,
        limit: int = 10,
        min_confidence: float = 0.0,
        profile_id: str = PAPER_PROFILE_ID,
    ) -> list[dict[str, Any]]:
        with session_scope() as session:
            rows = self._filtered_rows(session, lookback_days=lookback_days, mode_filter=mode_filter, min_confidence=min_confidence, profile_id=profile_id)
        return rows[: max(1, int(limit))]

    def get_payload(
        self,
        lookback_days: int = 30,
        mode_filter: str | None = None,
        min_confidence: float = 0.6,
        profile_id: str = PAPER_PROFILE_ID,
    ) -> dict[str, Any]:
        with session_scope() as session:
            all_rows = self._base_rows(session, lookback_days=lookback_days, mode_filter=mode_filter, profile_id=profile_id)
        filtered_rows = [row for row in all_rows if float(row.get("confidence") or 0.0) >= float(min_confidence)]
        page_summary = self._build_page_summary(filtered_rows)
        page_summary["total_losses"] = len(all_rows)
        ranked_improvements = self._build_ranked_improvements(filtered_rows)
        recent_failures = filtered_rows[:10]
        filtered_out_all = bool(all_rows) and not filtered_rows
        return {
            "ok": True,
            "filters": {
                "lookback_days": lookback_days,
                "mode": mode_filter,
                "min_confidence": min_confidence,
                "profile_id": profile_id,
            },
            "summary": page_summary,
            "source_breakdown": self._breakdown(filtered_rows, "failure_source"),
            "component_breakdown": self._breakdown(filtered_rows, "blamed_component"),
            "source_component_matrix": self._build_source_component_matrix(filtered_rows),
            "severity_distribution": self._build_severity_distribution(filtered_rows),
            "ranked_improvements": ranked_improvements,
            "recent_failures": recent_failures,
            "meta": {
                "generated_at": _utc_now_iso(),
                "has_meaningful_heatmap": page_summary["total_losses_analyzed"] >= 5,
                "all_filtered_out_by_confidence": filtered_out_all,
            },
        }

    def export_rows(
        self,
        lookback_days: int = 30,
        mode_filter: str | None = None,
        min_confidence: float | None = None,
        profile_id: str = PAPER_PROFILE_ID,
    ) -> list[dict[str, Any]]:
        with session_scope() as session:
            rows = self._base_rows(session, lookback_days=lookback_days, mode_filter=mode_filter, profile_id=profile_id)
        if min_confidence is None:
            return rows
        return [row for row in rows if float(row.get("confidence") or 0.0) >= float(min_confidence)]

    @staticmethod
    def _build_page_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
        analyzed = len(rows)
        total_losses = analyzed
        avg_realized_r = round(sum(float(row.get("realized_r") or 0.0) for row in rows) / analyzed, 4) if analyzed else 0.0
        source_counts = FailureAnalyticsService._count_by(rows, "failure_source")
        component_counts = FailureAnalyticsService._count_by(rows, "blamed_component")
        top_source, top_source_count = FailureAnalyticsService._top_count(source_counts)
        top_component, top_component_count = FailureAnalyticsService._top_count(component_counts)
        return {
            "total_losses_analyzed": analyzed,
            "total_losses": total_losses,
            "avg_realized_r": avg_realized_r,
            "top_failure_source": top_source,
            "top_failure_source_count": top_source_count,
            "top_blamed_component": top_component,
            "top_blamed_component_count": top_component_count,
        }

    @staticmethod
    def _build_source_component_matrix(rows: list[dict[str, Any]]) -> dict[str, Any]:
        sources = sorted({str(row.get("failure_source") or "UNKNOWN") for row in rows})
        components = sorted({str(row.get("blamed_component") or "UNKNOWN") for row in rows})
        matrix: dict[str, dict[str, int]] = {source: {component: 0 for component in components} for source in sources}
        for row in rows:
            matrix[str(row.get("failure_source"))][str(row.get("blamed_component"))] += 1
        return {
            "sources": sources,
            "components": components,
            "cells": matrix,
        }

    @staticmethod
    def _build_severity_distribution(rows: list[dict[str, Any]]) -> dict[str, Any]:
        total = len(rows)
        counts = {level: 0 for level in range(1, 6)}
        for row in rows:
            level = max(1, min(5, int(row.get("severity_score") or 0)))
            counts[level] += 1
        items = [
            {
                "severity": level,
                "count": counts[level],
                "percent": round((counts[level] / total) * 100, 4) if total else 0.0,
            }
            for level in range(1, 6)
        ]
        return {
            "items": items,
            "avg_severity": round(sum(float(row.get("severity_score") or 0.0) for row in rows) / total, 4) if total else 0.0,
            "avg_confidence": round(sum(float(row.get("confidence") or 0.0) for row in rows) / total, 4) if total else 0.0,
        }

    @staticmethod
    def _build_ranked_improvements(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            grouped[(str(row.get("failure_source")), str(row.get("blamed_component")))].append(row)

        ranked: list[dict[str, Any]] = []
        for (failure_source, blamed_component), items in grouped.items():
            count = len(items)
            avg_severity = round(sum(float(item.get("severity_score") or 0.0) for item in items) / count, 4) if count else 0.0
            avg_confidence = round(sum(float(item.get("confidence") or 0.0) for item in items) / count, 4) if count else 0.0
            best = max(items, key=lambda item: float(item.get("confidence") or 0.0))
            ranked.append(
                {
                    "failure_source": failure_source,
                    "blamed_component": blamed_component,
                    "weight_score": round(count * avg_severity, 4),
                    "count": count,
                    "avg_severity": avg_severity,
                    "avg_confidence": avg_confidence,
                    "improvement": str(best.get("improvement") or ""),
                }
            )

        ranked.sort(key=lambda row: float(row["weight_score"]), reverse=True)
        deduped: list[dict[str, Any]] = []
        seen_norms: set[str] = set()
        for row in ranked:
            normalized = _norm_text(str(row.get("improvement") or ""))
            if normalized and normalized in seen_norms:
                continue
            if normalized:
                seen_norms.add(normalized)
            deduped.append(row)
        return deduped

    @staticmethod
    def export_csv(rows: list[dict[str, Any]]) -> str:
        fieldnames = [
            "order_id",
            "symbol",
            "interval",
            "mode",
            "realized_r",
            "failure_source",
            "blamed_component",
            "severity_score",
            "confidence",
            "classification",
            "explanation",
            "improvement",
            "created_at_utc",
        ]
        out = io.StringIO()
        writer = csv.DictWriter(out, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in fieldnames})
        return out.getvalue()

    @staticmethod
    def _count_by(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
        counts: dict[str, int] = {}
        for row in rows:
            label = str(row.get(key) or "UNKNOWN")
            counts[label] = counts.get(label, 0) + 1
        return counts

    @staticmethod
    def _top_count(counts: dict[str, int]) -> tuple[str | None, int]:
        if not counts:
            return None, 0
        label, count = max(counts.items(), key=lambda item: item[1])
        return label, count

    @staticmethod
    def _breakdown(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
        counts = FailureAnalyticsService._count_by(rows, key)
        total = len(rows)
        items = [
            {
                "label": label,
                "count": count,
                "percent": round((count / total) * 100, 4) if total else 0.0,
            }
            for label, count in counts.items()
        ]
        items.sort(key=lambda row: row["count"], reverse=True)
        return items
