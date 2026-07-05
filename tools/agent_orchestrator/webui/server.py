"""server.py — Minimal Web UI for Agent Orchestrator.

Usage:
    python server.py                        # default :8765
    python server.py --port 9999 --host 0.0.0.0

Endpoints:
    GET  /                                 → index.html
    GET  /api/runs                          → run list
    GET  /api/runs/{run_id}                 → run + iteration details
    GET  /api/runs/{run_id}/log             → SSE log stream
    POST /api/runs/{run_id}/stop            → create STOP file
    POST /api/runs/{run_id}/inject           → write inject.json for strategist
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# ── paths ────────────────────────────────────────────────────────────────

_THIS_DIR = Path(__file__).resolve().parent
ORCHESTRATOR_DIR = _THIS_DIR.parent
RUNS_DIR = ORCHESTRATOR_DIR / "runs"
STOP_FILENAME = "STOP"
INJECT_FILENAME = "inject.json"

app = FastAPI(title="Agent Orchestrator UI", description="Monitor and intervene in orchestrator runs")

# Mount static files (index.html, etc.)
STATIC_DIR = _THIS_DIR / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# ── helpers ──────────────────────────────────────────────────────────────


def _read_json(path: Path) -> dict[str, Any]:
    """Read JSON file, return {} on any error."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _list_runs() -> list[dict[str, Any]]:
    """Return sorted list of runs with summary metadata."""
    if not RUNS_DIR.exists():
        return []

    runs: list[dict[str, Any]] = []
    for d in sorted(RUNS_DIR.iterdir(), reverse=True):
        if not d.is_dir() or d.name == ".gitkeep":
            continue

        summary = _read_json(d / "summary.json")
        # Derive started_at from directory name timestamp
        started_at = d.name[:22]  # YYYYMMDD_HHMMSS_ffffff

        # Get latest verdict from most recent iteration if summary is incomplete
        verdict = summary.get("final_verdict", "?")
        iters_run = summary.get("iterations_run", "?")
        max_iters = summary.get("max_iters", "?")

        # Check if STILL running — no summary.json or partial data
        is_running = not (d / "summary.json").exists() or verdict in ("?",)

        runs.append({
            "id": d.name,
            "goal": summary.get("goal", "")[:80],
            "verdict": verdict if not is_running else "RUNNING",
            "iterations": iters_run,
            "max_iters": max_iters,
            "dry_run": summary.get("dry_run", False),
            "started_at": started_at,
            "has_stop": (d / STOP_FILENAME).exists(),
        })
    return runs


def _read_iter(iter_dir: Path) -> dict[str, Any]:
    """Read all iteration artifacts into a dict."""
    result: dict[str, Any] = {"name": iter_dir.name}

    json_files = [
        "strategist_request.json",
        "strategist_response.json",
        "gate_result.json",
        "git_snapshot.json",
        "summary.json",
    ]
    for fname in json_files:
        fp = iter_dir / fname
        if fp.exists():
            result[fname.replace(".json", "")] = _read_json(fp)
            result[fname.replace(".json", "") + "_path"] = str(fp)

    # Worker task text
    task_file = iter_dir / "worker_task.txt"
    if task_file.exists():
        text = task_file.read_text(encoding="utf-8")
        result["worker_task"] = text[:5000]
        result["worker_task_truncated"] = len(text) > 5000

    # Worker output (saved as JSON in controller)
    output_file = iter_dir / "worker_output.json"
    if output_file.exists():
        try:
            result["worker_output"] = json.loads(output_file.read_text(encoding="utf-8"))
        except Exception:
            result["worker_output"] = {"raw": output_file.read_text(encoding="utf-8")[:2000]}

    # Claude log — metadata only (full log streamed via SSE)
    log_file = iter_dir / "claude_stream.jsonl"
    if log_file.exists():
        st = log_file.stat()
        # Count lines efficiently without reading entire file
        line_count = 0
        try:
            with open(log_file, "rb") as lf:
                buf_size = 65536
                buf = lf.read(buf_size)
                while buf:
                    line_count += buf.count(b"\n")
                    buf = lf.read(buf_size)
        except Exception:
            line_count = 0
        result["log"] = {
            "size": st.st_size,
            "path": str(log_file),
            "lines": line_count,
        }

    return result


# ── routes ───────────────────────────────────────────────────────────────


@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/runs")
async def list_runs():
    return _list_runs()


@app.get("/api/runs/{run_id}")
async def get_run(run_id: str):
    run_dir = RUNS_DIR / run_id
    if not run_dir.is_dir():
        raise HTTPException(404, f"Run '{run_id}' not found")

    summary = _read_json(run_dir / "summary.json")
    goal = _read_json(run_dir / "goal.json")

    # List iterations sorted
    iters: list[dict[str, Any]] = []
    for d in sorted(run_dir.iterdir()):
        if d.name.startswith("iter_"):
            iters.append(_read_iter(d))

    # Inject file status
    inject_file = run_dir / INJECT_FILENAME
    has_pending_inject = inject_file.exists()

    return {
        "id": run_id,
        "summary": summary,
        "goal": goal,
        "iterations": iters,
        "has_pending_inject": has_pending_inject,
    }


@app.get("/api/runs/{run_id}/log")
async def stream_log(run_id: str):
    """SSE endpoint — streams claude log lines as they're written.

    On connect: immediately sends ALL existing content from the most
    recent iteration that HAS a log file.  Then polls every 1s for new
    content in that same file.  When a NEW iteration directory appears
    with its own log, switches to that.

    Always falls back to the latest iter **with a log** — never gets
    stuck on an empty iter directory.
    """
    run_dir = RUNS_DIR / run_id
    if not run_dir.is_dir():
        raise HTTPException(404, f"Run '{run_id}' not found")

    def _latest_log_path() -> tuple[str, Path] | None:
        """Return (iter_name, log_path) for the most recent iter that
        has a claude_stream.jsonl, or None if none exist."""
        iters = sorted([
            d for d in run_dir.iterdir()
            if d.is_dir() and d.name.startswith("iter_")
        ])
        for d in reversed(iters):
            lp = d / "claude_stream.jsonl"
            if lp.exists() and lp.stat().st_size > 0:
                return (d.name, lp)
        return None

    async def _event_stream():
        # Track iteration set to detect new ones
        prev_iters: set[str] = set()
        if run_dir.exists():
            prev_iters = {
                d.name for d in run_dir.iterdir()
                if d.is_dir() and d.name.startswith("iter_")
            }

        # Track current log file and how much we've sent
        current_iter_name: str | None = None
        current_log_path: Path | None = None
        last_size: int = 0

        # ── Phase 1: Send all existing content immediately ──
        found = _latest_log_path()
        if found is not None:
            current_iter_name, current_log_path = found
            last_size = current_log_path.stat().st_size
            # Read and send entire file in chunks
            yield (
                f"event: connected\n"
                f"data: {json.dumps({'run_id': run_id, 'iter': current_iter_name, 'log_size': last_size})}\n\n"
            )
            with open(current_log_path, "r", encoding="utf-8", errors="replace") as f:
                while True:
                    chunk = f.read(16384)  # 16KB chunks
                    if not chunk:
                        break
                    yield (
                        f"event: log\n"
                        f"data: {json.dumps({'chunk': chunk, 'iter': current_iter_name})}\n\n"
                    )
        else:
            yield (
                f"event: connected\n"
                f"data: {json.dumps({'run_id': run_id, 'iter': None, 'log_size': 0})}\n\n"
            )

        # ── Phase 2: Poll for new content ──
        while True:
            try:
                # 2a. Detect new iteration directories
                current_iters = {
                    d.name for d in run_dir.iterdir()
                    if d.is_dir() and d.name.startswith("iter_")
                }
                new_iters = current_iters - prev_iters
                if new_iters:
                    for name in sorted(new_iters):
                        yield (
                            f"event: new_iter\n"
                            f"data: {json.dumps({'iter': name})}\n\n"
                        )
                    prev_iters = current_iters
                    # Check if the new iter has a log — switch to it
                    new_found = _latest_log_path()
                    if new_found is not None and new_found[0] != current_iter_name:
                        current_iter_name, current_log_path = new_found
                        last_size = current_log_path.stat().st_size
                        yield (
                            f"event: switch\n"
                            f"data: {json.dumps({'iter': current_iter_name, 'log_size': last_size})}\n\n"
                        )
                        # Send the entire new log
                        with open(current_log_path, "r", encoding="utf-8", errors="replace") as f:
                            while True:
                                chunk = f.read(16384)
                                if not chunk:
                                    break
                                yield (
                                    f"event: log\n"
                                    f"data: {json.dumps({'chunk': chunk, 'iter': current_iter_name})}\n\n"
                                )

                # 2b. Check current log for new content
                if current_log_path is not None and current_log_path.exists():
                    st = current_log_path.stat()
                    if st.st_size > last_size:
                        with open(current_log_path, "r", encoding="utf-8", errors="replace") as f:
                            f.seek(last_size)
                            chunk = f.read(16384)
                            while chunk:
                                yield (
                                    f"event: log\n"
                                    f"data: {json.dumps({'chunk': chunk, 'iter': current_iter_name})}\n\n"
                                )
                                chunk = f.read(16384)
                            last_size = f.tell()
                elif current_log_path is None:
                    # No log yet — try to find one
                    found = _latest_log_path()
                    if found is not None:
                        current_iter_name, current_log_path = found
                        last_size = current_log_path.stat().st_size
                        yield (
                            f"event: switch\n"
                            f"data: {json.dumps({'iter': current_iter_name, 'log_size': last_size})}\n\n"
                        )
                        with open(current_log_path, "r", encoding="utf-8", errors="replace") as f:
                            while True:
                                chunk = f.read(16384)
                                if not chunk:
                                    break
                                yield (
                                    f"event: log\n"
                                    f"data: {json.dumps({'chunk': chunk, 'iter': current_iter_name})}\n\n"
                                )
                else:
                    # current_log_path existed but now gone (rotated?) — reset
                    current_log_path = None
                    current_iter_name = None
                    last_size = 0

            except Exception as exc:
                yield (
                    f"event: error\n"
                    f"data: {json.dumps({'error': str(exc)})}\n\n"
                )

            await asyncio.sleep(1)

    return StreamingResponse(
        _event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── command models ───────────────────────────────────────────────────────


class InjectInput(BaseModel):
    message: str


class StopOutput(BaseModel):
    status: str
    file: str


class InjectOutput(BaseModel):
    status: str
    message: str


# ── commands ─────────────────────────────────────────────────────────────


@app.post("/api/runs/{run_id}/stop", response_model=StopOutput)
async def stop_run(run_id: str):
    """Create STOP file to gracefully halt the orchestrator.

    Writes to both the run directory and the orchestrator root so the
    controller picks it up at the next iteration boundary.
    """
    run_dir = RUNS_DIR / run_id
    if not run_dir.is_dir():
        raise HTTPException(404, f"Run '{run_id}' not found")

    ts = datetime.now(timezone.utc).isoformat()

    # Write to run dir
    stop_file = run_dir / STOP_FILENAME
    stop_file.write_text(f"stopped_by_user_at_{ts}", encoding="utf-8")

    # Also write to orchestrator root (controller's _check_stop_file checks here)
    orch_stop = ORCHESTRATOR_DIR / STOP_FILENAME
    orch_stop.write_text(f"stopped_by_user_at_{ts}", encoding="utf-8")

    return StopOutput(status="stopped", file=str(stop_file))


@app.post("/api/runs/{run_id}/inject", response_model=InjectOutput)
async def inject_message(run_id: str, inp: InjectInput):
    """Write a user instruction for the strategist to see next iteration.

    The controller reads and consumes ``inject.json`` before each strategist
    call, so the message only affects the **next** iteration.
    """
    run_dir = RUNS_DIR / run_id
    if not run_dir.is_dir():
        raise HTTPException(404, f"Run '{run_id}' not found")

    inject_file = run_dir / INJECT_FILENAME
    inject_file.write_text(
        json.dumps(
            {
                "message": inp.message,
                "injected_at": datetime.now(timezone.utc).isoformat(),
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    return InjectOutput(status="injected", message=inp.message[:200])


# ── entry point ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = 8765
    host = "127.0.0.1"
    # Minimal arg parse for convenience
    for i, a in enumerate(sys.argv[1:]):
        if a == "--port" and i + 2 < len(sys.argv):
            port = int(sys.argv[i + 2])
        elif a == "--host" and i + 2 < len(sys.argv):
            host = sys.argv[i + 2]

    print(f"  Agent Orchestrator UI -> http://{host}:{port}")
    print(f"  Runs dir: {RUNS_DIR}")
    print(f"  Press Ctrl+C to stop\n")
    uvicorn.run(app, host=host, port=port, log_level="info")
