"""Real-Time Mining Dashboard — FastAPI + Jinja2.

Monitors mining pipeline status, discovered rules, and system health.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import jinja2

logger = logging.getLogger(__name__)

app = FastAPI(title="AlphaForge Mining Dashboard", version="0.1.0")

# Templates
_template_dir = Path(__file__).resolve().parent / "templates"
_templates = Jinja2Templates(directory=str(_template_dir))

# Default reports path
_REPORTS_DIR = Path("reports/alphaforge/mining")


def _load_latest_summary() -> dict:
    """Load the most recent mining_summary.json."""
    if not _REPORTS_DIR.exists():
        return {"status": "no_data", "message": "No mining runs found"}
    runs = sorted(_REPORTS_DIR.iterdir())
    if not runs:
        return {"status": "no_data", "message": "No mining runs found"}
    latest = runs[-1]
    summary_file = latest / "mining_summary.json"
    if not summary_file.exists():
        return {"status": "no_data", "message": f"No summary in {latest.name}"}
    with open(summary_file) as f:
        return json.load(f)


@app.get("/")
async def index(request: Request):
    """Render the dashboard."""
    summary = _load_latest_summary()
    return _templates.TemplateResponse(
        "index.html",
        {"request": request, "summary": summary, "title": "AlphaForge Mining Dashboard"},
    )


@app.get("/api/status")
async def api_status():
    """JSON endpoint for live updates."""
    summary = _load_latest_summary()
    return JSONResponse(summary)
