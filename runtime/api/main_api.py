"""Uvicorn entrypoint for the V7 Engine backend.

This file wires the FastAPI `app` created by `runtime.api.main.create_app`
so that uvicorn can discover it via `uvicorn runtime.api.main_api:app`.
"""

from runtime.api.main import create_app

app = create_app()
