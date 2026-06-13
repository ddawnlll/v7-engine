"""Impact analytics for registered engine improvements."""

from __future__ import annotations

import csv
import io
import math
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from runtime.db.models import ImprovementChangeEvent, SignalComponentAttribution, TradeComponentOutcome
from runtime.db.repos._helpers import loads_json
from runtime.db.repos.runtime_profile_repo import PAPER_PROFILE_ID
from runtime.db.session import session_scope
from runtime.services.attribution_integrity_service import AttributionIntegrityService
from runtime.services.engine_manifest_service import EngineManifestService
from runtime.services.improvement_registry_service import ImprovementRegistryService


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_iso(value: Any):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


class ImprovementAnalyticsService:
    def __init__(
        self,
        registry_service: ImprovementRegistryService | None = None,
        manifest_service: EngineManifestService | None = None,
        attribution_integrity_service: AttributionIntegrityService | None = None,
    ) -> None:
        self.registry_service = registry_service or ImprovementRegistryService()
        self.manifest_service = manifest_service or EngineManifestService(self.registry_service)
        self.attribution_integrity_service = attribution_integrity_service or AttributionIntegrityService()

    def get_payload(
        self,
        *,
        lookback_days: int = 30,
        min_samples: int = 10,
        component_type: str | None = None,
        component_status: str | None = None,
        component_id: str | None = None,
        mode: str | None = None,
        symbol: str | None = None,
        interval: str | None = None,
        direction: str | None = None,
        regime: str | None = None,
        profile_id: str = PAPER_PROFILE_ID,
    ) -> dict[str, Any]:
        filters = {
            "component_type": component_type,
            "component_status": component_status,
            "component_id": component_id,
            "mode": mode,
            "symbol": symbol,
            "interval": interval,
            "direction": direction,
            "regime": regime,
        }
        self.registry_service.sync_registry()
        registry = self.registry_service.list_components(status=component_status, component_type=component_type)
        with session_scope() as session:
            outcomes = self._outcomes(session, lookback_days=lookback_days, filters=filters, profile_id=profile_id)
            changes = self._changes(session, lookback_days=lookback_days, filters=filters)
        current = outcomes
        prior = self._prior_window(outcomes, lookback_days)
        current = self._current_window(outcomes, lookback_days)
        attribution_integrity = self.attribution_integrity_service.evaluate(lookback_days=lookback_days)
        rollout_measurement = self.get_rollout_measurement(current, prior)
        return {
            "ok": True,
            "filters": {
                "lookback_days": lookback_days,
                "min_samples": min_samples,
                **filters,
                "profile_id": profile_id,
            },
            "overview": self.get_overview(registry, current, changes, min_samples=min_samples),
            "recent_changes": self.get_recent_changes(changes),
            "component_registry": self.get_component_registry(registry, current),
            "component_impact": self.get_component_impact(registry, current, min_samples=min_samples),
            "change_impact": self.get_change_impact(changes, current, prior, min_samples=min_samples),
            "combination_impact": self.get_combination_impact(current, min_samples=min_samples),
            "contextual_impact": self.get_contextual_impact(current, min_samples=min_samples),
            "recommendations": self.get_recommendations(registry, current, changes, min_samples=min_samples),
            "operator_alerts": self.get_operator_alerts(registry, current, changes, min_samples=min_samples),
            "comparison": self.get_comparison(current, prior, min_samples=min_samples),
            "rollout_measurement": rollout_measurement,
            "attribution_integrity": attribution_integrity,
            "safety_notes": self._safety_notes(attribution_integrity),
            "meta": {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "total_rows": len(current),
            },
        }

    def export_csv(self, **kwargs) -> str:
        payload = self.get_payload(**kwargs)
        rows = payload["component_impact"]["by_component"]
        out = io.StringIO()
        fieldnames = [
            "component_id", "label", "component_type", "status", "version", "trades_affected", "wins", "losses",
            "win_rate", "avg_realized_r", "net_r", "profit_factor", "avg_hold_minutes", "stop_hit_pct",
            "target_hit_pct", "max_drawdown_r", "expectancy_delta_vs_baseline", "confidence_delta_vs_baseline", "sample_reliability",
        ]
        writer = csv.DictWriter(out, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key) for key in fieldnames})
        return out.getvalue()

    def get_overview(self, registry: list[dict], rows: list[dict], changes: list[dict], *, min_samples: int) -> dict[str, Any]:
        impact = self.get_component_impact(registry, rows, min_samples=min_samples)["ranked_components"]
        best = impact[0] if impact else None
        worst = impact[-1] if impact else None
        return {
            "total_registered_components": len(registry),
            "active_components": sum(1 for item in registry if item.get("status") == "ACTIVE"),
            "experimental_components": sum(1 for item in registry if item.get("status") == "EXPERIMENTAL"),
            "components_changed_in_window": len({item["component_id"] for item in changes if item.get("component_id") != "__engine__"}),
            "promoted_components_in_window": sum(1 for item in changes if item.get("change_type") == "component_enabled"),
            "rolled_back_components_in_window": sum(1 for item in changes if item.get("change_type") == "component_disabled"),
            "best_improving_component": best["label"] if best else None,
            "worst_degrading_component": worst["label"] if worst else None,
        }

    @staticmethod
    def get_recent_changes(changes: list[dict]) -> dict[str, Any]:
        grouped = defaultdict(list)
        by_type = defaultdict(int)
        for item in changes:
            grouped[item["component_id"]].append(item)
            by_type[item["change_type"]] += 1
        return {
            "items": changes[:50],
            "by_component": {key: value[:10] for key, value in grouped.items()},
            "by_change_type": dict(by_type),
        }

    def get_component_registry(self, registry: list[dict], outcomes: list[dict]) -> dict[str, Any]:
        last_seen = {}
        first_seen = {}
        for row in outcomes:
            component_id = str(row.get("component_id") or "")
            created_at = str(row.get("created_at_utc") or "")
            if component_id not in first_seen or created_at < first_seen[component_id]:
                first_seen[component_id] = created_at
            if component_id not in last_seen or created_at > last_seen[component_id]:
                last_seen[component_id] = created_at
        items = []
        for row in registry:
            items.append({
                **row,
                "first_seen": first_seen.get(row["component_id"], row.get("introduced_at_utc")),
                "last_seen": last_seen.get(row["component_id"], row.get("updated_at_utc")),
            })
        return {"items": items}

    def get_component_impact(self, registry: list[dict], rows: list[dict], *, min_samples: int) -> dict[str, Any]:
        registry_by_id = {item["component_id"]: item for item in registry}
        grouped: dict[str, list[dict]] = defaultdict(list)
        for row in rows:
            grouped[str(row.get("component_id") or "")].append(row)
        impact_rows = []
        baseline_expectancy = sum(_as_float(row.get("realized_r")) for row in rows) / max(len(rows), 1) if rows else 0.0
        baseline_confidence = sum(_as_float(row.get("confidence")) for row in rows) / max(len(rows), 1) if rows else 0.0
        for component_id, component_rows in grouped.items():
            meta = registry_by_id.get(component_id, {"component_id": component_id, "component_name": component_id, "component_type": "UNKNOWN", "status": "UNKNOWN", "version": "unknown", "owner": "system"})
            impact_rows.append(self._impact_row(meta, component_rows, baseline_expectancy=baseline_expectancy, baseline_confidence=baseline_confidence, min_samples=min_samples))
        impact_rows.sort(key=lambda item: (item["provisional"], -_as_float(item["expectancy_delta_vs_baseline"]), -_as_float(item["avg_realized_r"])))
        by_type = self._aggregate_group(impact_rows, "component_type")
        by_status = self._aggregate_group(impact_rows, "status")
        by_version = self._aggregate_group(impact_rows, "version")
        return {
            "by_component": impact_rows,
            "ranked_components": [row for row in impact_rows if not row["provisional"]],
            "provisional_components": [row for row in impact_rows if row["provisional"]],
            "by_component_type": by_type,
            "by_status": by_status,
            "by_version": by_version,
        }

    def get_change_impact(self, changes: list[dict], current_rows: list[dict], prior_rows: list[dict], *, min_samples: int) -> dict[str, Any]:
        current_by_component = defaultdict(list)
        prior_by_component = defaultdict(list)
        for row in current_rows:
            current_by_component[str(row.get("component_id") or "")].append(row)
        for row in prior_rows:
            prior_by_component[str(row.get("component_id") or "")].append(row)
        items = []
        for change in changes:
            component_id = str(change.get("component_id") or "")
            before = prior_by_component.get(component_id, [])
            after = current_by_component.get(component_id, [])
            if len(before) + len(after) <= 0:
                continue
            items.append({
                **change,
                "trades_before": len(before),
                "trades_after": len(after),
                "avg_r_before": self._avg_r(before),
                "avg_r_after": self._avg_r(after),
                "expectancy_delta": round(self._avg_r(after) - self._avg_r(before), 4),
                "confounded": len(changes) > 1,
                "sample_reliability": self._sample_reliability(len(after), min_samples),
            })
        return {"items": items}

    def get_combination_impact(self, rows: list[dict], *, min_samples: int) -> dict[str, Any]:
        by_trade: dict[str, list[dict]] = defaultdict(list)
        for row in rows:
            by_trade[str(row.get("order_id") or row.get("signal_id") or "")].append(row)
        grouped: dict[str, list[dict]] = defaultdict(list)
        for trade_rows in by_trade.values():
            components = sorted({str(item.get("component_id") or "") for item in trade_rows})
            if len(components) < 2:
                continue
            combo = " + ".join(components[:3])
            grouped[combo].append(trade_rows[0])
        items = []
        for label, group_rows in grouped.items():
            trades = len(group_rows)
            items.append({
                "label": label,
                "trades_affected": trades,
                "avg_realized_r": self._avg_r(group_rows),
                "sample_reliability": self._sample_reliability(trades, min_samples),
                "provisional": trades < min_samples,
            })
        items.sort(key=lambda item: (item["provisional"], -_as_float(item["avg_realized_r"])))
        return {
            "best_combinations": [item for item in items if not item["provisional"]][:10],
            "worst_combinations": list(reversed([item for item in items if not item["provisional"]][-10:])),
        }

    def get_contextual_impact(self, rows: list[dict], *, min_samples: int) -> dict[str, Any]:
        return {
            "by_mode": self._group_context(rows, "mode", min_samples=min_samples),
            "by_regime": self._group_context(rows, "regime", min_samples=min_samples),
            "by_direction": self._group_context(rows, "direction", min_samples=min_samples),
            "by_session": self._group_context(rows, "session_label", min_samples=min_samples),
            "by_confidence_bucket": self._group_context(rows, "confidence_bucket", min_samples=min_samples),
        }

    def get_rollout_comparison(self, component_id: str, before_window: list[dict], after_window: list[dict], *, min_samples: int) -> dict[str, Any]:
        before = [row for row in before_window if str(row.get("component_id") or "") == component_id]
        after = [row for row in after_window if str(row.get("component_id") or "") == component_id]
        return {
            "component_id": component_id,
            "baseline_window": {"trades": len(before), "avg_realized_r": self._avg_r(before)},
            "post_change_window": {"trades": len(after), "avg_realized_r": self._avg_r(after)},
            "absolute_delta": round(self._avg_r(after) - self._avg_r(before), 4),
            "relative_delta": round((self._avg_r(after) - self._avg_r(before)) / max(abs(self._avg_r(before)), 0.01), 4) if before else None,
            "matched_sample_note": "rollout-linked comparison, not proof of causation",
            "sample_reliability": self._sample_reliability(len(after), min_samples),
        }

    def get_recommendations(self, registry: list[dict], rows: list[dict], changes: list[dict], *, min_samples: int) -> dict[str, Any]:
        impact = self.get_component_impact(registry, rows, min_samples=min_samples)["by_component"]
        promote = [self._recommend(row, "PROMOTE", "positive expectancy delta with stable sample") for row in impact if not row["provisional"] and _as_float(row["expectancy_delta_vs_baseline"]) > 0.2][:3]
        rollback = [self._recommend(row, "ROLLBACK", "expectancy turned negative after rollout") for row in impact if not row["provisional"] and _as_float(row["expectancy_delta_vs_baseline"]) < -0.2][:3]
        experimental = [self._recommend(row, "KEEP_EXPERIMENTAL", "component helping but still low sample") for row in impact if row["provisional"] and _as_float(row["avg_realized_r"]) > 0][:3]
        investigate = [self._recommend(row, "INVESTIGATE", "two changes landed together and cannot be separated cleanly") for row in impact if not row["provisional"] and len(changes) > 1][:3]
        return {
            "promote_now": promote,
            "keep_experimental": experimental,
            "pause_or_rollback": rollback,
            "investigate": investigate,
        }

    def get_operator_alerts(self, registry: list[dict], rows: list[dict], changes: list[dict], *, min_samples: int) -> list[dict[str, Any]]:
        alerts = []
        impact = self.get_component_impact(registry, rows, min_samples=min_samples)["by_component"]
        for row in impact:
            if row["sample_reliability"] == "LOW_SAMPLE" and _as_float(row["avg_realized_r"]) > 0:
                alerts.append({"severity": "warning", "message": f"{row['label']} is positive but still low sample."})
            if row["sample_reliability"] == "STABLE" and _as_float(row["avg_realized_r"]) < 0:
                alerts.append({"severity": "critical", "message": f"{row['label']} is degrading expectancy on a stable sample."})
        if len(changes) > 1:
            alerts.append({"severity": "warning", "message": "Multiple engine changes landed in the same window; results may be confounded."})
        return alerts[:10]

    @staticmethod
    def _safety_notes(attribution_integrity: dict[str, Any]) -> list[str]:
        if attribution_integrity.get("provisional"):
            return [f"Component-level impact remains provisional until attribution integrity is healthy. {attribution_integrity.get('summary')}"]
        return []

    def get_comparison(self, current: list[dict], prior: list[dict], *, min_samples: int) -> dict[str, Any]:
        current_map = self.get_component_impact(self.registry_service.list_components(), current, min_samples=min_samples)["by_component"]
        prior_map = {row["component_id"]: row for row in self.get_component_impact(self.registry_service.list_components(), prior, min_samples=min_samples)["by_component"]}
        improving = []
        degrading = []
        emerging = []
        broken = []
        for row in current_map:
            previous = prior_map.get(row["component_id"])
            if previous is None:
                if not row["provisional"] and _as_float(row["avg_realized_r"]) > 0:
                    emerging.append({"label": row["label"], "delta_avg_r": row["avg_realized_r"]})
                continue
            delta = _as_float(row["avg_realized_r"]) - _as_float(previous.get("avg_realized_r"))
            item = {"label": row["label"], "delta_avg_r": round(delta, 4), "current": row, "prior": previous}
            if delta > 0.1:
                improving.append(item)
            elif delta < -0.1:
                degrading.append(item)
            if _as_float(previous.get("avg_realized_r")) > 0 and _as_float(row["avg_realized_r"]) < 0:
                broken.append(item)
        edge_decay = bool(broken)
        return {
            "improving_components": improving[:5],
            "degrading_components": degrading[:5],
            "emerging_components": emerging[:5],
            "recently_broken_components": broken[:5],
            "edge_decay_warning": edge_decay,
        }

    def get_rollout_measurement(self, current: list[dict[str, Any]], prior: list[dict[str, Any]]) -> dict[str, Any]:
        current_manifest = self._latest_manifest_for_rows(current)
        prior_manifest = self._latest_manifest_for_rows(prior)
        return {
            "current_window": {
                "manifest": current_manifest,
                "run_count": len({str(row.get("run_id") or "") for row in current if row.get("run_id")}),
                "trade_count": len(current),
            },
            "prior_window": {
                "manifest": prior_manifest,
                "run_count": len({str(row.get("run_id") or "") for row in prior if row.get("run_id")}),
                "trade_count": len(prior),
            },
            "frozen_config_snapshot": {
                "current_param_hash": (current_manifest or {}).get("param_hash"),
                "prior_param_hash": (prior_manifest or {}).get("param_hash"),
                "config_changed": bool(current_manifest and prior_manifest and current_manifest.get("param_hash") != prior_manifest.get("param_hash")),
            },
        }

    def _outcomes(
        self,
        session: Session,
        *,
        lookback_days: int,
        filters: dict[str, Any],
        profile_id: str = PAPER_PROFILE_ID,
    ) -> list[dict[str, Any]]:
        query = session.query(TradeComponentOutcome).filter(TradeComponentOutcome.profile_id == profile_id)
        if lookback_days > 0:
            threshold = (datetime.now(timezone.utc) - timedelta(days=int(lookback_days) * 2)).isoformat()
            query = query.filter(TradeComponentOutcome.created_at_utc >= threshold)
        if filters.get("component_id"):
            query = query.filter(TradeComponentOutcome.component_id == filters["component_id"])
        if filters.get("mode"):
            query = query.filter(TradeComponentOutcome.mode == filters["mode"])
        if filters.get("symbol"):
            query = query.filter(TradeComponentOutcome.symbol == filters["symbol"])
        if filters.get("interval"):
            query = query.filter(TradeComponentOutcome.interval == filters["interval"])
        if filters.get("direction"):
            query = query.filter(TradeComponentOutcome.direction == filters["direction"])
        if filters.get("regime"):
            query = query.filter(TradeComponentOutcome.regime == filters["regime"])
        rows = query.order_by(TradeComponentOutcome.created_at_utc.desc()).all()
        result = []
        for row in rows:
            payload = loads_json(row.payload_json, {})
            result.append({
                "order_id": row.order_id,
                "profile_id": getattr(row, "profile_id", PAPER_PROFILE_ID),
                "signal_id": row.signal_id,
                "run_id": row.run_id,
                "component_id": row.component_id,
                "mode": row.mode,
                "symbol": row.symbol,
                "interval": row.interval,
                "direction": row.direction,
                "regime": row.regime,
                "session_label": payload.get("session_label"),
                "confidence": row.confidence,
                "confidence_bucket": self._confidence_bucket(row.confidence),
                "realized_r": row.realized_r,
                "close_reason": row.close_reason,
                "failure_source": row.failure_source,
                "blamed_component": row.blamed_component,
                "created_at_utc": row.created_at_utc,
                "payload": payload,
            })
        return result

    def _changes(self, session: Session, *, lookback_days: int, filters: dict[str, Any]) -> list[dict[str, Any]]:
        query = session.query(ImprovementChangeEvent)
        if lookback_days > 0:
            threshold = (datetime.now(timezone.utc) - timedelta(days=int(lookback_days))).isoformat()
            query = query.filter(ImprovementChangeEvent.effective_at_utc >= threshold)
        if filters.get("component_id"):
            query = query.filter(ImprovementChangeEvent.component_id == filters["component_id"])
        rows = query.order_by(ImprovementChangeEvent.effective_at_utc.desc()).all()
        return [self.manifest_service._change_to_dict(row) for row in rows]

    @staticmethod
    def _avg_r(rows: list[dict[str, Any]]) -> float:
        return sum(_as_float(row.get("realized_r")) for row in rows) / max(len(rows), 1) if rows else 0.0

    @staticmethod
    def _profit_factor(rows: list[dict[str, Any]]) -> float:
        gross_profit = sum(max(_as_float(row.get("realized_r")), 0.0) for row in rows)
        gross_loss = sum(abs(min(_as_float(row.get("realized_r")), 0.0)) for row in rows)
        if gross_loss <= 0:
            return gross_profit if gross_profit > 0 else 0.0
        return gross_profit / gross_loss

    @staticmethod
    def _max_drawdown(rows: list[dict[str, Any]]) -> float:
        equity = 0.0
        peak = 0.0
        max_drawdown = 0.0
        for row in sorted(rows, key=lambda item: str(item.get("created_at_utc") or "")):
            equity += _as_float(row.get("realized_r"))
            peak = max(peak, equity)
            max_drawdown = min(max_drawdown, equity - peak)
        return abs(max_drawdown)

    def _impact_row(self, meta: dict[str, Any], rows: list[dict], *, baseline_expectancy: float, baseline_confidence: float, min_samples: int) -> dict[str, Any]:
        trades = len(rows)
        wins = sum(1 for row in rows if _as_float(row.get("realized_r")) > 0.0)
        losses = sum(1 for row in rows if _as_float(row.get("realized_r")) < 0.0)
        avg_hold = sum(_as_float((row.get("payload") or {}).get("hold_minutes")) for row in rows) / max(trades, 1) if rows else 0.0
        avg_confidence = sum(_as_float(row.get("confidence")) for row in rows) / max(trades, 1) if rows else 0.0
        return {
            "component_id": meta["component_id"],
            "label": meta.get("ui_label") or meta.get("component_name") or meta["component_id"],
            "component_type": meta.get("component_type"),
            "status": meta.get("status"),
            "version": meta.get("version"),
            "owner": meta.get("owner"),
            "trades_affected": trades,
            "wins": wins,
            "losses": losses,
            "win_rate": wins / trades if trades else 0.0,
            "avg_realized_r": self._avg_r(rows),
            "net_r": sum(_as_float(row.get("realized_r")) for row in rows),
            "profit_factor": self._profit_factor(rows),
            "avg_hold_minutes": avg_hold,
            "stop_hit_pct": sum(1 for row in rows if str(row.get("close_reason") or "") == "HIT_SL") / trades if trades else 0.0,
            "target_hit_pct": sum(1 for row in rows if str(row.get("close_reason") or "") == "HIT_TP") / trades if trades else 0.0,
            "max_drawdown_r": self._max_drawdown(rows),
            "expectancy_delta_vs_baseline": round(self._avg_r(rows) - baseline_expectancy, 4),
            "confidence_delta_vs_baseline": round(avg_confidence - baseline_confidence, 4),
            "sample_reliability": self._sample_reliability(trades, min_samples),
            "provisional": trades < min_samples,
            "failure_source_distribution": self._distribution(rows, "failure_source"),
            "blamed_component_distribution": self._distribution(rows, "blamed_component"),
        }

    @staticmethod
    def _aggregate_group(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
        grouped = defaultdict(list)
        for row in rows:
            grouped[str(row.get(key) or "UNKNOWN")].append(row)
        items = []
        for label, group in grouped.items():
            items.append({
                "label": label,
                "trades_affected": sum(int(item.get("trades_affected") or 0) for item in group),
                "avg_realized_r": sum(_as_float(item.get("avg_realized_r")) * max(int(item.get("trades_affected") or 0), 1) for item in group) / max(sum(int(item.get("trades_affected") or 0) for item in group), 1),
            })
        items.sort(key=lambda item: -_as_float(item["avg_realized_r"]))
        return items

    @staticmethod
    def _group_context(rows: list[dict[str, Any]], field: str, *, min_samples: int) -> list[dict[str, Any]]:
        grouped = defaultdict(list)
        for row in rows:
            grouped[str(row.get(field) or "UNKNOWN")].append(row)
        items = []
        for label, group in grouped.items():
            trades = len(group)
            items.append({
                "label": label,
                "trades": trades,
                "avg_realized_r": sum(_as_float(item.get("realized_r")) for item in group) / max(trades, 1),
                "win_rate": sum(1 for item in group if _as_float(item.get("realized_r")) > 0) / max(trades, 1),
                "sample_reliability": ImprovementAnalyticsService._sample_reliability(trades, min_samples),
                "provisional": trades < min_samples,
            })
        items.sort(key=lambda item: (item["provisional"], -_as_float(item["avg_realized_r"])))
        return items

    @staticmethod
    def _sample_reliability(trades: int, min_samples: int) -> str:
        if trades < max(3, min_samples // 2):
            return "LOW_SAMPLE"
        if trades < min_samples:
            return "BUILDING_SAMPLE"
        if trades < (min_samples * 2):
            return "MIXED"
        return "STABLE"

    @staticmethod
    def _distribution(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
        grouped = defaultdict(int)
        for row in rows:
            label = str(row.get(key) or "UNKNOWN")
            grouped[label] += 1
        return dict(grouped)

    @staticmethod
    def _recommend(row: dict[str, Any], action: str, reason: str) -> dict[str, Any]:
        return {
            "component_id": row["component_id"],
            "label": row["label"],
            "action": action,
            "reason_summary": reason,
            "avg_realized_r": row["avg_realized_r"],
            "expectancy_delta_vs_baseline": row["expectancy_delta_vs_baseline"],
            "sample_reliability": row["sample_reliability"],
        }

    @staticmethod
    def _current_window(rows: list[dict[str, Any]], lookback_days: int) -> list[dict[str, Any]]:
        if lookback_days <= 0:
            return rows
        cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
        return [row for row in rows if (_parse_iso(row.get("created_at_utc")) or datetime.min.replace(tzinfo=timezone.utc)) >= cutoff]

    @staticmethod
    def _prior_window(rows: list[dict[str, Any]], lookback_days: int) -> list[dict[str, Any]]:
        if lookback_days <= 0:
            return []
        current_cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
        prior_cutoff = current_cutoff - timedelta(days=lookback_days)
        return [
            row
            for row in rows
            if prior_cutoff <= (_parse_iso(row.get("created_at_utc")) or datetime.min.replace(tzinfo=timezone.utc)) < current_cutoff
        ]

    @staticmethod
    def _confidence_bucket(value: float | None) -> str:
        confidence = _as_float(value)
        floor = int(max(0, min(90, math.floor(confidence / 10.0) * 10)))
        return f"{floor}-{floor + 10}"

    def _latest_manifest_for_rows(self, rows: list[dict[str, Any]]) -> dict[str, Any] | None:
        seen: set[tuple[str, str]] = set()
        for row in rows:
            run_id = str(row.get("run_id") or "")
            profile_id = str(row.get("profile_id") or PAPER_PROFILE_ID)
            if not run_id or (run_id, profile_id) in seen:
                continue
            seen.add((run_id, profile_id))
            manifest = self.manifest_service.get_manifest(run_id, profile_id=profile_id)
            if manifest:
                return manifest
        return None
