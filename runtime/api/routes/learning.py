"""Adaptive learning profile routes."""

from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Query, Response

from runtime.services.learning_effectiveness_service import LearningEffectivenessService
from runtime.services.learning_service import LearningService

router = APIRouter(tags=["learning"])
learning_service = LearningService()
effectiveness_service = LearningEffectivenessService()


@router.get("/api/v3/learning/profile")
@router.get("/api/admin/learning/profile")
def get_learning_profile(
    lookback_days: int = Query(default=30, ge=0, le=3650),
    min_confidence: float = Query(default=0.6, ge=0.0, le=1.0),
):
    profile = learning_service.get_learning_adjustments(
        lookback_days=lookback_days,
        min_confidence=min_confidence,
    )
    samples = dict(profile.get("samples") or {})
    return {
        "ok": True,
        "active": bool(profile.get("active_adjustments", {}).get("learning_active")),
        "sample_size": int(samples.get("total_closed_trades") or 0),
        "top_penalties": list(profile.get("top_penalties") or []),
        "calibration_data": list((profile.get("confidence_calibration") or {}).get("buckets") or []),
        "effectiveness_summary": effectiveness_service.get_effectiveness_report(lookback_days=lookback_days),
        "profile": profile,
    }


@router.get("/api/v3/learning/export")
@router.get("/api/admin/learning/export")
def export_learning_csv(
    lookback_days: int = Query(default=30, ge=0, le=3650),
    min_confidence: float = Query(default=0.6, ge=0.0, le=1.0),
    min_samples: int = Query(default=5, ge=1, le=1000),
):
    profile = learning_service.get_learning_adjustments(
        lookback_days=lookback_days,
        min_confidence=min_confidence,
    )
    effectiveness = effectiveness_service.get_effectiveness_report(
        lookback_days=lookback_days,
        min_samples=min_samples,
    )
    rows: list[dict[str, object]] = []

    samples = dict(profile.get("samples") or {})
    rows.append(
        {
            "section": "summary",
            "key": "profile",
            "label": "Learning Profile",
            "value": profile.get("status"),
            "sample_size": int(samples.get("total_closed_trades") or 0),
            "active": bool((profile.get("active_adjustments") or {}).get("learning_active")),
            "lookback_days": lookback_days,
            "min_confidence": min_confidence,
            "min_samples": min_samples,
            "generated_at": profile.get("generated_at"),
        }
    )

    for bucket in list((profile.get("confidence_calibration") or {}).get("buckets") or []):
        rows.append(
            {
                "section": "calibration_bucket",
                "key": bucket.get("label"),
                "label": bucket.get("label"),
                "sample_size": bucket.get("sample_size"),
                "avg_predicted_confidence": bucket.get("avg_predicted_confidence"),
                "realized_win_rate": bucket.get("realized_win_rate"),
                "avg_realized_r": bucket.get("avg_realized_r"),
                "generated_at": profile.get("generated_at"),
            }
        )

    for item in list(profile.get("top_penalties") or []):
        rows.append(
            {
                "section": "top_penalty",
                "key": item.get("label") or item.get("component"),
                "label": item.get("label") or item.get("component"),
                "penalty": item.get("penalty"),
                "count": item.get("count"),
                "avg_severity": item.get("avg_severity"),
                "top_failure_source": item.get("top_failure_source"),
                "kind": item.get("kind"),
                "generated_at": profile.get("generated_at"),
            }
        )

    for item in list(effectiveness.get("adjustments") or []):
        rows.append(
            {
                "section": "effectiveness_adjustment",
                "key": item.get("adjustment_id"),
                "label": item.get("label"),
                "status": item.get("status"),
                "trades_before": item.get("trades_before"),
                "trades_after": item.get("trades_after"),
                "win_rate_before": item.get("win_rate_before"),
                "win_rate_after": item.get("win_rate_after"),
                "avg_r_before": item.get("avg_r_before"),
                "avg_r_after": item.get("avg_r_after"),
                "loss_severity_before": item.get("loss_severity_before"),
                "loss_severity_after": item.get("loss_severity_after"),
                "status_reason": item.get("status_reason"),
                "generated_at": effectiveness.get("generated_at"),
            }
        )

    for index, note in enumerate(list(effectiveness.get("safety_notes") or []), start=1):
        rows.append(
            {
                "section": "safety_note",
                "key": f"note-{index}",
                "label": f"Safety Note {index}",
                "value": note,
                "generated_at": effectiveness.get("generated_at"),
            }
        )

    buffer = io.StringIO()
    fieldnames = sorted({key for row in rows for key in row.keys()})
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="learning.csv"'},
    )


@router.get("/api/v3/learning/effectiveness")
@router.get("/api/admin/learning/effectiveness")
def get_learning_effectiveness(
    lookback_days: int = Query(default=30, ge=0, le=3650),
    min_samples: int = Query(default=5, ge=1, le=1000),
):
    return {
        "ok": True,
        "report": effectiveness_service.get_effectiveness_report(
            lookback_days=lookback_days,
            min_samples=min_samples,
        ),
    }


@router.get("/api/v3/learning/effectiveness/{adjustment_id}")
@router.get("/api/admin/learning/effectiveness/{adjustment_id}")
def get_learning_effectiveness_adjustment(
    adjustment_id: str,
    lookback_days: int = Query(default=30, ge=0, le=3650),
    min_samples: int = Query(default=5, ge=1, le=1000),
):
    report = effectiveness_service.get_effectiveness_report(
        lookback_days=lookback_days,
        min_samples=min_samples,
    )
    item = next((row for row in report.get("adjustments") or [] if row.get("adjustment_id") == adjustment_id), None)
    return {
        "ok": item is not None,
        "item": item,
        "report_meta": {
            "generated_at": report.get("generated_at"),
            "lookback_days": report.get("lookback_days"),
            "overall_health_score": report.get("overall_health_score", report.get("health_score")),
        },
    }
