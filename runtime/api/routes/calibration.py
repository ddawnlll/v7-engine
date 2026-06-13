"""Calibration readiness routes for v4."""

from __future__ import annotations

from fastapi import APIRouter

from runtime.services.calibration_service import CalibrationStatusService

router = APIRouter(tags=["calibration"])
calibration_service = CalibrationStatusService()


@router.get("/api/v3/calibration/status")
@router.get("/api/admin/calibration/status")
def get_calibration_status(limit: int = 5000):
    return calibration_service.get_status(limit=limit)
