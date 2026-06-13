from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from runtime.api.deps import get_db_session
from runtime.db.session import session_scope
from runtime.services.v6_runtime_metrics_service import V6RuntimeMetricsService
from runtime.db.repos.settings_repo import SettingsRepository
from runtime.services.analyzer_engine_registry_service import AnalyzerEngineRegistryService
from v6.config import V6Config
from v6.evaluation.phase12_verification import classify_artifact_promotion_readiness
from v6.registry.model_registry import ModelArtifact, ModelRegistry, ModelRole
from v6.registry.promotion_service import PromotionEvidence, PromotionService
from v6.runtime.runtime_status import describe_runtime_status, refresh_runtime_champion

router = APIRouter(tags=["phase7-operate"])

config = V6Config.load(__import__('pathlib').Path('config/v6_config_defaults.json')).phase7_api
registry = ModelRegistry()
promotion_service = PromotionService(registry=registry)
analyzer_registry = AnalyzerEngineRegistryService()
settings_repo = SettingsRepository()
runtime_metrics_service = V6RuntimeMetricsService(V6Config.load(__import__('pathlib').Path('config/v6_config_defaults.json')))


class PromoteRequest(BaseModel):
    model_artifact_version: str
    expectancy_delta: float = 0.0
    win_rate: float = 0.0
    suppression_accuracy: float = 0.0
    holdout_period_utc: str = ""
    paper_outcome_sample_size: int = 0
    shadow_comparison_run_id: str | None = None


class RollbackRequest(BaseModel):
    reason: str = "manual rollback from operate control"


class ShadowEngineUpdateRequest(BaseModel):
    shadow_engine: str | None = None


def _load_model_metrics(artifact) -> dict[str, object]:
    payload = dict(artifact.payload or {})
    metrics_sources = [
        dict(payload.get("val_metrics") or {}),
        dict(payload.get("metrics") or {}),
    ]
    if artifact.validation_report_path and Path(artifact.validation_report_path).is_file():
        report = json.loads(Path(artifact.validation_report_path).read_text(encoding="utf-8"))
        metrics_sources.insert(0, dict(report.get("metrics") or {}))
        metrics_sources.insert(0, dict(report.get("val_metrics") or {}))
        metrics_sources.insert(0, dict((report.get("phase11") or {}).get("symbol_metrics") or {}))
    metrics: dict[str, object] = {}
    for source in metrics_sources:
        for key in ("win_rate", "expectancy_r", "avg_realized_r", "sample_size", "executed_count"):
            value = source.get(key)
            if value is not None and key not in metrics:
                metrics[key] = value
    if "sample_size" not in metrics:
        symbol_metrics = dict((json.loads(Path(artifact.validation_report_path).read_text(encoding="utf-8")) if artifact.validation_report_path and Path(artifact.validation_report_path).is_file() else {}).get("phase11", {}).get("symbol_metrics") or {})
        if symbol_metrics:
            metrics["sample_size"] = sum(int(dict(bucket or {}).get("executed_count", 0) or 0) for bucket in symbol_metrics.values())
    if "sample_size" not in metrics:
        symbol_breakdown = dict((json.loads(Path(artifact.validation_report_path).read_text(encoding="utf-8")) if artifact.validation_report_path and Path(artifact.validation_report_path).is_file() else {}).get("metrics", {}).get("symbol_breakdown") or {})
        if symbol_breakdown:
            metrics["sample_size"] = sum(int(dict(bucket or {}).get("executed_count", 0) or 0) for bucket in symbol_breakdown.values())
    if "sample_size" not in metrics and "executed_count" in metrics:
        metrics["sample_size"] = metrics["executed_count"]
    return metrics


def _read_json_file(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _discover_local_model_artifacts() -> list[ModelArtifact]:
    models_root = Path("data/models/v6_decision_engine")
    if not models_root.is_dir():
        return []

    discovered: list[ModelArtifact] = []
    for model_dir in sorted((path for path in models_root.iterdir() if path.is_dir()), key=lambda path: path.name, reverse=True):
        model_version = model_dir.name
        model_path = model_dir / "model.pkl"
        if not model_path.is_file():
            continue

        run_manifest = _read_json_file(model_dir / "run_manifest.json")
        training_summary = _read_json_file(model_dir / "training_summary.json")
        validation_report = _read_json_file(model_dir / "validation_report.json")
        effective_config = _read_json_file(model_dir / "effective_config.json")

        training_config = dict(training_summary.get("training_config") or {})
        payload = {
            **training_summary,
            "run_manifest": run_manifest,
            "metrics": dict(validation_report.get("metrics") or {}),
            "val_metrics": {
                **dict(validation_report.get("val_metrics") or {}),
                **({
                    "win_rate": validation_report.get("win_rate"),
                    "expectancy_r": validation_report.get("expectancy_r"),
                    "avg_realized_r": validation_report.get("avg_realized_r"),
                    "executed_count": validation_report.get("executed_count"),
                    "sample_size": validation_report.get("sample_size") or validation_report.get("executed_count"),
                }),
            },
            "effective_config": effective_config,
        }
        payload = {key: value for key, value in payload.items() if value not in (None, {}, [])}

        discovered.append(
            ModelArtifact(
                model_artifact_version=str(run_manifest.get("model_version") or validation_report.get("model_artifact_version") or model_version),
                engine_name=str(training_config.get("engine_name") or training_summary.get("engine_name") or models_root.name),
                engine_version=str(training_summary.get("engine_version") or run_manifest.get("model_version") or model_version),
                role=ModelRole.CANDIDATE,
                dataset_name=str(training_config.get("dataset_name") or training_summary.get("dataset_name") or ""),
                dataset_version=str(run_manifest.get("dataset_version") or training_summary.get("dataset_version") or validation_report.get("dataset_version") or ""),
                feature_schema_version=str(training_summary.get("feature_schema_version") or ""),
                snapshot_builder_version=str(training_summary.get("snapshot_builder_version") or effective_config.get("snapshot_builder_version") or ""),
                training_timestamp_utc=str(run_manifest.get("snapshot_created_at") or training_summary.get("training_timestamp_utc") or validation_report.get("generated_at_utc") or ""),
                validation_passed=bool(validation_report.get("validation_passed")),
                validation_report_path=str(model_dir / "validation_report.json") if (model_dir / "validation_report.json").is_file() else None,
                artifact_path=str(model_dir),
                payload=payload,
            )
        )
    return discovered


def _sync_local_models_into_registry() -> list[ModelArtifact]:
    discovered = _discover_local_model_artifacts()
    if not discovered:
        return registry.list_all()

    existing_by_version = {item.model_artifact_version: item for item in registry.list_all()}
    champion = registry.get_champion()
    champion_version = champion.model_artifact_version if champion else None

    for artifact in discovered:
        existing = existing_by_version.get(artifact.model_artifact_version)
        role = existing.role if existing else (ModelRole.CHAMPION if artifact.model_artifact_version == champion_version else ModelRole.CANDIDATE)
        registry.register(
            ModelArtifact(
                model_artifact_version=artifact.model_artifact_version,
                engine_name=artifact.engine_name,
                engine_version=artifact.engine_version,
                role=role,
                dataset_name=artifact.dataset_name,
                dataset_version=artifact.dataset_version,
                feature_schema_version=artifact.feature_schema_version,
                snapshot_builder_version=artifact.snapshot_builder_version,
                training_timestamp_utc=artifact.training_timestamp_utc,
                mlflow_run_id=existing.mlflow_run_id if existing else artifact.mlflow_run_id,
                promoted_at_utc=existing.promoted_at_utc if existing else artifact.promoted_at_utc,
                retired_at_utc=existing.retired_at_utc if existing else artifact.retired_at_utc,
                validation_passed=artifact.validation_passed,
                validation_report_path=artifact.validation_report_path,
                artifact_path=artifact.artifact_path,
                payload={**(existing.payload if existing else {}), **artifact.payload},
                created_at_utc=existing.created_at_utc if existing else artifact.created_at_utc,
                updated_at_utc=artifact.updated_at_utc,
            )
        )
    return registry.list_all()


def _summarize_model(artifact, champion) -> dict[str, object]:
    metrics = _load_model_metrics(artifact)
    champion_metrics = _load_model_metrics(champion) if champion and champion.model_artifact_version != artifact.model_artifact_version else {}
    win_rate = float(metrics.get("win_rate") or 0.0)
    expectancy_r = float(metrics.get("expectancy_r") or metrics.get("avg_realized_r") or 0.0)
    sample_size = int(metrics.get("sample_size") or metrics.get("executed_count") or 0)
    promotion_readiness = classify_artifact_promotion_readiness(artifact)
    promotion = dict(promotion_readiness.get("promotion_readiness") or {})
    release = dict(promotion_readiness.get("release_eligibility") or {})
    verification = dict(promotion_readiness.get("verification") or {})
    return {
        "model_artifact_version": artifact.model_artifact_version,
        "engine_name": artifact.engine_name,
        "engine_version": artifact.engine_version,
        "role": artifact.role.value,
        "dataset_name": artifact.dataset_name,
        "dataset_version": artifact.dataset_version,
        "feature_schema_version": artifact.feature_schema_version,
        "snapshot_builder_version": artifact.snapshot_builder_version,
        "training_timestamp_utc": artifact.training_timestamp_utc,
        "promoted_at_utc": artifact.promoted_at_utc,
        "retired_at_utc": artifact.retired_at_utc,
        "validation_passed": artifact.validation_passed,
        "validation_report_path": artifact.validation_report_path,
        "artifact_path": artifact.artifact_path,
        "metrics": {
            "win_rate": win_rate,
            "expectancy_r": expectancy_r,
            "sample_size": sample_size,
        },
        "promotion_readiness": promotion,
        "release_eligibility": release,
        "verification": verification,
        "comparison_to_champion": {
            "champion_model_artifact_version": champion.model_artifact_version if champion else None,
            "same_engine_family": bool(champion and champion.engine_name == artifact.engine_name),
            "same_engine_version": bool(champion and champion.engine_version == artifact.engine_version),
            "same_dataset_version": bool(champion and champion.dataset_version == artifact.dataset_version),
            "win_rate_delta": round(win_rate - float(champion_metrics.get("win_rate") or 0.0), 6) if champion and champion.model_artifact_version != artifact.model_artifact_version else 0.0,
            "expectancy_r_delta": round(expectancy_r - float(champion_metrics.get("expectancy_r") or champion_metrics.get("avg_realized_r") or 0.0), 6) if champion and champion.model_artifact_version != artifact.model_artifact_version else 0.0,
        },
    }


@router.get("/api/v3/operate/registry/champion")
def get_champion():
    artifact = registry.get_champion()
    return {
        "champion": asdict(artifact) if artifact else None,
        "shadow_engine": analyzer_registry.shadow_engine_name(),
        "active_engine": analyzer_registry.active_engine_name(),
        "available_engines": analyzer_registry.list_engines_raw(),
        "shadow_engine_selector": {
            "supported": True,
            "selected_engine": analyzer_registry.shadow_engine_name(),
            "active_engine": analyzer_registry.active_engine_name(),
            "available_engines": analyzer_registry.list_engines_raw(),
        },
    }


@router.get("/api/v3/operate/runtime/status")
def get_runtime_status():
    status = describe_runtime_status()
    return {"ok": True, **status}


@router.post("/api/v3/operate/runtime/refresh-champion")
def refresh_runtime_champion_route():
    status = refresh_runtime_champion()
    return {"ok": True, "action": "refresh_champion", **status}


@router.get("/api/v3/operate/registry/candidates")
def get_candidates():
    champion = registry.get_champion()
    candidates = registry.get_candidates()
    items = [asdict(item) for item in candidates]
    comparisons = []
    for item in candidates:
        comparisons.append({
            "model_artifact_version": item.model_artifact_version,
            "engine_name": item.engine_name,
            "engine_version": item.engine_version,
            "dataset_version": item.dataset_version,
            "training_timestamp_utc": item.training_timestamp_utc,
            "validation_passed": item.validation_passed,
            "role": item.role.value,
            "comparison_to_champion": {
                "champion_model_artifact_version": champion.model_artifact_version if champion else None,
                "same_engine_family": bool(champion and champion.engine_name == item.engine_name),
                "same_engine_version": bool(champion and champion.engine_version == item.engine_version),
                "same_dataset_version": bool(champion and champion.dataset_version == item.dataset_version),
            },
        })
    return {"items": items, "count": len(items), "comparisons": comparisons}


@router.get("/api/v3/operate/registry/models")
def get_registry_models():
    items_all = _sync_local_models_into_registry()
    champion = registry.get_champion()
    items = [_summarize_model(item, champion) for item in items_all]
    items.sort(
        key=lambda item: (
            float((item.get("metrics") or {}).get("expectancy_r") or 0.0),
            float((item.get("metrics") or {}).get("win_rate") or 0.0),
            str(item.get("training_timestamp_utc") or ""),
        ),
        reverse=True,
    )
    return {"ok": True, "count": len(items), "champion": asdict(champion) if champion else None, "items": items}


@router.post("/api/v3/operate/registry/promote")
def promote_candidate(payload: PromoteRequest):
    artifact = registry.get(payload.model_artifact_version)
    if artifact is None:
        raise HTTPException(status_code=404, detail="candidate not found")
    try:
        promotion_service.promote_candidate(
            payload.model_artifact_version,
            PromotionEvidence(
                expectancy_delta=payload.expectancy_delta,
                win_rate=payload.win_rate,
                suppression_accuracy=payload.suppression_accuracy,
                holdout_period_utc=payload.holdout_period_utc,
                paper_outcome_sample_size=payload.paper_outcome_sample_size,
                shadow_comparison_run_id=payload.shadow_comparison_run_id,
            ),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    updated = registry.get_champion()
    return {"ok": True, "champion": asdict(updated) if updated else None}


@router.post("/api/v3/operate/registry/rollback")
def rollback_champion(payload: RollbackRequest):
    promotion_service.rollback_champion(payload.reason)
    updated = registry.get_champion()
    return {"ok": True, "champion": asdict(updated) if updated else None}


@router.post("/api/v3/operate/shadow-engine")
def update_shadow_engine(payload: ShadowEngineUpdateRequest, session: Session = Depends(get_db_session)):
    available = {item.get("engine_name") for item in analyzer_registry.list_engines_raw()}
    selected = (payload.shadow_engine or "").strip() or None
    if selected is not None and selected not in available:
        raise HTTPException(status_code=400, detail="unknown shadow engine")
    saved = settings_repo.save_many(session, {"SHADOW_ENGINE": selected or ""})
    return {
        "ok": True,
        "shadow_engine": analyzer_registry.shadow_engine_name(),
        "settings": saved,
        "available_engines": analyzer_registry.list_engines_raw(),
    }


@router.get("/api/v3/operate/control")
def get_operate_control():
    _sync_local_models_into_registry()
    champion = registry.get_champion()
    candidates = [asdict(item) for item in registry.get_candidates()]
    runtime_metrics = runtime_metrics_service.get_metrics()
    with session_scope() as session:
        latest_event = session.execute(
            text("SELECT decision_event_id, timestamp_utc, signal_status, decision_status, degraded_reason, fallback_used FROM decision_events ORDER BY timestamp_utc DESC LIMIT 1")
        ).mappings().first()
    return {
        "refresh_seconds": config.operate_control_refresh_seconds,
        "engine": {
            "active_engine": analyzer_registry.active_engine_name(),
            "shadow_engine": analyzer_registry.shadow_engine_name(),
            "champion": asdict(champion) if champion else None,
            "candidates": candidates,
        },
        "runtime": runtime_metrics,
        "latest_decision_event": dict(latest_event) if latest_event else None,
        "promotion_actions": {
            "promote_route": "/api/v3/operate/registry/promote",
            "rollback_route": "/api/v3/operate/registry/rollback",
            "shadow_engine_route": "/api/v3/operate/shadow-engine",
        },
    }


@router.get("/api/v3/operate/promotion-readiness")
def get_promotion_readiness():
    champion = registry.get_champion()
    candidates = registry.get_candidates()
    readiness = []
    for item in candidates:
        payload = dict(item.payload or {})
        metrics = dict(payload.get("val_metrics") or {})
        classification = classify_artifact_promotion_readiness(item)
        release_eligibility = dict(classification.get("release_eligibility") or {})
        verification = dict(classification.get("verification") or {})
        promotion_readiness = dict(classification.get("promotion_readiness") or {})
        readiness.append({
            "model_artifact_version": item.model_artifact_version,
            "engine_version": item.engine_version,
            "dataset_version": item.dataset_version,
            "validation_passed": item.validation_passed,
            "release_eligible": bool(release_eligibility.get("is_release_eligible")),
            "verification_passed": bool(verification.get("verification_passed")),
            "promotion_classification": promotion_readiness.get("classification"),
            "promotion_readiness": promotion_readiness,
            "release_eligibility": release_eligibility,
            "verification": verification,
            "val_metrics": metrics,
            "same_dataset_as_champion": bool(champion and champion.dataset_version == item.dataset_version),
            "prepare_promotion_route": "/api/v3/operate/registry/promote",
        })
    return {
        "champion": asdict(champion) if champion else None,
        "candidates": readiness,
        "rollback_route": "/api/v3/operate/registry/rollback",
    }


@router.get("/api/v3/trade/overview")
def get_trade_overview():
    champion = registry.get_champion()
    runtime_metrics = runtime_metrics_service.get_metrics()
    with session_scope() as session:
        latest_event = session.execute(
            text("SELECT decision_event_id, timestamp_utc, signal_status, decision_status, fallback_used, degraded_reason FROM decision_events ORDER BY timestamp_utc DESC LIMIT 1")
        ).mappings().first()
        latest_outcome = session.execute(
            text("SELECT trade_outcome_id, timestamp_utc, outcome_status, realized_r, outcome_label FROM trade_outcomes ORDER BY timestamp_utc DESC LIMIT 1")
        ).mappings().first()
    degraded = bool(runtime_metrics.get("fallback_rate_1h", 0.0)) or bool(runtime_metrics.get("timeout_rate_24h", 0.0))
    return {
        "engine": {
            "active_engine": analyzer_registry.active_engine_name(),
            "shadow_engine": analyzer_registry.shadow_engine_name(),
            "champion": asdict(champion) if champion else None,
        },
        "summary": {
            "refresh_seconds": config.trade_overview_refresh_seconds,
            "open_trade_count": 0,
            "last_scan_status": latest_event.get("decision_status") if latest_event else "UNKNOWN",
            "last_outcome_summary": dict(latest_outcome) if latest_outcome else None,
            "degraded": degraded,
            "fallback_rate_1h": runtime_metrics.get("fallback_rate_1h", 0.0),
            "timeout_rate_24h": runtime_metrics.get("timeout_rate_24h", 0.0),
        },
        "latest_decision_event": dict(latest_event) if latest_event else None,
        "runtime": runtime_metrics,
    }
