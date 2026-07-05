"""Metrics routes for the V7 runtime.

Provides a metrics endpoint for monitoring and observability.
"""

from __future__ import annotations

from fastapi import APIRouter

from runtime.services.observability import get_metrics

router = APIRouter(tags=["metrics"])


@router.get("/api/v3/metrics")
def get_metrics_endpoint():
    """Get runtime metrics snapshot.

    Returns counters, gauges, and timer summaries.
    Metrics are in-memory and reset on process restart.
    """
    metrics = get_metrics()
    return metrics.snapshot()
