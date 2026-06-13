"""Simulation routes for v4."""

from __future__ import annotations

import asyncio
import json
import logging
from queue import Empty

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from runtime.db.repos.simulation_preset_repo import SimulationPresetRepository
from runtime.db.session import session_scope
from runtime.services.simulation_service import SimulationService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["simulations"])
simulation_service = SimulationService()
simulation_preset_repo = SimulationPresetRepository()


def _sse_payload(event: dict) -> str:
    return f"data: {json.dumps(event, default=str, separators=(',', ':'))}\n\n"


class CreateSimulationRequest(BaseModel):
    name: str | None = None
    requested_by: str = "interface"
    status: str | None = None
    parameters: dict = Field(default_factory=dict)
    period_start: str | None = None
    period_end: str | None = None
    symbols: list[str] = Field(default_factory=list)
    intervals: list[str] = Field(default_factory=list)
    modes: list[str] = Field(default_factory=list)
    capital: float = 50_000
    risk_per_trade_pct: float = 1.0
    max_hold_bars: int | None = None
    min_confidence: float | None = None
    scan_step_bars: int = 1
    scan_workers: int = 4
    time_forward_step_bars: int = 1
    simulation_profile_id: str | None = None
    simulation_profile: dict = Field(default_factory=dict)
    execution_settings: dict = Field(default_factory=dict)


class UpdateSimulationRequest(BaseModel):
    status: str | None = None
    metrics: dict | None = None
    started: bool = False
    finished: bool = False


class SimulationResultsRequest(BaseModel):
    results: list[dict]


class SimulationPresetRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    profile_id: str | None = None
    symbols: list[str] = Field(default_factory=list)
    intervals: list[str] = Field(default_factory=list)
    modes: list[str] = Field(default_factory=list)
    period_start: str | None = None
    period_end: str | None = None
    capital: float | None = None
    execution_settings: dict = Field(default_factory=dict)
    created_by: str | None = None
    updated_by: str | None = None
    is_shared: bool = False
    tags: list[str] = Field(default_factory=list)


class SimulationPresetPatchRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    profile_id: str | None = None
    symbols: list[str] | None = None
    intervals: list[str] | None = None
    modes: list[str] | None = None
    period_start: str | None = None
    period_end: str | None = None
    capital: float | None = None
    execution_settings: dict | None = None
    updated_by: str | None = None
    is_shared: bool | None = None
    tags: list[str] | None = None


@router.get("/api/v3/simulation-presets")
@router.get("/api/admin/simulation-presets")
def list_simulation_presets(limit: int = Query(default=100, ge=1, le=500)):
    with session_scope() as session:
        return {"ok": True, "presets": simulation_preset_repo.list_presets(session, limit=limit)}


@router.post("/api/v3/simulation-presets")
@router.post("/api/admin/simulation-presets")
def create_simulation_preset(payload: SimulationPresetRequest):
    try:
        with session_scope() as session:
            preset = simulation_preset_repo.create_preset(session, payload.model_dump(exclude_none=True))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"ok": True, "preset": preset}


@router.patch("/api/v3/simulation-presets/{preset_id}")
@router.patch("/api/admin/simulation-presets/{preset_id}")
def update_simulation_preset(preset_id: int, payload: SimulationPresetPatchRequest):
    try:
        with session_scope() as session:
            preset = simulation_preset_repo.update_preset(session, preset_id, payload.model_dump(exclude_unset=True, exclude_none=True))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not preset:
        raise HTTPException(status_code=404, detail="Simulation preset not found")
    return {"ok": True, "preset": preset}


@router.delete("/api/v3/simulation-presets/{preset_id}")
@router.delete("/api/admin/simulation-presets/{preset_id}")
def delete_simulation_preset(preset_id: int):
    with session_scope() as session:
        deleted = simulation_preset_repo.delete_preset(session, preset_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Simulation preset not found")
    return {"ok": True, "deleted": True, "preset_id": preset_id}


@router.get("/api/v3/simulations")
@router.get("/api/admin/simulations")
def get_simulations(limit: int = Query(default=50, ge=1, le=250)):
    return simulation_service.list_runs(limit=limit)


@router.post("/api/v3/simulations")
@router.post("/api/admin/simulations")
def create_simulation(payload: CreateSimulationRequest, background_tasks: BackgroundTasks):
    return simulation_service.create_and_start_run(payload.model_dump(), background_tasks=background_tasks)


@router.get("/api/v3/simulations/{run_id}")
@router.get("/api/admin/simulations/{run_id}")
def get_simulation(run_id: int):
    result = simulation_service.get_run_detail(run_id)
    if not result:
        raise HTTPException(status_code=404, detail="Simulation run not found")
    return result


@router.get("/api/v3/simulations/{run_id}/decision-traces")
@router.get("/api/admin/simulations/{run_id}/decision-traces")
def get_simulation_decision_traces(
    run_id: int,
    symbol: str | None = None,
    interval: str | None = None,
    mode: str | None = None,
    direction: str | None = None,
    signal_status: str | None = None,
    runtime_filter_reason: str | None = None,
    reason: str | None = None,
    fallback_used: bool | None = None,
    min_confidence: float | None = None,
    max_confidence: float | None = None,
    start_ts: str | None = None,
    end_ts: str | None = None,
    limit: int = Query(default=250, ge=1, le=1000),
    cursor: int | None = Query(default=None, ge=1),
    sort: str = Query(default="asc", pattern="^(asc|desc)$"),
):
    result = simulation_service.get_decision_traces(
        run_id,
        symbol=symbol,
        interval=interval,
        mode=mode,
        direction=direction,
        signal_status=signal_status,
        runtime_filter_reason=runtime_filter_reason,
        reason=reason,
        fallback_used=fallback_used,
        min_confidence=min_confidence,
        max_confidence=max_confidence,
        start_ts=start_ts,
        end_ts=end_ts,
        limit=limit,
        cursor=cursor,
        sort=sort,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Simulation run not found")
    return result


@router.get("/api/v3/simulations/{run_id}/decision-trace-summary")
@router.get("/api/admin/simulations/{run_id}/decision-trace-summary")
def get_simulation_decision_trace_summary(run_id: int):
    result = simulation_service.get_decision_trace_summary(run_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Simulation run not found")
    return result


@router.get("/api/v3/simulations/{run_id}/diagnostics")
@router.get("/api/admin/simulations/{run_id}/diagnostics")
def get_simulation_diagnostics(run_id: int):
    result = simulation_service.get_diagnostics(run_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Simulation run not found")
    return result


@router.get("/api/v3/simulations/{run_id}/confidence-histogram")
@router.get("/api/admin/simulations/{run_id}/confidence-histogram")
def get_simulation_confidence_histogram(run_id: int):
    result = simulation_service.get_confidence_histogram(run_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Simulation run not found")
    return result


@router.get("/api/v3/simulations/{run_id}/what-if")
@router.get("/api/admin/simulations/{run_id}/what-if")
def get_simulation_what_if(
    run_id: int,
    min_confidence: float | None = None,
    fees_bps: float | None = None,
    slippage_bps: float | None = None,
    max_hold_bars: int | None = None,
    risk_per_trade: float | None = None,
):
    result = simulation_service.get_what_if(
        run_id,
        min_confidence=min_confidence,
        fees_bps=fees_bps,
        slippage_bps=slippage_bps,
        max_hold_bars=max_hold_bars,
        risk_per_trade=risk_per_trade,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Simulation run not found")
    return result


@router.get("/api/v3/simulations/{run_id}/parity-report")
@router.get("/api/admin/simulations/{run_id}/parity-report")
def get_simulation_parity_report(run_id: int):
    result = simulation_service.get_parity_report(run_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Simulation run not found")
    return result


@router.post("/api/v3/simulations/{run_id}/failure-analysis")
@router.post("/api/admin/simulations/{run_id}/failure-analysis")
def analyze_simulation_failures(run_id: int, persist: bool = Query(default=True), profile_id: str | None = Query(default=None)):
    try:
        result = simulation_service.analyze_failures(run_id, persist=persist, profile_id=profile_id)
    except Exception as exc:
        logger.exception(
            "simulation failure-analysis route failed run_id=%s persist=%s profile_id=%s",
            run_id,
            persist,
            profile_id,
        )
        raise HTTPException(status_code=500, detail=f"Simulation failure analysis failed: {exc}") from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Simulation run not found")
    return result


@router.get("/api/v3/simulations/{run_id}/exports")
@router.get("/api/admin/simulations/{run_id}/exports")
def export_simulation(
    run_id: int,
    target: str = Query(default="decision_traces", pattern="^(trades|decision_traces|skip_breakdown|skip_samples|confidence_histogram|per_symbol_summary|per_mode_summary|diagnostics_summary|parity_report)$"),
    format: str = Query(default="json", pattern="^(json|csv|jsonl)$"),
    limit: int | None = Query(default=None, ge=1, le=50000),
):
    result = simulation_service.export_run(run_id, target=target, format=format, limit=limit)
    if result is None:
        raise HTTPException(status_code=404, detail="Simulation run not found")
    if "json" in result:
        return result["json"]
    return Response(content=result.get("content") or "", media_type=result.get("media_type") or "application/octet-stream")


@router.patch("/api/v3/simulations/{run_id}")
@router.patch("/api/admin/simulations/{run_id}")
def update_simulation(run_id: int, payload: UpdateSimulationRequest):
    result = simulation_service.update_run(run_id, payload.model_dump(exclude_none=True))
    if not result:
        raise HTTPException(status_code=404, detail="Simulation run not found")
    return result


@router.post("/api/v3/simulations/{run_id}/stop")
@router.post("/api/admin/simulations/{run_id}/stop")
def stop_simulation(run_id: int):
    result = simulation_service.stop_run(run_id)
    if not result:
        raise HTTPException(status_code=404, detail="Simulation run not found")
    return result


@router.post("/api/v3/simulations/{run_id}/force-stop")
@router.post("/api/admin/simulations/{run_id}/force-stop")
def force_stop_simulation(run_id: int):
    result = simulation_service.force_stop_run(run_id)
    if not result:
        raise HTTPException(status_code=404, detail="Simulation run not found")
    return result


@router.get("/api/v3/simulations/{run_id}/events-sse")
@router.get("/api/admin/simulations/{run_id}/events-sse")
async def stream_simulation_events_sse(run_id: int):
    queue = simulation_service.trace_hub.subscribe(run_id)

    async def event_generator():
        try:
            detail = simulation_service.get_run_detail(run_id)
            if detail:
                yield _sse_payload({"type": "snapshot", "run_id": run_id, "run": detail.get("run"), "results": detail.get("results", [])})
            while True:
                try:
                    event = await asyncio.to_thread(queue.get, True, 10.0)
                    yield _sse_payload(event)
                except Empty:
                    yield _sse_payload({"type": "heartbeat", "run_id": run_id})
        finally:
            simulation_service.trace_hub.unsubscribe(run_id, queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@router.websocket("/api/v3/simulations/{run_id}/events")
@router.websocket("/api/admin/simulations/{run_id}/events")
async def stream_simulation_events(websocket: WebSocket, run_id: int):
    await websocket.accept()
    queue = simulation_service.trace_hub.subscribe(run_id)
    try:
        detail = simulation_service.get_run_detail(run_id)
        if detail:
            await websocket.send_json({"type": "snapshot", "run_id": run_id, "run": detail.get("run"), "results": detail.get("results", [])})
        while True:
            try:
                event = await asyncio.to_thread(queue.get, True, 1.0)
                await websocket.send_json(event)
            except Empty:
                await websocket.send_json({"type": "heartbeat", "run_id": run_id})
    except WebSocketDisconnect:
        pass
    finally:
        simulation_service.trace_hub.unsubscribe(run_id, queue)


@router.post("/api/v3/simulations/{run_id}/results")
@router.post("/api/admin/simulations/{run_id}/results")
def insert_simulation_results(run_id: int, payload: SimulationResultsRequest):
    result = simulation_service.insert_results(run_id, payload.results)
    if not result:
        raise HTTPException(status_code=404, detail="Simulation run not found")
    return result
