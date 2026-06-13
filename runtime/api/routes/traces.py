"""Trace history routes for v4."""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Query, Response

from runtime.db.repos.runtime_profile_repo import PAPER_PROFILE_ID
from runtime.services.trace_service import TraceService

router = APIRouter(tags=["traces"])
trace_service = TraceService()


@router.get("/api/v3/traces")
@router.get("/api/admin/traces")
def get_traces(
    limit: int = Query(default=250, ge=1, le=5000),
    run_id: str | None = Query(default=None),
    symbol: str | None = Query(default=None),
    event_type: str | None = Query(default=None),
    decision: str | None = Query(default=None),
    profile_id: str = Query(default=PAPER_PROFILE_ID),
):
    return trace_service.get_snapshot(limit=limit, run_id=run_id, symbol=symbol, event_type=event_type, decision=decision, profile_id=profile_id)


@router.get("/api/v3/traces/export")
@router.get("/api/admin/traces/export")
def export_traces(
    limit: int = Query(default=1000, ge=1, le=5000),
    run_id: str | None = Query(default=None),
    symbol: str | None = Query(default=None),
    event_type: str | None = Query(default=None),
    decision: str | None = Query(default=None),
    format: str = Query(default="jsonl"),
    profile_id: str = Query(default=PAPER_PROFILE_ID),
):
    rows = trace_service.get_export_rows(limit=limit, run_id=run_id, symbol=symbol, event_type=event_type, decision=decision, profile_id=profile_id)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    export_format = format.lower()
    if export_format == "json":
        return {"count": len(rows), "items": rows}
    if export_format == "csv":
        fieldnames = list(rows[0].keys()) if rows else [
            "trace_id",
            "timestamp",
            "run_id",
            "event_type",
            "decision",
            "status",
            "source",
            "order_id",
            "symbol",
            "interval",
            "mode",
            "direction",
            "confidence",
            "regime",
            "reason_code",
            "reason_text",
            "summary",
            "no_trade_reason",
            "factors_json",
            "details_json",
            "signal_payload_json",
        ]
        out = io.StringIO()
        writer = csv.DictWriter(out, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
        return Response(
            out.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=trade-traces-{stamp}.csv"},
        )
    body = "\n".join(json.dumps(row, ensure_ascii=False) for row in rows)
    if body:
        body += "\n"
    return Response(
        body,
        media_type="application/x-ndjson",
        headers={"Content-Disposition": f"attachment; filename=trade-traces-{stamp}.jsonl"},
    )
