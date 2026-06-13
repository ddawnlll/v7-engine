from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import text

from runtime.db.session import session_scope
from runtime.services.v6_runtime_metrics_service import V6RuntimeMetricsService
from v6.config import V6Config
from v6.evaluation.expectancy_eval import evaluate_expectancy
from v6.evaluation.regime_eval import evaluate_regimes
from v6.evaluation.shadow_compare import compare_shadow_events

router = APIRouter(tags=["phase7-review"])


_full_config = V6Config.load(__import__('pathlib').Path('config/v6_config_defaults.json'))
config = _full_config.phase7_api
phase8_config = _full_config.phase8
runtime_metrics_service = V6RuntimeMetricsService(_full_config)


def _safe_load_json_file(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _collect_dataset_manifests(limit: int) -> list[dict[str, Any]]:
    datasets_root = Path(_full_config.paths.datasets_root)
    if not datasets_root.exists():
        return []
    manifests: list[dict[str, Any]] = []
    for path in datasets_root.glob("*/**/manifest.json"):
        payload = _safe_load_json_file(path)
        if not payload:
            continue
        payload["manifest_path"] = str(path)
        manifests.append(payload)
    manifests.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    return manifests[:limit]


def _collect_model_artifacts(limit: int) -> list[dict[str, Any]]:
    models_root = Path(_full_config.paths.models_root)
    if not models_root.exists():
        return []
    items: list[dict[str, Any]] = []
    for path in models_root.glob("**/model.pkl"):
        stat = path.stat()
        items.append({
            "artifact_path": str(path),
            "engine_name": path.parent.parent.name if len(path.parents) >= 2 else path.parent.name,
            "model_artifact_version": path.parent.name,
            "size_bytes": stat.st_size,
            "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        })
    items.sort(key=lambda item: str(item.get("modified_at") or ""), reverse=True)
    return items[:limit]


def _collect_backfill_coverage(limit: int) -> list[dict[str, Any]]:
    candles_root = Path(_full_config.market_data.candles_root)
    if not candles_root.exists():
        return []
    rows: list[dict[str, Any]] = []
    for symbol_config in _full_config.market_data.symbols:
        for interval in _full_config.market_data.required_intervals + _full_config.market_data.optional_intervals:
            interval_root = candles_root / interval / symbol_config.symbol
            month_files = sorted(interval_root.glob("*.parquet")) if interval_root.exists() else []
            legacy_file = candles_root / f"{symbol_config.symbol}_{interval.upper()}.parquet"
            if legacy_file.exists():
                stat = legacy_file.stat()
                rows.append({
                    "symbol": symbol_config.symbol,
                    "interval": interval,
                    "enabled": symbol_config.enabled,
                    "source": "legacy_single_file",
                    "file_count": 1,
                    "latest_file": legacy_file.name,
                    "latest_update_utc": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                })
                continue
            latest_update = None
            latest_file = None
            if month_files:
                stat = month_files[-1].stat()
                latest_file = month_files[-1].name
                latest_update = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
            rows.append({
                "symbol": symbol_config.symbol,
                "interval": interval,
                "enabled": symbol_config.enabled,
                "source": "partitioned_monthly",
                "file_count": len(month_files),
                "latest_file": latest_file,
                "latest_update_utc": latest_update,
            })
    rows.sort(key=lambda item: (not bool(item.get("enabled")), item["symbol"], item["interval"]))
    return rows[:limit]


def _iso_days_ago(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def _limit_or_default(limit: int | None) -> int:
    value = int(limit or config.default_page_limit)
    return max(1, min(value, int(config.max_page_limit)))


def _loads(payload: str | None) -> dict[str, Any]:
    if not payload:
        return {}
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _decision_event_from_row(row: Any) -> dict[str, Any]:
    payload = _loads(getattr(row, "payload_json", None))
    if payload:
        return payload
    return {
        "identity": {
            "decision_event_id": row.decision_event_id,
            "request_id": row.request_id,
            "run_id": row.run_id,
            "timestamp_utc": row.timestamp_utc,
        },
        "lineage": {
            "engine_name": row.engine_name,
            "engine_version": row.engine_version,
            "request_kind": row.request_kind,
            "snapshot_builder_version": row.snapshot_builder_version,
            "feature_schema_version": row.feature_schema_version,
        },
        "scope": {
            "symbol": row.symbol,
            "interval": row.interval,
            "mode": payload.get("scope", {}).get("mode"),
        },
        "decision_summary": {
            "signal_status": row.signal_status,
            "decision_status": row.decision_status,
            "is_actionable": row.is_actionable,
            "recommended_action": row.recommended_action,
            "direction": row.direction,
            "confidence": row.confidence,
        },
        "runtime_interpretation": {
            "deterministic_alignment": row.deterministic_alignment,
            "deterministic_block": row.deterministic_block,
            "fallback_used": row.fallback_used,
            "degraded_reason": row.degraded_reason,
        },
        "outcome_linkage": {
            "trade_outcome_id": row.trade_outcome_id,
        },
        "contract": {
            "event_schema_version": row.event_schema_version,
        },
        "request_summary": payload.get("request_summary", {}),
        "observability": payload.get("observability", {}),
    }


def _trade_outcome_from_row(row: Any) -> dict[str, Any]:
    payload = _loads(getattr(row, "payload_json", None))
    if payload:
        return payload
    return {
        "identity": {
            "trade_outcome_id": row.trade_outcome_id,
            "decision_event_id": row.decision_event_id,
            "timestamp_utc": row.timestamp_utc,
        },
        "lineage": {
            "request_id": row.request_id,
            "outcome_source": row.outcome_source,
        },
        "execution_summary": {
            "execution_path": row.execution_path,
        },
        "resolution_status": {
            "outcome_status": row.outcome_status,
            "is_final": row.is_final,
        },
        "realized_outcome": {
            "realized_return": row.realized_return,
            "realized_r": row.realized_r,
        },
        "quality_interpretation": {
            "outcome_label": row.outcome_label,
            "is_good_decision": row.is_good_decision,
        },
        "contract": {
            "outcome_schema_version": row.outcome_schema_version,
        },
    }


@router.get("/api/v3/review/decision-events")
def list_decision_events(
    run_id: str | None = None,
    symbol: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int | None = Query(default=None, ge=1),
):
    clauses = ["1=1"]
    params: dict[str, Any] = {"limit": _limit_or_default(limit)}
    if run_id:
        clauses.append("run_id = :run_id")
        params["run_id"] = run_id
    if symbol:
        clauses.append("symbol = :symbol")
        params["symbol"] = symbol
    if date_from:
        clauses.append("timestamp_utc >= :date_from")
        params["date_from"] = date_from
    if date_to:
        clauses.append("timestamp_utc <= :date_to")
        params["date_to"] = date_to
    if not date_from and not date_to:
        params["date_from"] = _iso_days_ago(config.default_date_range_days)
        clauses.append("timestamp_utc >= :date_from")

    sql = text(
        f"""
        SELECT * FROM decision_events
        WHERE {' AND '.join(clauses)}
        ORDER BY timestamp_utc DESC
        LIMIT :limit
        """
    )
    with session_scope() as session:
        rows = session.execute(sql, params).mappings().all()
    items = [_decision_event_from_row(row) for row in rows]
    return {"items": items, "count": len(items), "limit": params["limit"]}


@router.get("/api/v3/review/decision-events/{event_id}")
def get_decision_event(event_id: str):
    sql = text("SELECT * FROM decision_events WHERE decision_event_id = :event_id LIMIT 1")
    with session_scope() as session:
        row = session.execute(sql, {"event_id": event_id}).mappings().first()
    if row is None:
        raise HTTPException(status_code=404, detail="decision event not found")
    return _decision_event_from_row(row)


@router.get("/api/v3/review/trade-outcomes")
def list_trade_outcomes(
    event_id: str | None = None,
    outcome_status: str | None = None,
    date_from: str | None = None,
    limit: int | None = Query(default=None, ge=1),
):
    clauses = ["1=1"]
    params: dict[str, Any] = {"limit": _limit_or_default(limit)}
    if event_id:
        clauses.append("decision_event_id = :event_id")
        params["event_id"] = event_id
    if outcome_status:
        clauses.append("outcome_status = :outcome_status")
        params["outcome_status"] = outcome_status
    if date_from:
        clauses.append("timestamp_utc >= :date_from")
        params["date_from"] = date_from
    else:
        params["date_from"] = _iso_days_ago(config.default_date_range_days)
        clauses.append("timestamp_utc >= :date_from")

    sql = text(
        f"""
        SELECT * FROM trade_outcomes
        WHERE {' AND '.join(clauses)}
        ORDER BY timestamp_utc DESC
        LIMIT :limit
        """
    )
    with session_scope() as session:
        rows = session.execute(sql, params).mappings().all()
    items = [_trade_outcome_from_row(row) for row in rows]
    return {"items": items, "count": len(items), "limit": params["limit"]}


@router.get("/api/v3/review/trade-outcomes/{outcome_id}")
def get_trade_outcome(outcome_id: str):
    sql = text("SELECT * FROM trade_outcomes WHERE trade_outcome_id = :outcome_id LIMIT 1")
    with session_scope() as session:
        row = session.execute(sql, {"outcome_id": outcome_id}).mappings().first()
    if row is None:
        raise HTTPException(status_code=404, detail="trade outcome not found")
    return _trade_outcome_from_row(row)


@router.get("/api/v3/review/engine-behavior")
def get_engine_behavior(date_from: str | None = None, date_to: str | None = None):
    clauses = ["1=1"]
    params: dict[str, Any] = {}
    if date_from:
        clauses.append("timestamp_utc >= :date_from")
        params["date_from"] = date_from
    else:
        params["date_from"] = _iso_days_ago(config.engine_behavior_window_days)
        clauses.append("timestamp_utc >= :date_from")
    if date_to:
        clauses.append("timestamp_utc <= :date_to")
        params["date_to"] = date_to

    with session_scope() as session:
        rows = session.execute(
            text(f"SELECT * FROM decision_events WHERE {' AND '.join(clauses)} ORDER BY timestamp_utc DESC"),
            params,
        ).mappings().all()
        outcome_rows = session.execute(
            text("SELECT * FROM trade_outcomes ORDER BY timestamp_utc DESC LIMIT :limit"),
            {"limit": config.max_page_limit},
        ).mappings().all()

    events = [_decision_event_from_row(row) for row in rows]
    outcomes = [_trade_outcome_from_row(row) for row in outcome_rows]
    total = len(events)
    fallback_count = sum(1 for item in events if bool(item.get("runtime_interpretation", {}).get("fallback_used", False)))
    block_count = sum(1 for item in events if bool(item.get("runtime_interpretation", {}).get("deterministic_block", False)))
    timeout_count = sum(
        1
        for item in events
        if "timeout" in str(item.get("runtime_interpretation", {}).get("degraded_reason", "")).lower()
    )
    return {
        "total_events": total,
        "fallback_rate": (fallback_count / total) if total else 0.0,
        "timeout_rate": (timeout_count / total) if total else 0.0,
        "block_rate": (block_count / total) if total else 0.0,
        "counts": {
            "fallback": fallback_count,
            "timeout": timeout_count,
            "block": block_count,
        },
        "decision_events": events[: config.review_behavior_default_limit],
        "evaluation": {
            "expectancy": asdict(evaluate_expectancy(events, outcomes)),
            "regimes": {"rows": [asdict(row) for row in evaluate_regimes(events, outcomes).rows]},
        },
    }


@router.get("/api/v3/review/shadow-comparison")
def get_shadow_comparison(comparison_group_id: str | None = None):
    report = compare_shadow_events(comparison_group_id=comparison_group_id)
    return {
        "pair_count": report.pair_count,
        "agreement_rate": report.agreement_rate,
        "divergence_rate": report.divergence_rate,
        "directional_flip_rate": report.directional_flip_rate,
        "pairs": [asdict(pair) for pair in report.pairs],
    }


@router.get("/api/v3/review/learning")
def get_review_learning():
    if not phase8_config.learning_review_route_enabled:
        raise HTTPException(status_code=404, detail="learning review route disabled")

    with session_scope() as session:
        training_rows = session.execute(
            text("SELECT * FROM model_registry ORDER BY training_timestamp_utc DESC LIMIT :limit"),
            {"limit": config.max_page_limit},
        ).mappings().all()
        registry_events = session.execute(
            text("SELECT * FROM model_registry_events ORDER BY created_at_utc DESC LIMIT :limit"),
            {"limit": config.max_page_limit},
        ).mappings().all()

    runs = []
    datasets = []
    candidate_comparisons = []
    for row in training_rows:
        payload = _loads(row.get("payload_json"))
        run = {
            "model_artifact_version": row.get("model_artifact_version"),
            "engine_name": row.get("engine_name"),
            "engine_version": row.get("engine_version"),
            "dataset_version": row.get("dataset_version"),
            "training_timestamp_utc": row.get("training_timestamp_utc"),
            "validation_passed": bool(row.get("validation_passed")),
            "role": row.get("role"),
            "walk_forward": payload.get("walk_forward", {}),
            "holdout_summary": payload.get("holdout_summary", {}),
            "calibration_drift": payload.get("calibration_drift", {}),
        }
        runs.append(run)
        datasets.append({
            "dataset_version": row.get("dataset_version"),
            "dataset_name": row.get("dataset_name"),
            "feature_schema_version": row.get("feature_schema_version"),
            "snapshot_builder_version": row.get("snapshot_builder_version"),
        })
        candidate_comparisons.append({
            "model_artifact_version": row.get("model_artifact_version"),
            "role": row.get("role"),
            "validation_passed": bool(row.get("validation_passed")),
            "holdout_summary": payload.get("holdout_summary", {}),
            "calibration_drift": payload.get("calibration_drift", {}),
        })

    return {
        "training_runs": runs,
        "dataset_versions": datasets,
        "walk_forward_fold_results": [run.get("walk_forward", {}) for run in runs if run.get("walk_forward")],
        "holdout_summaries": [run.get("holdout_summary", {}) for run in runs if run.get("holdout_summary")],
        "calibration_drift": [run.get("calibration_drift", {}) for run in runs if run.get("calibration_drift")],
        "candidate_comparisons": candidate_comparisons,
        "registry_events": [{
            "event_type": row.get("event_type"),
            "model_artifact_version": row.get("model_artifact_version"),
            "related_model_artifact_version": row.get("related_model_artifact_version"),
            "created_at_utc": row.get("created_at_utc"),
            "reason": row.get("reason"),
            "payload": _loads(row.get("payload_json")),
        } for row in registry_events],
        "prepare_promotion_evidence_route": "/operate/control",
    }


@router.get("/api/v3/review/engine-performance")
def get_engine_performance(date_from: str | None = None, date_to: str | None = None):
    if not date_from:
        date_from = _iso_days_ago(config.review_performance_default_range_days)
    events_response = list_decision_events(date_from=date_from, date_to=date_to, limit=config.max_page_limit)
    outcomes_response = list_trade_outcomes(date_from=date_from, limit=config.max_page_limit)
    events = events_response["items"]
    outcomes = outcomes_response["items"]
    expectancy = asdict(evaluate_expectancy(events, outcomes))
    regimes = [asdict(row) for row in evaluate_regimes(events, outcomes).rows]
    resolved = [item for item in outcomes if str(item.get("resolution_status", {}).get("outcome_status")) == "RESOLVED"]
    good_decision_count = sum(1 for item in outcomes if bool(item.get("quality_interpretation", {}).get("is_good_decision")))
    return {
        "window": {"date_from": date_from, "date_to": date_to},
        "counts": {
            "decision_events": len(events),
            "trade_outcomes": len(outcomes),
            "resolved_outcomes": len(resolved),
            "good_decisions": good_decision_count,
        },
        "expectancy": expectancy,
        "regimes": {"rows": regimes},
        "recent_decision_events": events[: config.lifecycle_recent_limit],
        "recent_trade_outcomes": outcomes[: config.lifecycle_recent_limit],
    }


@router.get("/api/v3/review/lifecycle")
def get_review_lifecycle():
    dataset_manifests = _collect_dataset_manifests(config.dataset_artifacts_limit)
    model_artifacts = _collect_model_artifacts(config.training_runs_limit)
    backfill_coverage = _collect_backfill_coverage(config.backfill_windows_limit)
    learning = get_review_learning()
    runtime_metrics = runtime_metrics_service.get_metrics()
    return {
        "data_coverage": {
            "candles_root": _full_config.market_data.candles_root,
            "required_intervals": _full_config.market_data.required_intervals,
            "optional_intervals": _full_config.market_data.optional_intervals,
            "items": backfill_coverage,
        },
        "datasets": {
            "datasets_root": _full_config.paths.datasets_root,
            "items": dataset_manifests,
        },
        "training": {
            "models_root": _full_config.paths.models_root,
            "tracking_root": _full_config.paths.mlflow_tracking_uri,
            "items": model_artifacts,
            "registry_training_runs": learning.get("training_runs", [])[: config.training_runs_limit],
        },
        "validation": {
            "candidate_comparisons": learning.get("candidate_comparisons", [])[: config.training_runs_limit],
            "holdout_summaries": learning.get("holdout_summaries", [])[: config.training_runs_limit],
            "walk_forward_fold_results": learning.get("walk_forward_fold_results", [])[: config.training_runs_limit],
            "calibration_drift": learning.get("calibration_drift", [])[: config.training_runs_limit],
        },
        "runtime": runtime_metrics,
    }


@router.get("/api/v3/runtime/metrics")
def get_runtime_metrics():
    return runtime_metrics_service.get_metrics()
