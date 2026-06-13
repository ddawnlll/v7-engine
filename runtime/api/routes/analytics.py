"""Composite trade analytics routes."""

from __future__ import annotations

from fastapi import APIRouter, Query
from fastapi.responses import PlainTextResponse

from runtime.services.swing_patch_validation_service import SwingPatchValidationService
from runtime.services.trade_analytics_service import TradeAnalyticsService

router = APIRouter(tags=["analytics"])
service = TradeAnalyticsService()
validation_service = SwingPatchValidationService(service)


@router.get("/api/v3/analytics")
@router.get("/api/admin/analytics")
def get_trade_analytics(
    lookback_days: int = Query(default=30, ge=0, le=3650),
    min_samples: int = Query(default=10, ge=1, le=1000),
    mode: str | None = Query(default=None),
    symbol: str | None = Query(default=None),
    interval: str | None = Query(default=None),
    direction: str | None = Query(default=None),
):
    return service.get_payload(
        lookback_days=lookback_days,
        min_samples=min_samples,
        mode=mode,
        symbol=symbol,
        interval=interval,
        direction=direction,
    )


@router.get("/api/v3/analytics/export", response_class=PlainTextResponse)
@router.get("/api/admin/analytics/export", response_class=PlainTextResponse)
def export_trade_analytics(
    lookback_days: int = Query(default=30, ge=0, le=3650),
    mode: str | None = Query(default=None),
    symbol: str | None = Query(default=None),
    interval: str | None = Query(default=None),
    direction: str | None = Query(default=None),
):
    return PlainTextResponse(
        service.export_csv(
            lookback_days=lookback_days,
            mode=mode,
            symbol=symbol,
            interval=interval,
            direction=direction,
        ),
        media_type="text/csv; charset=utf-8",
    )


@router.get("/api/v3/analytics/swing-patch-validation")
@router.get("/api/admin/analytics/swing-patch-validation")
def get_swing_patch_validation(
    lookback_days: int = Query(default=30, ge=0, le=3650),
    interval_min_minutes: int = Query(default=60, ge=1, le=10080),
):
    return validation_service.get_validation_payload(
        lookback_days=lookback_days,
        interval_min_minutes=interval_min_minutes,
    )


@router.get("/api/v3/analytics/swing-patch-validation/export", response_class=PlainTextResponse)
@router.get("/api/admin/analytics/swing-patch-validation/export", response_class=PlainTextResponse)
def export_swing_patch_validation(
    lookback_days: int = Query(default=30, ge=0, le=3650),
    interval_min_minutes: int = Query(default=60, ge=1, le=10080),
):
    return PlainTextResponse(
        validation_service.export_csv(
            lookback_days=lookback_days,
            interval_min_minutes=interval_min_minutes,
        ),
        media_type="text/csv; charset=utf-8",
    )
