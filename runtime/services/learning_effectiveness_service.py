"""Evaluate whether active learning adjustments are helping or hurting."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from runtime.db.models import Order, TradeFailure
from runtime.db.repos._helpers import loads_json
from runtime.services.attribution_integrity_service import AttributionIntegrityService
from runtime.services.learning_service import LearningService
from runtime.db.session import session_scope


def _lookback_start(lookback_days: int | None) -> str | None:
    if lookback_days is None or int(lookback_days) <= 0:
        return None
    return (datetime.now(timezone.utc) - timedelta(days=int(lookback_days))).isoformat()


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class LearningEffectivenessService:
    ADJUSTMENTS = (
        ("confidence_calibration", "Confidence Calibration"),
        ("entry_penalty", "Entry Timing Penalty"),
        ("component_penalty", "Component Penalty"),
        ("adaptive_stop", "Adaptive Stop Loss"),
        ("execution_penalty", "Execution Penalty"),
    )

    def __init__(
        self,
        learning_service: LearningService | None = None,
        attribution_integrity_service: AttributionIntegrityService | None = None,
    ) -> None:
        self.learning_service = learning_service or LearningService()
        self.attribution_integrity_service = attribution_integrity_service or AttributionIntegrityService()

    def get_effectiveness_report(self, *, lookback_days: int = 30, min_samples: int = 5) -> dict[str, Any]:
        with session_scope() as session:
            rows = self._closed_orders(session, lookback_days=lookback_days)
            severities = self._failure_severity_by_order(session, lookback_days=lookback_days)
        attribution_integrity = self.attribution_integrity_service.evaluate(lookback_days=lookback_days)
        calibration_check = self.get_calibration_monotonicity_check(lookback_days=lookback_days, min_samples=min_samples)

        adjustments = [self._evaluate_adjustment(rows, severities, key, label, min_samples=min_samples) for key, label in self.ADJUSTMENTS]
        status_counts: dict[str, int] = defaultdict(int)
        flagged_adjustments: list[dict[str, Any]] = []
        for item in adjustments:
            status_counts[str(item["status"])] += 1
            if item["status"] in {"DEGRADING", "INSUFFICIENT_DATA"}:
                flagged_adjustments.append(
                    {
                        "adjustment_id": item["adjustment_id"],
                        "reason": item["status_reason"],
                        "recommendation": "Review threshold strength or disable until more samples accumulate." if item["status"] == "DEGRADING" else "Collect more samples before judging this adjustment.",
                    }
                )

        overall_health_score = self._health_score(status_counts, len(adjustments))
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "lookback_days": int(lookback_days),
            "min_samples": int(min_samples),
            "overall_health_score": round(overall_health_score, 4),
            "health_score": round(overall_health_score, 4),
            "total_trades_before": sum(int(item["trades_before"]) for item in adjustments),
            "total_trades_after": sum(int(item["trades_after"]) for item in adjustments),
            "total_closed_trades": len(rows),
            "status_counts": dict(status_counts),
            "attribution_integrity": attribution_integrity,
            "calibration_monotonicity": calibration_check,
            "safety_notes": self._safety_notes(attribution_integrity, calibration_check),
            "adjustments": adjustments,
            "flagged_adjustments": flagged_adjustments,
        }

    def get_calibration_monotonicity_check(self, *, lookback_days: int = 30, min_samples: int = 5) -> dict[str, Any]:
        profile = self.learning_service.get_learning_adjustments(lookback_days=lookback_days, min_confidence=0.6)
        with session_scope() as session:
            rows = self._closed_orders(session, lookback_days=lookback_days)
        bucket_rows: list[dict[str, Any]] = []
        for row in rows:
            learning = dict(row.get("learning") or {})
            confidence_value = _as_float(learning.get("confidence_before"), row.get("confidence"))
            lower = max(50, min(90, int(confidence_value // 10) * 10))
            upper = 100 if lower >= 90 else lower + 10
            label = f"{lower}-{upper}"
            bucket_rows.append(
                {
                    "label": label,
                    "confidence_value": confidence_value,
                    "realized_r": _as_float(row.get("realized_r")),
                    "win": _as_float(row.get("realized_r")) > 0.0,
                }
            )
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in bucket_rows:
            grouped[str(row["label"])].append(row)
        buckets = []
        for label in sorted(grouped.keys()):
            items = grouped[label]
            sample_size = len(items)
            win_rate = sum(1 for item in items if item["win"]) / sample_size if sample_size else 0.0
            avg_r = sum(_as_float(item["realized_r"]) for item in items) / sample_size if sample_size else 0.0
            buckets.append(
                {
                    "label": label,
                    "sample_size": sample_size,
                    "win_rate": round(win_rate, 4),
                    "avg_realized_r": round(avg_r, 4),
                }
            )

        eligible = [bucket for bucket in buckets if int(bucket["sample_size"]) >= int(min_samples)]
        monotonic = True
        violations: list[dict[str, Any]] = []
        for index in range(1, len(eligible)):
            prior = eligible[index - 1]
            current = eligible[index]
            if _as_float(current["win_rate"]) + 1e-9 < _as_float(prior["win_rate"]) or _as_float(current["avg_realized_r"]) + 1e-9 < _as_float(prior["avg_realized_r"]):
                monotonic = False
                violations.append(
                    {
                        "prior_bucket": prior["label"],
                        "current_bucket": current["label"],
                        "prior_win_rate": prior["win_rate"],
                        "current_win_rate": current["win_rate"],
                        "prior_avg_realized_r": prior["avg_realized_r"],
                        "current_avg_realized_r": current["avg_realized_r"],
                    }
                )
        calibration_enabled = bool((profile.get("active_adjustments") or {}).get("confidence_calibration"))
        return {
            "status": (
                "BYPASSED"
                if not self.learning_service._calibration_enabled()
                else ("INSUFFICIENT_DATA" if len(eligible) < 2 else ("PASS" if monotonic else "FAIL"))
            ),
            "calibration_enabled": self.learning_service._calibration_enabled(),
            "profile_active": calibration_enabled,
            "lookback_days": int(lookback_days),
            "min_samples": int(min_samples),
            "eligible_bucket_count": len(eligible),
            "buckets": buckets,
            "violations": violations,
            "summary": (
                "Calibration is currently bypassed by runtime setting."
                if not self.learning_service._calibration_enabled()
                else ("Not enough populated confidence buckets to validate monotonic ordering." if len(eligible) < 2 else ("Higher confidence buckets outperform lower ones." if monotonic else "Higher confidence buckets do not consistently outperform lower ones."))
            ),
        }

    def _closed_orders(self, session: Session, *, lookback_days: int) -> list[dict[str, Any]]:
        date_from = _lookback_start(lookback_days)
        query = session.query(Order).filter(Order.status != "OPEN")
        if date_from:
            query = query.filter(Order.closed_at_utc >= date_from)
        rows = query.order_by(Order.closed_at_utc.asc()).limit(5000).all()
        items: list[dict[str, Any]] = []
        for row in rows:
            payload = loads_json(row.payload_json, {})
            learning = dict(payload.get("learning") or {})
            adjustments = dict(learning.get("adjustments") or {})
            items.append(
                {
                    "order_id": row.order_id,
                    "symbol": row.symbol,
                    "mode": row.mode,
                    "interval": row.interval,
                    "confidence": _as_float(row.confidence),
                    "realized_r": _as_float(payload.get("realized_r")),
                    "learning": learning,
                    "adjustments": adjustments,
                    "closed_at_utc": row.closed_at_utc,
                }
            )
        return items

    def _failure_severity_by_order(self, session: Session, *, lookback_days: int) -> dict[str, float]:
        date_from = _lookback_start(lookback_days)
        query = session.query(TradeFailure)
        if date_from:
            query = query.filter(TradeFailure.created_at_utc >= date_from)
        rows = query.all()
        return {str(row.order_id): float(row.severity_score or 0.0) for row in rows}

    def _evaluate_adjustment(
        self,
        rows: list[dict[str, Any]],
        severities: dict[str, float],
        key: str,
        label: str,
        *,
        min_samples: int,
    ) -> dict[str, Any]:
        after_rows = [row for row in rows if self._is_adjustment_active(row.get("adjustments") or {}, key)]
        before_rows = [row for row in rows if not self._is_adjustment_active(row.get("adjustments") or {}, key)]
        trades_after = len(after_rows)
        trades_before = len(before_rows)
        win_rate_before = self._win_rate(before_rows)
        win_rate_after = self._win_rate(after_rows)
        avg_r_before = self._avg_realized_r(before_rows)
        avg_r_after = self._avg_realized_r(after_rows)
        severity_before = self._avg_severity(before_rows, severities)
        severity_after = self._avg_severity(after_rows, severities)
        confidence = min(0.99, max(0.0, (trades_after + trades_before) / max((min_samples * 4), 1)))

        if trades_after < min_samples or trades_before < min_samples:
            status = "INSUFFICIENT_DATA"
            status_reason = f"Needs at least {min_samples} samples before and after activation."
        elif win_rate_after > win_rate_before and avg_r_after > avg_r_before:
            status = "IMPROVING"
            status_reason = "Win rate and realized R both improved after activation."
        elif win_rate_after < win_rate_before or avg_r_after < avg_r_before:
            status = "DEGRADING"
            status_reason = "Win rate or realized R worsened after activation."
        else:
            status = "NEUTRAL"
            status_reason = "No meaningful change detected after activation."

        applied_since = after_rows[0]["closed_at_utc"] if after_rows else None
        return {
            "adjustment_id": key,
            "label": label,
            "applied_since": applied_since,
            "trades_before": trades_before,
            "trades_after": trades_after,
            "win_rate_before": round(win_rate_before, 4),
            "win_rate_after": round(win_rate_after, 4),
            "avg_r_before": round(avg_r_before, 4),
            "avg_r_after": round(avg_r_after, 4),
            "loss_severity_before": round(severity_before, 4),
            "loss_severity_after": round(severity_after, 4),
            "status": status,
            "status_reason": status_reason,
            "confidence": round(confidence, 4),
        }

    @staticmethod
    def _avg_realized_r(rows: list[dict[str, Any]]) -> float:
        if not rows:
            return 0.0
        return sum(_as_float(row.get("realized_r")) for row in rows) / len(rows)

    @staticmethod
    def _avg_severity(rows: list[dict[str, Any]], severities: dict[str, float]) -> float:
        if not rows:
            return 0.0
        return sum(severities.get(str(row.get("order_id")), 0.0) for row in rows) / len(rows)

    @staticmethod
    def _win_rate(rows: list[dict[str, Any]]) -> float:
        if not rows:
            return 0.0
        return sum(1 for row in rows if _as_float(row.get("realized_r")) > 0.0) / len(rows)

    @staticmethod
    def _is_adjustment_active(adjustments: dict[str, Any], key: str) -> bool:
        if key == "confidence_calibration":
            return abs(_as_float(adjustments.get("calibration_multiplier"), 1.0) - 1.0) >= 0.02
        if key == "entry_penalty":
            return _as_float(adjustments.get("entry_penalty")) > 0.01
        if key == "component_penalty":
            return _as_float(adjustments.get("component_penalty")) > 0.01
        if key == "adaptive_stop":
            return _as_float(adjustments.get("stop_loss_multiplier"), 1.0) > 1.01
        if key == "execution_penalty":
            return _as_float(adjustments.get("execution_penalty")) > 0.01
        return False

    @staticmethod
    def _health_score(status_counts: dict[str, int], total: int) -> float:
        if total <= 0:
            return 0.0
        score = (
            status_counts.get("IMPROVING", 0) * 1.0
            + status_counts.get("NEUTRAL", 0) * 0.5
            + status_counts.get("INSUFFICIENT_DATA", 0) * 0.25
            - status_counts.get("DEGRADING", 0) * 1.0
        )
        return max(0.0, min(1.0, score / total))

    @staticmethod
    def _safety_notes(attribution_integrity: dict[str, Any], calibration_check: dict[str, Any]) -> list[str]:
        notes: list[str] = []
        if attribution_integrity.get("provisional"):
            notes.append(f"Component-level and calibration conclusions are provisional: {attribution_integrity.get('summary')}")
        if str(calibration_check.get("status")) in {"FAIL", "BYPASSED"}:
            notes.append(str(calibration_check.get("summary") or "Calibration should not be treated as production-valid yet."))
        return notes
