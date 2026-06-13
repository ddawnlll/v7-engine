"""Storage and operator tooling routes for v4."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query
from pydantic import BaseModel, Field

from runtime.services.storage_service import StorageService

router = APIRouter(tags=["storage"])
storage_service = StorageService()


class StorageBackendStatusResponse(BaseModel):
    backend: str
    healthy: bool
    detail: str | None
    counts: dict[str, int]
    total_size_bytes: int | None = None


class StorageStateResponse(BaseModel):
    mode: str
    label: str
    note: str


class StorageStatusResponse(BaseModel):
    generated_at: str
    postgres: StorageBackendStatusResponse
    state: StorageStateResponse
    clear_groups: list[dict[str, Any]] = Field(default_factory=list)


class StorageExportResponse(BaseModel):
    exported_at: str
    store: str
    kind: str
    counts: dict[str, int]
    state: dict[str, Any]
    runtime_settings: dict[str, str]
    candles: list[dict]
    scan_runs: list[dict]
    signals: list[dict]
    orders: list[dict]
    fills: list[dict]
    positions: list[dict]
    portfolio_snapshots: list[dict]
    alerts: list[dict]
    failures: list[dict]


class StorageMutationResponse(BaseModel):
    store: str
    mode: str
    counts: dict[str, int]
    current_counts: dict[str, int]
    dry_run: bool = False
    cleared_components: list[str] = Field(default_factory=list)
    cleared_group: str | None = None


class StorageClearComponentsRequest(BaseModel):
    components: list[str] = Field(default_factory=list)


class StorageTrashEntryResponse(BaseModel):
    trash_id: str
    archived_at: str | None = None
    expires_at: str | None = None
    operation: str | None = None
    profile_id: str | None = None
    components: list[str] = Field(default_factory=list)
    counts: dict[str, int] = Field(default_factory=dict)
    path: str | None = None


class StorageTrashDeleteResponse(BaseModel):
    trash_id: str
    deleted_forever: bool


@router.get("/api/v3/storage/status", response_model=StorageStatusResponse)
def get_storage_status(profile_id: str | None = Query(default=None)) -> StorageStatusResponse:
    payload = storage_service.get_status(profile_id=profile_id)
    return StorageStatusResponse(**payload)


@router.post("/api/v3/storage/export", response_model=StorageExportResponse)
def export_storage(store: str = Query(default="postgres"), profile_id: str | None = Query(default=None)) -> StorageExportResponse:
    try:
        payload = storage_service.export_operational_state(store=store, profile_id=profile_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return StorageExportResponse(**payload)


@router.post("/api/v3/storage/import", response_model=StorageMutationResponse)
def import_storage(
    payload: dict = Body(default_factory=dict),
    store: str = Query(default="postgres"),
    dry_run: bool = Query(default=False),
    confirm_phrase: str | None = Query(default=None),
) -> StorageMutationResponse:
    try:
        result = storage_service.import_operational_state(payload, store=store, dry_run=dry_run, confirm_phrase=confirm_phrase)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return StorageMutationResponse(**result)


@router.post("/api/v3/storage/seed", response_model=StorageMutationResponse)
def seed_storage(
    store: str = Query(default="postgres"),
    mode: str = Query(default="seed"),
    confirm_phrase: str | None = Query(default=None),
) -> StorageMutationResponse:
    try:
        result = storage_service.seed_operational_state(store=store, mode=mode, confirm_phrase=confirm_phrase)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return StorageMutationResponse(**result)


@router.post("/api/v3/storage/clear", response_model=StorageMutationResponse)
def clear_storage(
    store: str = Query(default="postgres"),
    keep_settings: bool = Query(default=False),
    profile_id: str | None = Query(default=None),
    confirm_phrase: str | None = Query(default=None),
) -> StorageMutationResponse:
    try:
        result = storage_service.clear_operational_state(store=store, keep_settings=keep_settings, profile_id=profile_id, confirm_phrase=confirm_phrase)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return StorageMutationResponse(**result)


@router.post("/api/v3/storage/clear-components", response_model=StorageMutationResponse)
def clear_storage_components(
    request: StorageClearComponentsRequest = Body(default_factory=StorageClearComponentsRequest),
    store: str = Query(default="postgres"),
    profile_id: str | None = Query(default=None),
    confirm_phrase: str | None = Query(default=None),
) -> StorageMutationResponse:
    try:
        result = storage_service.clear_components(store=store, components=request.components, profile_id=profile_id, confirm_phrase=confirm_phrase)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return StorageMutationResponse(**result)


@router.get("/api/v3/storage/trash", response_model=list[StorageTrashEntryResponse])
def list_storage_trash() -> list[StorageTrashEntryResponse]:
    return [StorageTrashEntryResponse(**item) for item in storage_service.list_trash_entries()]


@router.delete("/api/v3/storage/trash/{trash_id}", response_model=StorageTrashDeleteResponse)
def delete_storage_trash_entry(trash_id: str, confirm_phrase: str | None = Query(default=None)) -> StorageTrashDeleteResponse:
    try:
        payload = storage_service.delete_trash_entry(trash_id, confirm_phrase=confirm_phrase)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return StorageTrashDeleteResponse(**payload)


@router.post("/api/v3/storage/clear-group", response_model=StorageMutationResponse)
def clear_storage_group(
    store: str = Query(default="postgres"),
    group_id: str = Query(...),
    profile_id: str | None = Query(default=None),
    confirm_phrase: str | None = Query(default=None),
) -> StorageMutationResponse:
    try:
        result = storage_service.clear_group(store=store, group_id=group_id, profile_id=profile_id, confirm_phrase=confirm_phrase)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return StorageMutationResponse(**result)
