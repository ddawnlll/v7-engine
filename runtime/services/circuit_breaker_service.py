"""Rolling safety gate for hostile trading conditions."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from runtime.db.models import Order, TradeFailure
from v6.config import V6Config
from runtime.db.repos._helpers import loads_json
from runtime.db.repos.circuit_breaker_repo import CircuitBreakerRepository
from runtime.db.repos.runtime_profile_repo import PAPER_PROFILE_ID
from runtime.db.repos.settings_repo import SettingsRepository
from runtime.db.session import get_database_url
from runtime.db.session import session_scope


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


@dataclass
class CircuitRules:
    enabled: bool = True
    manual_mode: str = "AUTO"
    lookback_window: int = 10
    max_consecutive_losses: int = 5
    max_failure_rate_pct: float = 70.0
    max_severity_avg: float = 4.0
    cooldown_minutes: int = 60
    degraded_multiplier: float = 0.7


class CircuitBreakerService:
    _CACHE_TTL_SECONDS = 5.0

    def __init__(
        self,
        settings_repo: SettingsRepository | None = None,
        repo: CircuitBreakerRepository | None = None,
    ) -> None:
        self.settings_repo = settings_repo or SettingsRepository()
        self.repo = repo or CircuitBreakerRepository()
        self._cache: dict[tuple[str, int | None], tuple[datetime, dict[str, Any]]] = {}
        self._lock = Lock()
        self.v6_config = V6Config.load(__import__('pathlib').Path('config/v6_config_defaults.json'))

    def evaluate_circuit_state(
        self,
        lookback_window: int | None = None,
        profile_id: str = PAPER_PROFILE_ID,
    ) -> dict[str, Any]:
        cache_key = (get_database_url(), profile_id, int(lookback_window) if lookback_window is not None else None)
        now = _utc_now()
        with self._lock:
            cached = self._cache.get(cache_key)
        if cached and (now - cached[0]).total_seconds() < self._CACHE_TTL_SECONDS:
            return dict(cached[1])
        with session_scope() as session:
            settings = self.settings_repo.get_all(session, profile_id=profile_id)
            rules = self._rules_from_settings(settings, lookback_window=lookback_window)
            state = self._evaluate_with_session(session, rules, profile_id=profile_id)
            self._persist_transition(session, state, profile_id=profile_id)
        with self._lock:
            self._cache[cache_key] = (now, dict(state))
        return state

    def _invalidate_cache(self) -> None:
        with self._lock:
            self._cache.clear()

    def list_events(self, *, limit: int = 100, offset: int = 0, profile_id: str = PAPER_PROFILE_ID) -> list[dict]:
        with session_scope() as session:
            return self.repo.list_events(session, limit=limit, offset=offset, profile_id=profile_id)

    def reset(self, profile_id: str = PAPER_PROFILE_ID) -> dict[str, Any]:
        with session_scope() as session:
            now = _utc_now().isoformat()
            current = self.repo.get_current_state(session, profile_id=profile_id)
            if current:
                self.repo.resolve_event(session, int(current["id"]), now, profile_id=profile_id)
            payload = self.repo.normalize_payload(
                {
                    "profile_id": profile_id,
                    "status": "CLOSED",
                    "reason": "Manual reset",
                    "failure_rate": 0.0,
                    "consecutive_losses": 0,
                    "triggered_at_utc": now,
                    "resolved_at_utc": now,
                    "active_rules": ["manual_reset"],
                }
            )
            result = self.repo.save_event(session, payload)
        self._invalidate_cache()
        return result

    def update_settings(self, values: dict[str, Any], *, profile_id: str = PAPER_PROFILE_ID) -> dict[str, str]:
        allowed = {
            "CIRCUIT_BREAKER_ENABLED",
            "CIRCUIT_BREAKER_MANUAL_MODE",
            "CIRCUIT_BREAKER_LOOKBACK_TRADES",
            "CIRCUIT_BREAKER_MAX_CONSECUTIVE_LOSSES",
            "CIRCUIT_BREAKER_MAX_FAILURE_RATE_PCT",
            "CIRCUIT_BREAKER_MAX_SEVERITY_AVG",
            "CIRCUIT_BREAKER_COOLDOWN_MINUTES",
            "CIRCUIT_BREAKER_DEGRADED_MULTIPLIER",
        }
        updates = {key: str(value) for key, value in values.items() if key in allowed}
        with session_scope() as session:
            result = self.settings_repo.save_many(session, updates, profile_id=profile_id)
        self._invalidate_cache()
        return result

    def _evaluate_with_session(self, session: Session, rules: CircuitRules, *, profile_id: str = PAPER_PROFILE_ID) -> dict[str, Any]:
        now = _utc_now()
        active_event = self.repo.get_current_state(session, profile_id=profile_id)
        if not rules.enabled:
            return self._state_payload(
                status="CLOSED",
                reason="Circuit breaker disabled in settings.",
                triggered_at=now,
                failure_rate=0.0,
                consecutive_losses=0,
                active_rules=["disabled"],
                rules=rules,
                active_event=active_event,
                profile_id=profile_id,
            )
        if rules.manual_mode == "FORCE_OPEN":
            return self._state_payload(
                status="OPEN",
                reason="Circuit breaker manually forced OPEN by operator.",
                triggered_at=now,
                failure_rate=0.0,
                consecutive_losses=0,
                active_rules=["manual_force_open"],
                rules=rules,
                active_event=active_event,
                auto_resume_at=None,
                profile_id=profile_id,
            )
        if rules.manual_mode == "FORCE_CLOSED":
            return self._state_payload(
                status="CLOSED",
                reason="Circuit breaker manually forced CLOSED by operator.",
                triggered_at=now,
                failure_rate=0.0,
                consecutive_losses=0,
                active_rules=["manual_force_closed"],
                rules=rules,
                active_event=active_event,
                auto_resume_at=None,
                profile_id=profile_id,
            )

        window = max(1, int(rules.lookback_window))
        closed_orders = (
            session.query(Order)
            .filter(Order.profile_id == profile_id)
            .filter(Order.status != "OPEN")
            .order_by(Order.closed_at_utc.desc())
            .limit(max(window, 50))
            .all()
        )
        recent_orders = closed_orders[:window]
        analyzed_failures = (
            session.query(TradeFailure)
            .filter(TradeFailure.profile_id == profile_id)
            .order_by(TradeFailure.created_at_utc.desc())
            .limit(max(window, 20))
            .all()
        )

        failure_count = sum(1 for row in recent_orders if _as_float(loads_json(row.payload_json, {}).get("realized_r")) <= 0.0)
        failure_rate = (failure_count / len(recent_orders) * 100.0) if recent_orders else 0.0
        consecutive_losses = 0
        for row in closed_orders:
            realized_r = _as_float(loads_json(row.payload_json, {}).get("realized_r"))
            if realized_r > 0.0:
                break
            consecutive_losses += 1

        recent_severity_rows = analyzed_failures[:5]
        avg_severity = (
            sum(int(row.severity_score or 0) for row in recent_severity_rows) / len(recent_severity_rows)
            if recent_severity_rows
            else 0.0
        )
        session_breakdown = self._failure_breakdown(recent_orders, key="session_label")
        time_of_day_breakdown = self._failure_breakdown(recent_orders, key="hour_bucket")

        status = "CLOSED"
        reasons: list[str] = []
        active_rules: list[str] = []

        try:
            decision_rows = session.execute(
                text(
                    "SELECT symbol, fallback_used, degraded_reason, deterministic_block FROM decision_events ORDER BY timestamp_utc DESC LIMIT :limit"
                ),
                {"limit": max(window * 5, 50)},
            ).mappings().all()
        except Exception:
            decision_rows = []
        timeout_streak = 0
        schema_streak = 0
        hard_block_counter: Counter[str] = Counter()
        for row in decision_rows:
            reason = str(row.get("degraded_reason") or "").upper()
            if "TIMEOUT" in reason:
                timeout_streak += 1
            else:
                timeout_streak = 0
            if "SCHEMA" in reason or "VALIDATION" in reason:
                schema_streak += 1
            else:
                schema_streak = 0
            if bool(row.get("deterministic_block")):
                hard_block_counter[str(row.get("symbol") or "UNKNOWN")] += 1

        cooldown_until = _parse_iso(active_event.get("auto_resume_at_utc") if active_event else None)
        if active_event and active_event.get("status") == "OPEN" and cooldown_until and cooldown_until > now:
            status = "OPEN"
            reasons.append("Cooldown active after recent circuit breaker trip.")
            active_rules.append("cooldown")
        else:
            if consecutive_losses >= rules.max_consecutive_losses:
                status = "OPEN"
                reasons.append(f"Consecutive losses {consecutive_losses} reached threshold {rules.max_consecutive_losses}.")
                active_rules.append("max_consecutive_losses")
            if timeout_streak >= self.v6_config.phase8.circuit_breaker_timeout_trip_count:
                status = "OPEN"
                reasons.append(
                    f"Consecutive V6 timeout failures {timeout_streak} reached threshold {self.v6_config.phase8.circuit_breaker_timeout_trip_count}."
                )
                active_rules.append("v6_timeout_trip")
            if schema_streak >= self.v6_config.phase8.circuit_breaker_schema_failure_trip_count:
                status = "OPEN"
                reasons.append(
                    f"Consecutive V6 schema failures {schema_streak} reached threshold {self.v6_config.phase8.circuit_breaker_schema_failure_trip_count}."
                )
                active_rules.append("v6_schema_trip")
            if any(count >= self.v6_config.phase8.circuit_breaker_hard_block_trip_count for count in hard_block_counter.values()):
                status = "OPEN"
                reasons.append(
                    f"Repeated deterministic hard blocks reached threshold {self.v6_config.phase8.circuit_breaker_hard_block_trip_count} for at least one symbol."
                )
                active_rules.append("v6_hard_block_trip")
            if failure_rate >= rules.max_failure_rate_pct and len(recent_orders) >= min(window, 3):
                status = "OPEN"
                reasons.append(f"Failure rate {failure_rate:.1f}% exceeded threshold {rules.max_failure_rate_pct:.1f}%.")
                active_rules.append("max_failure_rate_pct")
            if avg_severity >= rules.max_severity_avg and len(recent_severity_rows) >= 3:
                status = "OPEN"
                reasons.append(f"Average failure severity {avg_severity:.2f} exceeded threshold {rules.max_severity_avg:.2f}.")
                active_rules.append("max_severity_avg")
            if status == "CLOSED":
                near_failure = failure_rate >= max(rules.max_failure_rate_pct * 0.8, rules.max_failure_rate_pct - 10.0)
                near_losses = consecutive_losses >= max(rules.max_consecutive_losses - 1, 1)
                near_severity = avg_severity >= max(rules.max_severity_avg - 0.5, rules.max_severity_avg * 0.85)
                if near_failure or near_losses or near_severity:
                    status = "DEGRADED"
                    if near_failure:
                        reasons.append(f"Failure rate {failure_rate:.1f}% is approaching threshold.")
                        active_rules.append("near_failure_rate")
                    if near_losses:
                        reasons.append(f"Loss streak {consecutive_losses} is approaching threshold.")
                        active_rules.append("near_consecutive_losses")
                    if near_severity:
                        reasons.append(f"Average failure severity {avg_severity:.2f} is elevated.")
                        active_rules.append("near_severity")

        return self._state_payload(
            status=status,
            reason=" ".join(reasons) if reasons else "Trading conditions are within configured safety thresholds.",
            triggered_at=now,
            failure_rate=failure_rate,
            consecutive_losses=consecutive_losses,
            active_rules=active_rules,
            rules=rules,
            active_event=active_event,
            session_breakdown=session_breakdown,
            time_of_day_breakdown=time_of_day_breakdown,
            profile_id=profile_id,
        )

    def _persist_transition(self, session: Session, state: dict[str, Any], *, profile_id: str = PAPER_PROFILE_ID) -> None:
        current = self.repo.get_current_state(session, profile_id=profile_id)
        now_iso = state["triggered_at"]
        desired_status = state["status"]
        if current and current.get("status") == desired_status:
            return
        if current and current.get("status") in {"OPEN", "DEGRADED"}:
            self.repo.resolve_event(session, int(current["id"]), now_iso, profile_id=profile_id)
        if desired_status in {"OPEN", "DEGRADED"}:
            self.repo.save_event(session, self.repo.normalize_payload({**state, "profile_id": profile_id}))

    def _rules_from_settings(self, settings: dict[str, str], *, lookback_window: int | None) -> CircuitRules:
        return CircuitRules(
            enabled=str(settings.get("CIRCUIT_BREAKER_ENABLED", "true")).lower() in {"1", "true", "yes", "on"},
            manual_mode=str(settings.get("CIRCUIT_BREAKER_MANUAL_MODE", "AUTO") or "AUTO").upper(),
            lookback_window=int(lookback_window or settings.get("CIRCUIT_BREAKER_LOOKBACK_TRADES", "10") or 10),
            max_consecutive_losses=int(settings.get("CIRCUIT_BREAKER_MAX_CONSECUTIVE_LOSSES", "5") or 5),
            max_failure_rate_pct=_as_float(settings.get("CIRCUIT_BREAKER_MAX_FAILURE_RATE_PCT"), 70.0),
            max_severity_avg=_as_float(settings.get("CIRCUIT_BREAKER_MAX_SEVERITY_AVG"), 4.0),
            cooldown_minutes=int(settings.get("CIRCUIT_BREAKER_COOLDOWN_MINUTES", "60") or 60),
            degraded_multiplier=_as_float(settings.get("CIRCUIT_BREAKER_DEGRADED_MULTIPLIER"), 0.7),
        )

    def _failure_breakdown(self, rows: list[Order], *, key: str) -> dict[str, float]:
        counter: Counter[str] = Counter()
        losses = 0
        for row in rows:
            payload = loads_json(row.payload_json, {})
            if _as_float(payload.get("realized_r")) > 0.0:
                continue
            losses += 1
            signal_payload = dict(payload.get("signal") or {})
            if key == "session_label":
                label = str((signal_payload.get("advanced_analysis") or {}).get("session_label") or "unknown")
            else:
                closed = _parse_iso(row.closed_at_utc)
                label = f"{closed.hour:02d}:00" if closed else "unknown"
            counter[label] += 1
        if losses <= 0:
            return {}
        return {name: round((count / losses) * 100.0, 2) for name, count in counter.items()}

    def _state_payload(
        self,
        *,
        status: str,
        reason: str,
        triggered_at: datetime,
        failure_rate: float,
        consecutive_losses: int,
        active_rules: list[str],
        rules: CircuitRules,
        active_event: dict | None,
        session_breakdown: dict[str, float] | None = None,
        time_of_day_breakdown: dict[str, float] | None = None,
        auto_resume_at: str | None = None,
        profile_id: str = PAPER_PROFILE_ID,
    ) -> dict[str, Any]:
        resolved_auto_resume_at = auto_resume_at
        if resolved_auto_resume_at is None and status == "OPEN" and rules.manual_mode != "FORCE_OPEN":
            resolved_auto_resume_at = (triggered_at + timedelta(minutes=rules.cooldown_minutes)).isoformat()
        elif resolved_auto_resume_at is None and active_event and active_event.get("status") == "OPEN":
            resolved_auto_resume_at = active_event.get("auto_resume_at_utc")
        return {
            "profile_id": profile_id,
            "status": status,
            "reason": reason,
            "triggered_at": triggered_at.isoformat(),
            "triggered_at_utc": triggered_at.isoformat(),
            "auto_resume_at": resolved_auto_resume_at,
            "auto_resume_at_utc": resolved_auto_resume_at,
            "failure_rate": round(failure_rate, 2),
            "consecutive_losses": int(consecutive_losses),
            "active_rules": list(active_rules),
            "degraded_multiplier": round(rules.degraded_multiplier, 4),
            "lookback_window": int(rules.lookback_window),
            "enabled": bool(rules.enabled),
            "manual_mode": str(rules.manual_mode),
            "is_manual_override": str(rules.manual_mode) != "AUTO",
            "session_breakdown": session_breakdown or {},
            "time_of_day_breakdown": time_of_day_breakdown or {},
        }
