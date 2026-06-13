"""Realtime scan event stream routes."""

from __future__ import annotations

import asyncio
import json
from queue import Empty

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

from runtime.db.repos.runtime_profile_repo import PAPER_PROFILE_ID
from runtime.runtime.scan_event_bus import get_scan_event_bus, utc_now_iso

router = APIRouter(tags=["scan-events"])


def _sse_payload(event: dict) -> str:
    return f"data: {json.dumps(event, default=str, separators=(',', ':'))}\n\n"


@router.get("/api/v3/scans/events-sse")
@router.get("/api/admin/jobs/events-sse")
async def stream_scan_events_sse(
    profile_id: str = Query(default=PAPER_PROFILE_ID),
    run_id: str | None = Query(default=None),
):
    resolved_profile_id = str(profile_id or PAPER_PROFILE_ID)
    resolved_run_id = str(run_id).strip() if run_id is not None and str(run_id).strip() else None
    bus = get_scan_event_bus()
    queue = bus.subscribe(profile_id=resolved_profile_id, run_id=resolved_run_id)

    async def event_generator():
        try:
            while True:
                try:
                    event = await asyncio.to_thread(queue.get, True, 10.0)
                    yield _sse_payload(event)
                except Empty:
                    yield _sse_payload({
                        "type": "HEARTBEAT",
                        "timestamp": utc_now_iso(),
                        "profile_id": resolved_profile_id,
                        "run_id": resolved_run_id or "*",
                    })
        finally:
            bus.unsubscribe(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@router.websocket("/api/v3/scans/events")
@router.websocket("/api/admin/jobs/events")
async def stream_scan_events(
    websocket: WebSocket,
    profile_id: str = Query(default=PAPER_PROFILE_ID),
    run_id: str | None = Query(default=None),
):
    resolved_profile_id = str(profile_id or PAPER_PROFILE_ID)
    resolved_run_id = str(run_id).strip() if run_id is not None and str(run_id).strip() else None
    await websocket.accept()
    bus = get_scan_event_bus()
    queue = bus.subscribe(profile_id=resolved_profile_id, run_id=resolved_run_id)
    try:
        while True:
            try:
                event = await asyncio.to_thread(queue.get, True, 1.0)
                await websocket.send_json(event)
            except Empty:
                await websocket.send_json({
                    "type": "HEARTBEAT",
                    "timestamp": utc_now_iso(),
                    "profile_id": resolved_profile_id,
                    "run_id": resolved_run_id or "*",
                })
    except WebSocketDisconnect:
        pass
    finally:
        bus.unsubscribe(queue)
