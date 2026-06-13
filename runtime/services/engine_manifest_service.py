"""Run manifests and change detection for engine composition."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from runtime.db.models import EngineRunManifest, ImprovementChangeEvent
from runtime.db.repos._helpers import dumps_json, dumps_list, loads_json
from runtime.db.repos.runtime_profile_repo import PAPER_PROFILE_ID
from runtime.db.session import session_scope
from runtime.services.improvement_registry_service import ImprovementRegistryService


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class EngineManifestService:
    def __init__(self, registry_service: ImprovementRegistryService | None = None) -> None:
        self.registry_service = registry_service or ImprovementRegistryService()

    def create_run_manifest(
        self,
        run_id: str,
        engine_version: str,
        enabled_components: list[str],
        param_snapshot: dict[str, Any],
        feature_flags: dict[str, Any],
        *,
        runtime_mode: str = "SCAN",
        symbol_scope: list[str] | None = None,
        interval_scope: list[str] | None = None,
        profile_id: str = PAPER_PROFILE_ID,
        resolved_config_hash: str = "",
    ) -> dict[str, Any]:
        registry = {item["component_id"]: item for item in self.registry_service.sync_registry()}
        component_snapshot = [registry[component_id] for component_id in enabled_components if component_id in registry]
        payload = {
            "run_id": run_id,
            "profile_id": profile_id,
            "engine_version": engine_version,
            "started_at_utc": _utc_now_iso(),
            "finished_at_utc": None,
            "component_snapshot_json": dumps_list(component_snapshot),
            "enabled_component_ids_json": dumps_list(sorted(enabled_components)),
            "disabled_component_ids_json": dumps_list(self.registry_service.disabled_component_ids()),
            "param_hash": self._param_hash(param_snapshot, feature_flags),
            "param_snapshot_json": dumps_json(param_snapshot),
            "feature_flags_json": dumps_json(feature_flags),
            "runtime_mode": runtime_mode,
            "symbol_scope_json": dumps_list(symbol_scope or []),
            "interval_scope_json": dumps_list(interval_scope or []),
            "summary_json": dumps_json({}),
            "resolved_config_hash": str(resolved_config_hash or ""),
        }
        with session_scope() as session:
            prior = self._previous_manifest(session, exclude_run_id=run_id, profile_id=profile_id)
            row = session.query(EngineRunManifest).filter(EngineRunManifest.run_id == run_id).one_or_none()
            if row is None:
                row = EngineRunManifest(**payload)
                session.add(row)
            else:
                for key, value in payload.items():
                    setattr(row, key, value)
            session.commit()
            manifest = self._to_dict(row)
            if prior:
                self._record_changes(session, manifest, prior)
            return manifest

    def finalize_run_manifest(
        self,
        run_id: str,
        summary: dict[str, Any],
        profile_id: str = PAPER_PROFILE_ID,
    ) -> dict[str, Any] | None:
        with session_scope() as session:
            row = (
                session.query(EngineRunManifest)
                .filter(EngineRunManifest.run_id == run_id)
                .filter(EngineRunManifest.profile_id == profile_id)
                .one_or_none()
            )
            if row is None:
                return None
            row.finished_at_utc = _utc_now_iso()
            row.summary_json = dumps_json(summary)
            session.commit()
            return self._to_dict(row)

    def compare_manifests(
        self,
        current_run_id: str,
        prior_run_id: str | None = None,
        profile_id: str = PAPER_PROFILE_ID,
    ) -> dict[str, Any]:
        with session_scope() as session:
            current = (
                session.query(EngineRunManifest)
                .filter(EngineRunManifest.run_id == current_run_id)
                .filter(EngineRunManifest.profile_id == profile_id)
                .one_or_none()
            )
            prior = (
                session.query(EngineRunManifest)
                .filter(EngineRunManifest.run_id == prior_run_id)
                .filter(EngineRunManifest.profile_id == profile_id)
                .one_or_none()
            ) if prior_run_id else self._previous_manifest(session, exclude_run_id=current_run_id, profile_id=profile_id)
            if current is None:
                return {"current": None, "prior": None, "changes": []}
            current_payload = self._to_dict(current)
            prior_payload = self._to_dict(prior) if prior else None
            return {"current": current_payload, "prior": prior_payload, "changes": self._compute_changes(current_payload, prior_payload)}

    def list_changes(self, *, lookback_days: int = 30) -> list[dict[str, Any]]:
        with session_scope() as session:
            query = session.query(ImprovementChangeEvent)
            if lookback_days > 0:
                from datetime import timedelta

                threshold = (datetime.now(timezone.utc) - timedelta(days=int(lookback_days))).isoformat()
                query = query.filter(ImprovementChangeEvent.effective_at_utc >= threshold)
            rows = query.order_by(ImprovementChangeEvent.effective_at_utc.desc()).all()
            return [self._change_to_dict(row) for row in rows]

    def get_manifest(self, run_id: str, profile_id: str = PAPER_PROFILE_ID) -> dict[str, Any] | None:
        with session_scope() as session:
            row = (
                session.query(EngineRunManifest)
                .filter(EngineRunManifest.run_id == run_id)
                .filter(EngineRunManifest.profile_id == profile_id)
                .one_or_none()
            )
            return self._to_dict(row) if row else None

    def _record_changes(self, session: Session, current: dict[str, Any], prior: dict[str, Any]) -> None:
        for change in self._compute_changes(current, prior):
            existing = session.query(ImprovementChangeEvent).filter(ImprovementChangeEvent.change_id == change["change_id"]).one_or_none()
            if existing:
                continue
            session.add(ImprovementChangeEvent(**{
                "change_id": change["change_id"],
                "change_type": change["change_type"],
                "component_id": change["component_id"],
                "old_value_json": dumps_json(change.get("old_value")) if change.get("old_value") is not None else None,
                "new_value_json": dumps_json(change.get("new_value")) if change.get("new_value") is not None else None,
                "effective_from_run_id": current["run_id"],
                "effective_at_utc": current["started_at_utc"],
                "change_reason": change.get("change_reason", ""),
                "author": "system",
            }))
        session.commit()

    def _compute_changes(self, current: dict[str, Any], prior: dict[str, Any] | None) -> list[dict[str, Any]]:
        if prior is None:
            return []
        current_enabled = set(current.get("enabled_component_ids") or [])
        prior_enabled = set(prior.get("enabled_component_ids") or [])
        current_components = {item["component_id"]: item for item in current.get("component_snapshot") or []}
        prior_components = {item["component_id"]: item for item in prior.get("component_snapshot") or []}
        changes: list[dict[str, Any]] = []
        for component_id in sorted(current_enabled - prior_enabled):
            changes.append(self._change("component_enabled", component_id, None, current_components.get(component_id), current))
        for component_id in sorted(prior_enabled - current_enabled):
            changes.append(self._change("component_disabled", component_id, prior_components.get(component_id), None, current))
        for component_id in sorted(current_components):
            if component_id not in prior_components:
                changes.append(self._change("component_added", component_id, None, current_components.get(component_id), current))
                continue
            if str(current_components[component_id].get("version")) != str(prior_components[component_id].get("version")):
                changes.append(self._change("version_replaced", component_id, {"version": prior_components[component_id].get("version")}, {"version": current_components[component_id].get("version")}, current))
        if current.get("param_hash") != prior.get("param_hash"):
            changes.append(self._change("parameter_changed", "__engine__", {"param_hash": prior.get("param_hash")}, {"param_hash": current.get("param_hash")}, current))
        return changes

    @staticmethod
    def _change(change_type: str, component_id: str, old_value: Any, new_value: Any, current: dict[str, Any]) -> dict[str, Any]:
        return {
            "change_id": f"chg-{uuid4().hex[:16]}",
            "change_type": change_type,
            "component_id": component_id,
            "old_value": old_value,
            "new_value": new_value,
            "effective_from_run_id": current["run_id"],
            "effective_at_utc": current["started_at_utc"],
            "change_reason": change_type.replace("_", " "),
        }

    @staticmethod
    def _param_hash(param_snapshot: dict[str, Any], feature_flags: dict[str, Any]) -> str:
        payload = json.dumps({"params": param_snapshot, "flags": feature_flags}, sort_keys=True, separators=(",", ":"))
        return hashlib.sha1(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def _previous_manifest(session: Session, *, exclude_run_id: str, profile_id: str = PAPER_PROFILE_ID) -> dict[str, Any] | None:
        row = (
            session.query(EngineRunManifest)
            .filter(EngineRunManifest.profile_id == profile_id)
            .filter(EngineRunManifest.run_id != exclude_run_id)
            .order_by(EngineRunManifest.started_at_utc.desc())
            .first()
        )
        return EngineManifestService._to_dict(row) if row else None

    @staticmethod
    def _to_dict(row: EngineRunManifest | None) -> dict[str, Any] | None:
        if row is None:
            return None
        return {
            "id": row.id,
            "run_id": row.run_id,
            "profile_id": getattr(row, "profile_id", PAPER_PROFILE_ID),
            "engine_version": row.engine_version,
            "started_at_utc": row.started_at_utc,
            "finished_at_utc": row.finished_at_utc,
            "component_snapshot": loads_json(row.component_snapshot_json, []),
            "enabled_component_ids": loads_json(row.enabled_component_ids_json, []),
            "disabled_component_ids": loads_json(row.disabled_component_ids_json, []),
            "param_hash": row.param_hash,
            "param_snapshot": loads_json(row.param_snapshot_json, {}),
            "feature_flags": loads_json(row.feature_flags_json, {}),
            "runtime_mode": row.runtime_mode,
            "symbol_scope": loads_json(row.symbol_scope_json, []),
            "interval_scope": loads_json(row.interval_scope_json, []),
            "summary": loads_json(row.summary_json, {}),
            "resolved_config_hash": getattr(row, "resolved_config_hash", ""),
        }

    @staticmethod
    def _change_to_dict(row: ImprovementChangeEvent) -> dict[str, Any]:
        return {
            "id": row.id,
            "change_id": row.change_id,
            "change_type": row.change_type,
            "component_id": row.component_id,
            "old_value": loads_json(row.old_value_json, None) if row.old_value_json else None,
            "new_value": loads_json(row.new_value_json, None) if row.new_value_json else None,
            "effective_from_run_id": row.effective_from_run_id,
            "effective_at_utc": row.effective_at_utc,
            "change_reason": row.change_reason,
            "author": row.author,
        }
