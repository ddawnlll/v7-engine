"""Adaptive learning profile for analyzer self-correction.

This service turns closed-trade outcomes plus classified failures into a
bounded adjustment profile. The analyzer consumes the resolved adjustments for:
- confidence calibration
- entry timing penalties
- adaptive stop-loss multipliers
- hard rejection rules
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Any

from sqlalchemy.orm import Session

from runtime.db.models import Order, TradeFailure
from runtime.db.repos._helpers import loads_json
from runtime.db.repos.settings_repo import SettingsRepository
from runtime.db.repos.state_repo import StateRepository
from runtime.db.session import get_database_url, session_scope

_CACHE_TTL_SECONDS = 90.0
_STATE_KEY = "learning_profile"
_MIN_TOTAL_CLOSED = 12
_MIN_FAILURES = 5


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(value, upper))


def _blend_multiplier_toward_neutral(multiplier: float, damping: float) -> float:
    """Reduce adjustment strength when regime stability is poor.

    A damping multiplier below 1.0 should not directly reduce signal confidence.
    It should only pull learning-derived multipliers back toward 1.0.
    """

    multiplier = float(multiplier)
    damping = _clamp(float(damping), 0.0, 1.0)
    return 1.0 + ((multiplier - 1.0) * damping)


def _lookback_start(lookback_days: int | None) -> str | None:
    if lookback_days is None or int(lookback_days) <= 0:
        return None
    return (datetime.now(timezone.utc) - timedelta(days=int(lookback_days))).isoformat()


def _confidence_bucket_bounds(confidence_pct: float) -> tuple[float, float]:
    lower = max(50.0, min(90.0, confidence_pct // 10 * 10))
    upper = min(lower + 10.0, 100.0)
    if lower >= 100.0:
        lower = 90.0
        upper = 100.0
    return lower, upper


def _confidence_bucket_label(confidence_pct: float) -> str:
    lower, upper = _confidence_bucket_bounds(confidence_pct)
    return f"{int(lower)}-{int(upper)}"


@dataclass(slots=True)
class ResolvedLearningAdjustments:
    learning_active: bool
    calibration_multiplier: float = 1.0
    calibration_mode: str = "ACTIVE"
    component_penalty: float = 0.0
    entry_penalty: float = 0.0
    execution_penalty: float = 0.0
    entry_timing_risk: float = 0.0
    stop_loss_multiplier: float = 1.0
    adaptive_stop_mode: str = "ACTIVE"
    regime_stability_damping: float = 1.0
    regime_stability_label: str | None = None
    hard_reject: bool = False
    reasons: list[str] | None = None
    execution_flags: list[str] | None = None
    bucket_label: str | None = None
    stop_loss_component_penalty: float = 0.0
    applied_components: list[str] | None = None
    calibration_monotonicity_score: float | None = None
    calibration_monotonicity_status: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "learning_active": self.learning_active,
            "calibration_multiplier": round(self.calibration_multiplier, 4),
            "calibration_mode": self.calibration_mode,
            "component_penalty": round(self.component_penalty, 4),
            "entry_penalty": round(self.entry_penalty, 4),
            "execution_penalty": round(self.execution_penalty, 4),
            "entry_timing_risk": round(self.entry_timing_risk, 4),
            "stop_loss_multiplier": round(self.stop_loss_multiplier, 4),
            "adaptive_stop_mode": self.adaptive_stop_mode,
            "regime_stability_damping": round(self.regime_stability_damping, 4),
            "regime_stability_label": self.regime_stability_label,
            "hard_reject": self.hard_reject,
            "reasons": list(self.reasons or []),
            "execution_flags": list(self.execution_flags or []),
            "bucket_label": self.bucket_label,
            "stop_loss_component_penalty": round(self.stop_loss_component_penalty, 4),
            "applied_components": list(self.applied_components or []),
            "calibration_monotonicity_score": (
                round(self.calibration_monotonicity_score, 4)
                if self.calibration_monotonicity_score is not None
                else None
            ),
            "calibration_monotonicity_status": self.calibration_monotonicity_status,
        }


class LearningService:
    def __init__(self, state_repo: StateRepository | None = None, settings_repo: SettingsRepository | None = None) -> None:
        self.state_repo = state_repo or StateRepository()
        self.settings_repo = settings_repo or SettingsRepository()
        self._cache: dict[tuple[str, int, float], tuple[float, dict[str, Any]]] = {}
        self._settings_cache: tuple[float, dict[str, str]] | None = None
        self._lock = Lock()

    def _settings(self) -> dict[str, str]:
        now = time.time()
        with self._lock:
            if self._settings_cache and now - self._settings_cache[0] < _CACHE_TTL_SECONDS:
                return dict(self._settings_cache[1])
        with session_scope() as session:
            values = self.settings_repo.get_all(session)
        with self._lock:
            self._settings_cache = (now, dict(values))
        return values

    def get_learning_adjustments(
        self,
        lookback_days: int = 30,
        min_confidence: float = 0.6,
        *,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        cache_key = (get_database_url(), int(lookback_days), round(float(min_confidence), 4))
        now = time.time()
        with self._lock:
            cached = self._cache.get(cache_key)
        if not force_refresh and cached and now - cached[0] < _CACHE_TTL_SECONDS:
            return cached[1]

        with session_scope() as session:
            profile = self._build_profile(session, lookback_days=int(lookback_days), min_confidence=float(min_confidence))
            self.state_repo.set(session, _STATE_KEY, profile)
        with self._lock:
            self._cache[cache_key] = (now, profile)
        return profile

    def get_cached_profile(self, *, default_lookback_days: int = 30, default_min_confidence: float = 0.6) -> dict[str, Any]:
        with session_scope() as session:
            cached = self.state_repo.get(session, _STATE_KEY, default=None)
        if isinstance(cached, dict) and cached:
            return cached
        return self.get_learning_adjustments(default_lookback_days, default_min_confidence)

    def resolve_trade_adjustments(
        self,
        *,
        symbol: str,
        interval: str,
        mode: str,
        regime: str,
        direction: str,
        raw_confidence: float,
        snap: dict[str, Any],
        factors: list[dict[str, Any]] | None = None,
        lookback_days: int = 30,
        min_confidence: float = 0.6,
    ) -> ResolvedLearningAdjustments:
        profile = self.get_learning_adjustments(lookback_days=lookback_days, min_confidence=min_confidence)
        active = bool(profile.get("active_adjustments", {}).get("learning_active"))
        if not active:
            profile = self.get_learning_adjustments(
                lookback_days=lookback_days,
                min_confidence=min_confidence,
                force_refresh=True,
            )
            active = bool(profile.get("active_adjustments", {}).get("learning_active"))
        if not active:
            status = str(profile.get("status") or "inactive").lower()
            reason = "Learning disabled by runtime setting." if status == "disabled" else "Learning inactive — insufficient sample size."
            return ResolvedLearningAdjustments(learning_active=False, calibration_mode="INACTIVE", reasons=[reason])

        raw_confidence = _clamp(_as_float(raw_confidence), 0.0, 100.0)
        bucket_label = _confidence_bucket_label(raw_confidence)
        calibration_profile = dict(profile.get("confidence_calibration") or {})
        calibration_monotonicity_score = _as_float(calibration_profile.get("monotonicity_score"), 0.0)
        calibration_monotonicity_status = str(calibration_profile.get("monotonicity_status") or "INSUFFICIENT_DATA")
        calibration_multiplier = 1.0
        calibration_mode = "ACTIVE"
        for bucket in calibration_profile.get("buckets", []):
            if bucket.get("label") == bucket_label:
                calibration_multiplier = _clamp(_as_float(bucket.get("multiplier"), 1.0), 0.7, 1.1)
                break

        regime_stability = dict(profile.get("regime_stability") or {})
        regime_stability_damping = _clamp(_as_float(regime_stability.get("damping_multiplier"), 1.0), 0.6, 1.0)
        regime_stability_label = str(regime_stability.get("label") or "STABLE")
        calibration_multiplier = _clamp(
            _blend_multiplier_toward_neutral(calibration_multiplier, regime_stability_damping),
            0.82,
            1.08,
        )
        if not self._calibration_enabled():
            calibration_multiplier = 1.0
            calibration_mode = "DISABLED_BY_SETTING"
        elif calibration_monotonicity_status not in {"PASS", "WEAK_PASS"}:
            calibration_multiplier = 1.0
            calibration_mode = "DISABLED_BY_VALIDATION"

        entry_risk, entry_reasons, execution_flags = self._entry_timing_risk(snap=snap, direction=direction)
        entry_penalty_base = _as_float(profile.get("entry_penalties", {}).get("global_penalty"), 0.0)
        entry_penalty = entry_penalty_base * entry_risk * regime_stability_damping
        if entry_penalty_base >= 0.15 and entry_risk >= 0.45:
            entry_penalty = max(entry_penalty, entry_penalty_base * 0.65)
        entry_penalty = _clamp(entry_penalty, 0.0, 0.45)

        factor_names = {str((factor or {}).get("name") or "") for factor in (factors or [])}
        penalty_map = {
            str(item.get("component")): _as_float(item.get("penalty"), 0.0)
            for item in profile.get("component_penalties", {}).get("items", [])
        }
        applied_components: list[str] = []
        component_penalty = 0.0
        stop_loss_component_penalty = _as_float(penalty_map.get("Stop Loss"), 0.0)

        if penalty_map.get("Entry Logic"):
            component_penalty += _as_float(penalty_map["Entry Logic"]) * max(0.5, entry_risk)
            applied_components.append("Entry Logic")
        if penalty_map.get("Trend Filter") and abs(_as_float(snap.get("trend_strength"), 50.0) - 50.0) < 12.0:
            component_penalty += _as_float(penalty_map["Trend Filter"]) * 0.7
            applied_components.append("Trend Filter")
        if penalty_map.get("RSI") and "RSI" in factor_names:
            component_penalty += _as_float(penalty_map["RSI"]) * 0.55
            applied_components.append("RSI")
        if penalty_map.get("MACD") and any(name.startswith("MACD") for name in factor_names):
            component_penalty += _as_float(penalty_map["MACD"]) * 0.55
            applied_components.append("MACD")
        if penalty_map.get("Volume") and any("Volume" in name or "VWAP" in name for name in factor_names):
            component_penalty += _as_float(penalty_map["Volume"]) * 0.45
            applied_components.append("Volume")
        hostile_volatility = bool(snap.get("atr_expanding")) or str(snap.get("volatility_regime") or "").upper() in {"EXPANDING", "HIGH_VOL"}
        if stop_loss_component_penalty > 0.0 and (entry_risk >= 0.35 or hostile_volatility):
            stop_loss_weight = 0.2 + min(0.22, entry_risk * 0.3) + (0.08 if hostile_volatility else 0.0)
            component_penalty += stop_loss_component_penalty * stop_loss_weight
            applied_components.append("Stop Loss")
        component_penalty = _clamp(component_penalty * regime_stability_damping, 0.0, 0.35)
        applied_components = list(dict.fromkeys(applied_components))

        execution_penalty = 0.0
        if execution_flags.get("ema_extension"):
            execution_penalty += 0.10
        if execution_flags.get("vwap_stretch"):
            execution_penalty += 0.15
        if execution_flags.get("no_retest_breakout"):
            execution_penalty += 0.18
        if execution_flags.get("impulse_extension"):
            execution_penalty += 0.08
        if execution_flags.get("rsi_stretch"):
            execution_penalty += 0.05
        if execution_flags.get("opposing_flow"):
            execution_penalty += 0.14
        if entry_risk >= 0.6:
            execution_penalty += min(0.08, entry_risk * 0.08)
        execution_penalty = _clamp(execution_penalty * max(regime_stability_damping, 0.7), 0.0, 0.45)

        stop_profile = profile.get("stop_loss_adjustments", {})
        stop_loss_multiplier = 1.0
        adaptive_stop_mode = "ACTIVE"
        if not self._adaptive_stop_enabled():
            adaptive_stop_mode = "DISABLED_BY_SETTING"
        elif stop_profile.get("active"):
            stop_loss_multiplier = _clamp(_as_float(stop_profile.get("base_multiplier"), 1.0), 1.0, _as_float(stop_profile.get("max_multiplier"), 1.8))
            if bool(snap.get("atr_expanding")) or str(snap.get("volatility_regime") or "").upper() == "EXPANDING":
                stop_loss_multiplier += _as_float(stop_profile.get("expanding_volatility_bonus"), 0.0)
            if raw_confidence >= 72.0 and entry_risk >= 0.45:
                stop_loss_multiplier += min(0.15, entry_risk * 0.2)
            stop_loss_multiplier += min(0.12, stop_loss_component_penalty * 0.4)
            stop_loss_multiplier = 1.0 + ((stop_loss_multiplier - 1.0) * regime_stability_damping)
            stop_loss_multiplier = _clamp(stop_loss_multiplier, 1.0, _as_float(stop_profile.get("max_multiplier"), 1.8))

        hard_rules = profile.get("hard_rejection_rules", {})
        hard_reject = False
        if hard_rules.get("active"):
            min_conf = _as_float(hard_rules.get("reject_if_confidence_lte"), 68.0)
            min_risk = _as_float(hard_rules.get("reject_if_entry_risk_gte"), 0.72) + ((1.0 - regime_stability_damping) * 0.18)
            if raw_confidence <= min_conf and entry_risk >= min_risk:
                hard_reject = True
                entry_reasons.append("Hard rejection: execution profile matches repeated high-failure entry pattern.")

        return ResolvedLearningAdjustments(
            learning_active=True,
            calibration_multiplier=calibration_multiplier,
            calibration_mode=calibration_mode,
            component_penalty=component_penalty,
            entry_penalty=entry_penalty,
            execution_penalty=execution_penalty,
            entry_timing_risk=entry_risk,
            stop_loss_multiplier=stop_loss_multiplier,
            adaptive_stop_mode=adaptive_stop_mode,
            regime_stability_damping=regime_stability_damping,
            regime_stability_label=regime_stability_label,
            hard_reject=hard_reject,
            reasons=entry_reasons,
            execution_flags=sorted(flag for flag, active_flag in execution_flags.items() if active_flag),
            bucket_label=bucket_label,
            stop_loss_component_penalty=stop_loss_component_penalty,
            applied_components=applied_components,
            calibration_monotonicity_score=calibration_monotonicity_score,
            calibration_monotonicity_status=calibration_monotonicity_status,
        )

    def _calibration_enabled(self) -> bool:
        raw = self._settings().get("LEARNING_CALIBRATION_ENABLED", "false")
        return str(raw or "false").lower() in {"1", "true", "yes", "on"}

    def _learning_engine_enabled(self) -> bool:
        raw = self._settings().get("LEARNING_ENGINE_ENABLED", "true")
        return str(raw or "true").lower() in {"1", "true", "yes", "on"}

    def _adaptive_stop_enabled(self) -> bool:
        raw = self._settings().get("LEARNING_ADAPTIVE_STOP_ENABLED", "false")
        return str(raw or "false").lower() in {"1", "true", "yes", "on"}

    def _build_profile(self, session: Session, *, lookback_days: int, min_confidence: float) -> dict[str, Any]:
        closed_orders = self._closed_orders(session, lookback_days=lookback_days)
        failures = self._failure_rows(session, lookback_days=lookback_days, min_confidence=min_confidence)
        total_closed = len(closed_orders)
        total_failures = len(failures)
        learning_enabled = str(self.settings_repo.get_value(session, "LEARNING_ENGINE_ENABLED", "true") or "true").lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        learning_active = learning_enabled and total_closed >= _MIN_TOTAL_CLOSED and total_failures >= _MIN_FAILURES

        calibration = self._confidence_calibration(closed_orders, learning_active)
        component_penalties = self._component_penalties(failures, learning_active)
        entry_penalties = self._entry_penalties(failures, learning_active)
        stop_loss_adjustments = self._stop_loss_adjustments(failures, learning_active)
        hard_rejection_rules = self._hard_rejection_rules(failures, learning_active)
        regime_stability = self._regime_stability(closed_orders)

        return {
            "generated_at": _utc_now_iso(),
            "lookback_days": int(lookback_days),
            "min_confidence": float(min_confidence),
            "samples": {
                "total_closed_trades": total_closed,
                "analyzed_losses": total_failures,
                "minimum_closed_trades": _MIN_TOTAL_CLOSED,
                "minimum_failures": _MIN_FAILURES,
                "learning_enabled": learning_enabled,
            },
            "confidence_calibration": calibration,
            "entry_penalties": entry_penalties,
            "stop_loss_adjustments": stop_loss_adjustments,
            "component_penalties": component_penalties,
            "hard_rejection_rules": hard_rejection_rules,
            "regime_stability": regime_stability,
            "active_adjustments": {
                "learning_active": learning_active,
                "confidence_calibration": bool(calibration.get("active")),
                "entry_penalty": bool(entry_penalties.get("active")),
                "stop_loss_adjustment": bool(stop_loss_adjustments.get("active")),
                "component_penalties": bool(component_penalties.get("active")),
                "hard_rejection": bool(hard_rejection_rules.get("active")),
                "regime_stability": bool(regime_stability.get("active")),
            },
            "top_penalties": self._top_penalties(component_penalties, stop_loss_adjustments, entry_penalties),
            "status": "active" if learning_active else ("disabled" if not learning_enabled else "inactive"),
        }

    def _closed_orders(self, session: Session, *, lookback_days: int) -> list[dict[str, Any]]:
        date_from = _lookback_start(lookback_days)
        query = session.query(Order).filter(Order.status != "OPEN")
        if date_from:
            query = query.filter(Order.closed_at_utc >= date_from)
        rows = query.order_by(Order.closed_at_utc.desc()).limit(5000).all()
        results: list[dict[str, Any]] = []
        for row in rows:
            payload = loads_json(row.payload_json, {})
            realized_r = _as_float(payload.get("realized_r"))
            confidence = _as_float(row.confidence)
            results.append(
                {
                    "order_id": row.order_id,
                    "symbol": row.symbol,
                    "interval": row.interval,
                    "mode": row.mode,
                    "direction": row.direction,
                    "confidence": confidence,
                    "confidence_pct": confidence,
                    "realized_r": realized_r,
                    "win": realized_r > 0.0,
                    "closed_at_utc": row.closed_at_utc,
                    "payload": payload,
                    "regime": payload.get("signal", {}).get("regime"),
                }
            )
        return results

    def _regime_stability(self, orders: list[dict[str, Any]]) -> dict[str, Any]:
        regime_counts: dict[str, int] = defaultdict(int)
        for row in orders:
            regime = str(row.get("regime") or "UNKNOWN")
            regime_counts[regime] += 1
        total = sum(regime_counts.values())
        if total <= 0:
            return {
                "active": False,
                "label": "INSUFFICIENT_DATA",
                "damping_multiplier": 1.0,
                "dominant_regime": None,
                "dominant_regime_share": 0.0,
                "unique_regimes": 0,
                "counts": {},
            }
        dominant_regime, dominant_count = max(regime_counts.items(), key=lambda item: item[1])
        dominant_share = dominant_count / total
        unique_regimes = len(regime_counts)
        if total < _MIN_TOTAL_CLOSED:
            label = "INSUFFICIENT_DATA"
            damping = 1.0
        elif unique_regimes >= 3 and dominant_share < 0.45:
            label = "UNSTABLE"
            damping = 0.72
        elif unique_regimes >= 2 and dominant_share < 0.6:
            label = "MIXED"
            damping = 0.85
        else:
            label = "STABLE"
            damping = 1.0
        return {
            "active": total >= _MIN_TOTAL_CLOSED,
            "label": label,
            "damping_multiplier": round(damping, 4),
            "dominant_regime": dominant_regime,
            "dominant_regime_share": round(dominant_share, 4),
            "unique_regimes": unique_regimes,
            "counts": dict(regime_counts),
        }

    def _failure_rows(self, session: Session, *, lookback_days: int, min_confidence: float) -> list[dict[str, Any]]:
        date_from = _lookback_start(lookback_days)
        query = session.query(TradeFailure, Order).outerjoin(Order, Order.order_id == TradeFailure.order_id)
        if date_from:
            query = query.filter(TradeFailure.created_at_utc >= date_from)
        rows: list[dict[str, Any]] = []
        for failure, order in query.all():
            if _as_float(failure.confidence) < float(min_confidence):
                continue
            payload = loads_json(order.payload_json, {}) if order is not None else {}
            rows.append(
                {
                    "order_id": failure.order_id,
                    "signal_id": failure.signal_id,
                    "symbol": order.symbol if order is not None else None,
                    "interval": order.interval if order is not None else None,
                    "mode": order.mode if order is not None else None,
                    "direction": order.direction if order is not None else None,
                    "realized_r": _as_float(payload.get("realized_r")),
                    "failure_source": failure.failure_source,
                    "blamed_component": failure.blamed_component,
                    "severity_score": int(failure.severity_score or 1),
                    "confidence": _as_float(failure.confidence),
                    "classification": failure.classification,
                    "explanation": failure.explanation,
                    "improvement": failure.improvement,
                    "created_at_utc": failure.created_at_utc,
                }
            )
        return rows

    def _confidence_calibration(self, orders: list[dict[str, Any]], active: bool) -> dict[str, Any]:
        ordered_rows = sorted(orders, key=lambda row: str(row.get("closed_at_utc") or ""))
        total_orders = len(ordered_rows)
        split_index = max(1, int(total_orders * 0.7)) if total_orders else 0
        training_rows = ordered_rows[:split_index]
        validation_rows = ordered_rows[split_index:] if split_index < total_orders else []
        if len(validation_rows) < 4 and total_orders >= 8:
            validation_rows = ordered_rows[-4:]
            training_rows = ordered_rows[:-4]

        items, global_multiplier, global_avg_predicted, global_realized_win_rate = self._build_calibration_buckets(training_rows or ordered_rows)
        monotonicity = self._calibration_monotonicity(validation_rows or ordered_rows)
        if monotonicity["status"] == "INSUFFICIENT_DATA" and total_orders >= _MIN_TOTAL_CLOSED:
            fallback = self._calibration_monotonicity(ordered_rows)
            if fallback["status"] in {"PASS", "WEAK_PASS"}:
                monotonicity = {
                    "status": "WEAK_PASS",
                    "score": fallback["score"],
                }
        is_validated = monotonicity["status"] in {"PASS", "WEAK_PASS"}
        return {
            "active": active and bool(items) and is_validated,
            "global_multiplier": round(global_multiplier, 4),
            "global_avg_predicted_confidence": round(global_avg_predicted, 4),
            "global_realized_win_rate": round(global_realized_win_rate, 4),
            "buckets": items,
            "training_samples": len(training_rows or ordered_rows),
            "validation_samples": len(validation_rows or ordered_rows),
            "validation_mode": "OUT_OF_SAMPLE",
            "monotonicity_score": round(_as_float(monotonicity.get("score")), 4),
            "monotonicity_status": monotonicity["status"],
        }

    def _build_calibration_buckets(self, orders: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], float, float, float]:
        buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for order in orders:
            buckets[_confidence_bucket_label(_as_float(order.get("confidence_pct")))].append(order)
        items: list[dict[str, Any]] = []
        global_sample_size = len(orders)
        global_avg_predicted = (
            sum(_as_float(row.get("confidence_pct")) / 100.0 for row in orders) / global_sample_size if global_sample_size else 0.0
        )
        global_realized_win_rate = sum(1 for row in orders if row.get("win")) / global_sample_size if global_sample_size else 0.0
        global_multiplier = 1.0
        if global_sample_size >= _MIN_TOTAL_CLOSED and global_avg_predicted > 0:
            global_multiplier = _clamp(global_realized_win_rate / global_avg_predicted, 0.55, 1.05)
        for label, rows in sorted(buckets.items()):
            sample_size = len(rows)
            avg_predicted = sum(_as_float(row.get("confidence_pct")) / 100.0 for row in rows) / sample_size if sample_size else 0.0
            realized_win_rate = sum(1 for row in rows if row.get("win")) / sample_size if sample_size else 0.0
            multiplier = global_multiplier if global_sample_size >= _MIN_TOTAL_CLOSED else 1.0
            if sample_size >= 3 and avg_predicted > 0:
                bucket_multiplier = _clamp(realized_win_rate / avg_predicted, 0.55, 1.05)
                weight = _clamp(sample_size / 6.0, 0.4, 1.0)
                multiplier = _clamp((bucket_multiplier * weight) + (global_multiplier * (1.0 - weight)), 0.55, 1.05)
            items.append(
                {
                    "label": label,
                    "sample_size": sample_size,
                    "avg_predicted_confidence": round(avg_predicted, 4),
                    "realized_win_rate": round(realized_win_rate, 4),
                    "multiplier": round(multiplier, 4),
                }
            )
        return items, global_multiplier, global_avg_predicted, global_realized_win_rate

    def _calibration_monotonicity(self, orders: list[dict[str, Any]]) -> dict[str, Any]:
        buckets: list[tuple[float, float, int]] = []
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for order in orders:
            grouped[_confidence_bucket_label(_as_float(order.get("confidence_pct")))].append(order)
        for label, rows in sorted(grouped.items()):
            if len(rows) < 2:
                continue
            avg_predicted = sum(_as_float(row.get("confidence_pct")) / 100.0 for row in rows) / len(rows)
            realized_win_rate = sum(1 for row in rows if row.get("win")) / len(rows)
            buckets.append((avg_predicted, realized_win_rate, len(rows)))
        if len(buckets) < 2:
            return {"status": "INSUFFICIENT_DATA", "score": 0.0}
        total_weight = 0
        monotonic_weight = 0
        for idx in range(1, len(buckets)):
            prev_predicted, prev_win_rate, prev_count = buckets[idx - 1]
            cur_predicted, cur_win_rate, cur_count = buckets[idx]
            pair_weight = min(prev_count, cur_count)
            total_weight += pair_weight
            if cur_predicted >= prev_predicted and cur_win_rate >= prev_win_rate:
                monotonic_weight += pair_weight
        if total_weight <= 0:
            return {"status": "INSUFFICIENT_DATA", "score": 0.0}
        score = monotonic_weight / total_weight
        if score >= 0.85:
            status = "PASS"
        elif score >= 0.65:
            status = "WEAK_PASS"
        else:
            status = "FAILED"
        return {"status": status, "score": round(score, 4)}

    def _component_penalties(self, failures: list[dict[str, Any]], active: bool) -> dict[str, Any]:
        total = len(failures)
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in failures:
            grouped[str(row.get("blamed_component") or "UNKNOWN")].append(row)

        items: list[dict[str, Any]] = []
        for component, rows in grouped.items():
            count = len(rows)
            avg_severity = sum(int(row.get("severity_score") or 1) for row in rows) / count if count else 0.0
            avg_conf = sum(_as_float(row.get("confidence")) for row in rows) / count if count else 0.0
            dominant_source = self._top_label(rows, "failure_source")
            frequency = count / max(total, 1)
            penalty = frequency * (avg_severity / 5.0) * max(avg_conf, 0.5)
            if frequency >= 0.55 and count >= 4 and avg_conf >= 0.7:
                penalty = max(penalty, 0.16)
            if component == "Stop Loss" and dominant_source == "RISK_MODEL" and frequency >= 0.5:
                penalty = max(penalty, 0.2)
            penalty = _clamp(penalty, 0.0, 0.35)
            items.append(
                {
                    "component": component,
                    "penalty": round(penalty, 4),
                    "count": count,
                    "avg_severity": round(avg_severity, 4),
                    "avg_confidence": round(avg_conf, 4),
                    "top_failure_source": dominant_source,
                }
            )
        items.sort(key=lambda row: float(row["penalty"]), reverse=True)
        return {"active": active and bool(items), "items": items}

    def _entry_penalties(self, failures: list[dict[str, Any]], active: bool) -> dict[str, Any]:
        timing_rows = [
            row for row in failures
            if str(row.get("failure_source") or "") == "TIMING"
            or str(row.get("blamed_component") or "") == "Entry Logic"
        ]
        total = len(failures)
        if not timing_rows or not total:
            return {
                "active": False,
                "global_penalty": 0.0,
                "early_entry_failure_rate": 0.0,
                "avg_confidence": 0.0,
                "significance_score": 0.0,
            }
        rate = len(timing_rows) / total
        avg_conf = sum(_as_float(row.get("confidence")) for row in timing_rows) / len(timing_rows)
        avg_severity = sum(int(row.get("severity_score") or 1) for row in timing_rows) / len(timing_rows)
        significance = _clamp(rate * (avg_severity / 5.0) * max(avg_conf, 0.5), 0.0, 1.0)
        global_penalty = significance * 0.35
        if rate >= 0.55 and len(timing_rows) >= 4 and avg_conf >= 0.7:
            global_penalty = max(global_penalty, 0.15)
        if rate >= 0.7 and avg_severity >= 4.0:
            global_penalty = max(global_penalty, 0.22)
        global_penalty = _clamp(global_penalty, 0.0, 0.35)
        return {
            "active": active and len(timing_rows) >= 2,
            "global_penalty": round(global_penalty, 4),
            "early_entry_failure_rate": round(rate, 4),
            "avg_confidence": round(avg_conf, 4),
            "significance_score": round(significance, 4),
        }

    def _stop_loss_adjustments(self, failures: list[dict[str, Any]], active: bool) -> dict[str, Any]:
        stop_rows = [
            row for row in failures
            if str(row.get("failure_source") or "") == "RISK_MODEL"
            or str(row.get("blamed_component") or "") == "Stop Loss"
            or str(row.get("classification") or "") == "STOP_LOSS_HIT"
        ]
        total = len(failures)
        if not stop_rows or not total:
            return {
                "active": False,
                "base_multiplier": 1.0,
                "min_multiplier": 1.0,
                "max_multiplier": 1.8,
                "stop_loss_failure_rate": 0.0,
                "avg_failure_severity": 0.0,
                "expanding_volatility_bonus": 0.0,
            }
        rate = len(stop_rows) / total
        avg_severity = sum(int(row.get("severity_score") or 1) for row in stop_rows) / len(stop_rows)
        avg_conf = sum(_as_float(row.get("confidence")) for row in stop_rows) / len(stop_rows)
        base_multiplier = 1.0 + _clamp(rate * (avg_severity / 5.0) * max(avg_conf, 0.5) * 0.8, 0.0, 0.55)
        return {
            "active": active and len(stop_rows) >= 3,
            "base_multiplier": round(_clamp(base_multiplier, 1.0, 1.8), 4),
            "min_multiplier": 1.0,
            "max_multiplier": 1.8,
            "stop_loss_failure_rate": round(rate, 4),
            "avg_failure_severity": round(avg_severity, 4),
            "avg_confidence": round(avg_conf, 4),
            "expanding_volatility_bonus": 0.12,
        }

    def _hard_rejection_rules(self, failures: list[dict[str, Any]], active: bool) -> dict[str, Any]:
        total = len(failures)
        if not total:
            return {
                "active": False,
                "dominant_cluster_ratio": 0.0,
                "reject_if_entry_risk_gte": 0.75,
                "reject_if_confidence_lte": 68.0,
            }
        clusters: dict[tuple[str, str], int] = defaultdict(int)
        for row in failures:
            key = (str(row.get("failure_source") or "UNKNOWN"), str(row.get("blamed_component") or "UNKNOWN"))
            clusters[key] += 1
        cluster_count = max(clusters.values()) if clusters else 0
        cluster_ratio = cluster_count / total if total else 0.0
        return {
            "active": active and cluster_ratio >= 0.55 and total >= _MIN_FAILURES,
            "dominant_cluster_ratio": round(cluster_ratio, 4),
            "reject_if_entry_risk_gte": 0.72,
            "reject_if_confidence_lte": 68.0,
        }

    def _top_penalties(self, component_penalties: dict[str, Any], stop_loss_adjustments: dict[str, Any], entry_penalties: dict[str, Any]) -> list[dict[str, Any]]:
        rows = list(component_penalties.get("items", []))[:5]
        if stop_loss_adjustments.get("active"):
            rows.insert(
                0,
                {
                    "label": "Adaptive Stop Loss",
                    "penalty": round(_as_float(stop_loss_adjustments.get("base_multiplier"), 1.0) - 1.0, 4),
                    "kind": "stop_loss_adjustment",
                },
            )
        if entry_penalties.get("active"):
            rows.insert(
                0,
                {
                    "label": "Entry Timing",
                    "penalty": round(_as_float(entry_penalties.get("global_penalty"), 0.0), 4),
                    "kind": "entry_penalty",
                },
            )
        return rows[:6]

    @staticmethod
    def _top_label(rows: list[dict[str, Any]], key: str) -> str | None:
        counts: dict[str, int] = defaultdict(int)
        for row in rows:
            counts[str(row.get(key) or "UNKNOWN")] += 1
        if not counts:
            return None
        return max(counts.items(), key=lambda item: item[1])[0]

    @staticmethod
    def _entry_timing_risk(*, snap: dict[str, Any], direction: str) -> tuple[float, list[str], dict[str, bool]]:
        price = _as_float(snap.get("price"))
        ema_21 = _as_float(snap.get("ema_21"))
        vwap = _as_float(snap.get("vwap"))
        rsi = _as_float(snap.get("rsi"), 50.0)
        flow_imbalance = _as_float(snap.get("flow_imbalance"))
        orderbook_imbalance = _as_float(snap.get("orderbook_imbalance"))
        price_impulse = abs(_as_float(snap.get("_price_5bar_change")))
        breakout = bool(snap.get("breakout_up") if direction == "BUY" else snap.get("breakout_down"))
        retest = bool(snap.get("retest_support") if direction == "BUY" else snap.get("retest_resist"))

        score = 0.0
        reasons: list[str] = []
        flags = {
            "ema_extension": False,
            "vwap_stretch": False,
            "no_retest_breakout": False,
            "impulse_extension": False,
            "rsi_stretch": False,
            "opposing_flow": False,
        }
        if price and ema_21 and abs(price - ema_21) / max(price, 1e-9) > 0.012:
            score += 0.28
            flags["ema_extension"] = True
            reasons.append("Price is extended away from EMA21.")
        if price and vwap and abs(price - vwap) / max(price, 1e-9) > 0.008:
            score += 0.12
            flags["vwap_stretch"] = True
            reasons.append("Entry is stretched away from VWAP.")
        if breakout and not retest:
            score += 0.28
            flags["no_retest_breakout"] = True
            reasons.append("Breakout has not retested yet.")
        if price_impulse >= 1.0:
            score += 0.12
            flags["impulse_extension"] = True
            reasons.append("Recent impulse is extended.")
        if direction == "BUY" and rsi >= 63:
            score += 0.1
            flags["rsi_stretch"] = True
            reasons.append("RSI is elevated for a fresh long entry.")
        if direction == "SELL" and rsi <= 37:
            score += 0.1
            flags["rsi_stretch"] = True
            reasons.append("RSI is compressed for a fresh short entry.")
        if direction == "BUY" and (flow_imbalance < -0.08 or orderbook_imbalance < -0.08):
            score += 0.16
            flags["opposing_flow"] = True
            reasons.append("Microstructure flow is still leaning against the long.")
        if direction == "SELL" and (flow_imbalance > 0.08 or orderbook_imbalance > 0.08):
            score += 0.16
            flags["opposing_flow"] = True
            reasons.append("Microstructure flow is still leaning against the short.")
        return _clamp(score, 0.0, 1.0), reasons, flags
