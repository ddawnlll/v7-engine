from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text

from runtime.db.session import session_scope
from runtime.services.observability import log_event
from v6.config import V6Config
from v6.evaluation.shadow_compare import compare_shadow_events
from v6.registry.model_registry import ModelRegistry


@dataclass(slots=True)
class RuntimeAlertRecord:
    alert_id: str
    severity: str
    kind: str
    scope: str
    message: str
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "alert_id": self.alert_id,
            "severity": self.severity,
            "kind": self.kind,
            "scope": self.scope,
            "message": self.message,
            "payload": self.payload,
        }


class V6RuntimeMetricsService:
    def __init__(self, config: V6Config, registry: ModelRegistry | None = None) -> None:
        self.config = config
        self.registry = registry or ModelRegistry()

    def get_metrics(self) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        hour_ago = (now - timedelta(hours=1)).isoformat()
        day_ago = (now - timedelta(hours=24)).isoformat()
        lookback_limit = self.config.phase8.metrics_recent_scan_limit

        with session_scope() as session:
            try:
                events_1h = session.execute(
                    text("SELECT fallback_used, degraded_reason, deterministic_block FROM decision_events WHERE timestamp_utc >= :ts"),
                    {"ts": hour_ago},
                ).mappings().all()
                events_24h = session.execute(
                    text("SELECT fallback_used, degraded_reason, deterministic_block FROM decision_events WHERE timestamp_utc >= :ts ORDER BY timestamp_utc DESC LIMIT :limit"),
                    {"ts": day_ago, "limit": lookback_limit},
                ).mappings().all()
            except Exception:
                events_1h = []
                events_24h = []
            try:
                pending_row = session.execute(
                    text("SELECT COUNT(*) AS total FROM trade_outcomes WHERE outcome_status = 'PENDING'"),
                ).mappings().first()
                resolved_row = session.execute(
                    text("SELECT COUNT(*) AS total FROM trade_outcomes WHERE outcome_status = 'RESOLVED'"),
                ).mappings().first()
            except Exception:
                pending_row = {"total": 0}
                resolved_row = {"total": 0}

        fallback_rate_1h = self._rate(events_1h, lambda row: bool(row.get("fallback_used")))
        fallback_rate_24h = self._rate(events_24h, lambda row: bool(row.get("fallback_used")))
        timeout_rate_24h = self._rate(events_24h, self._is_timeout)
        block_rate_24h = self._rate(events_24h, lambda row: bool(row.get("deterministic_block")))
        try:
            divergence_report = compare_shadow_events(date_from=day_ago)
        except Exception:
            class _Empty:
                divergence_rate = 0.0
                pair_count = 0
            divergence_report = _Empty()
        champion = self.registry.get_champion()
        champion_age_days = self._champion_age_days(champion)

        return {
            "fallback_rate_1h": fallback_rate_1h,
            "fallback_rate_24h": fallback_rate_24h,
            "timeout_rate_24h": timeout_rate_24h,
            "hard_block_rate_24h": block_rate_24h,
            "divergence_rate_24h": divergence_report.divergence_rate,
            "shadow_pair_count_24h": divergence_report.pair_count,
            "champion_model_age_days": champion_age_days,
            "champion_model_artifact_version": champion.model_artifact_version if champion else None,
            "pending_outcome_count": int((pending_row or {}).get("total") or 0),
            "resolved_outcome_count": int((resolved_row or {}).get("total") or 0),
        }

    def build_alerts(self) -> list[RuntimeAlertRecord]:
        metrics = self.get_metrics()
        alerts: list[RuntimeAlertRecord] = []

        def add(kind: str, message: str, payload: dict[str, Any], severity: str = "warning") -> None:
            record = RuntimeAlertRecord(
                alert_id=f"v6-{kind}",
                severity=severity,
                kind=kind,
                scope="v6-runtime",
                message=message,
                payload=payload,
            )
            log_event("engine.health_check_failed", kind=kind, **payload)
            alerts.append(record)

        if metrics["fallback_rate_24h"] >= self.config.phase8.alert_fallback_rate_threshold:
            add(
                "v6_fallback_rate",
                "V6 fallback rate exceeded configured threshold.",
                {
                    "current_rate": metrics["fallback_rate_24h"],
                    "threshold": self.config.phase8.alert_fallback_rate_threshold,
                    "window": "24h",
                },
            )
        if metrics["timeout_rate_24h"] >= self.config.phase8.alert_timeout_rate_threshold:
            add(
                "v6_timeout_rate",
                "V6 timeout rate exceeded configured threshold.",
                {
                    "current_rate": metrics["timeout_rate_24h"],
                    "threshold": self.config.phase8.alert_timeout_rate_threshold,
                    "window": "24h",
                },
            )
        if metrics["hard_block_rate_24h"] >= self.config.phase8.alert_block_rate_threshold:
            add(
                "v6_hard_block_rate",
                "V6 deterministic hard-block rate exceeded configured threshold.",
                {
                    "current_rate": metrics["hard_block_rate_24h"],
                    "threshold": self.config.phase8.alert_block_rate_threshold,
                    "window": "24h",
                },
            )
        if metrics["divergence_rate_24h"] >= self.config.phase8.divergence_rate_alert_threshold:
            add(
                "v6_divergence_rate",
                "V6/V4 divergence rate exceeded configured threshold.",
                {
                    "current_rate": metrics["divergence_rate_24h"],
                    "threshold": self.config.phase8.divergence_rate_alert_threshold,
                    "window": "24h",
                    "pair_count": metrics["shadow_pair_count_24h"],
                },
            )
        champion_age_days = metrics.get("champion_model_age_days")
        if champion_age_days is not None and champion_age_days >= self.config.phase8.champion_model_staleness_days:
            add(
                "v6_champion_staleness",
                "Champion model age exceeded configured staleness threshold.",
                {
                    "current_days": champion_age_days,
                    "threshold_days": self.config.phase8.champion_model_staleness_days,
                    "model_artifact_version": metrics.get("champion_model_artifact_version"),
                },
            )
        return alerts

    @staticmethod
    def _rate(rows: list[Any], predicate) -> float:
        if not rows:
            return 0.0
        hits = sum(1 for row in rows if predicate(row))
        return hits / len(rows)

    @staticmethod
    def _is_timeout(row: Any) -> bool:
        return "timeout" in str((row or {}).get("degraded_reason") or "").lower()

    @staticmethod
    def _champion_age_days(champion) -> int | None:
        if champion is None or not champion.training_timestamp_utc:
            return None
        try:
            ts = datetime.fromisoformat(str(champion.training_timestamp_utc).replace("Z", "+00:00"))
        except ValueError:
            return None
        return max(0, (datetime.now(timezone.utc) - ts).days)


__all__ = ["RuntimeAlertRecord", "V6RuntimeMetricsService"]
