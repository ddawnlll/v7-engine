"""Repository for backend-managed simulation presets."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from runtime.db.models import SimulationPreset
from runtime.db.repos._helpers import dumps_json, loads_json


class SimulationPresetRepository:
    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def list_presets(self, session: Session, *, limit: int = 100) -> list[dict[str, Any]]:
        rows = session.query(SimulationPreset).order_by(SimulationPreset.updated_at.desc(), SimulationPreset.id.desc()).limit(limit).all()
        return [self._to_dict(row) for row in rows]

    def get_preset(self, session: Session, preset_id: int) -> dict[str, Any] | None:
        row = session.get(SimulationPreset, preset_id)
        return self._to_dict(row) if row else None

    def create_preset(self, session: Session, payload: dict[str, Any]) -> dict[str, Any]:
        self._validate(payload, partial=False)
        now = self._now()
        row = SimulationPreset(
            name=str(payload.get("name") or "").strip(),
            description=payload.get("description"),
            profile_id=payload.get("profile_id"),
            symbols_json=dumps_json(payload.get("symbols") or []),
            intervals_json=dumps_json(payload.get("intervals") or []),
            modes_json=dumps_json(payload.get("modes") or []),
            period_start=payload.get("period_start"),
            period_end=payload.get("period_end"),
            capital=payload.get("capital"),
            execution_settings_json=dumps_json(payload.get("execution_settings") or {}),
            created_by=payload.get("created_by"),
            updated_by=payload.get("updated_by") or payload.get("created_by"),
            created_at=now,
            updated_at=now,
            is_shared=bool(payload.get("is_shared", False)),
            tags_json=dumps_json(payload.get("tags") or []),
        )
        session.add(row)
        session.commit()
        return self._to_dict(row)

    def update_preset(self, session: Session, preset_id: int, payload: dict[str, Any]) -> dict[str, Any] | None:
        row = session.get(SimulationPreset, preset_id)
        if row is None:
            return None
        self._validate(payload, partial=True)
        if "name" in payload:
            row.name = str(payload.get("name") or "").strip()
        if "description" in payload:
            row.description = payload.get("description")
        if "profile_id" in payload:
            row.profile_id = payload.get("profile_id")
        if "symbols" in payload:
            row.symbols_json = dumps_json(payload.get("symbols") or [])
        if "intervals" in payload:
            row.intervals_json = dumps_json(payload.get("intervals") or [])
        if "modes" in payload:
            row.modes_json = dumps_json(payload.get("modes") or [])
        if "period_start" in payload:
            row.period_start = payload.get("period_start")
        if "period_end" in payload:
            row.period_end = payload.get("period_end")
        if "capital" in payload:
            row.capital = payload.get("capital")
        if "execution_settings" in payload:
            row.execution_settings_json = dumps_json(payload.get("execution_settings") or {})
        if "is_shared" in payload:
            row.is_shared = bool(payload.get("is_shared"))
        if "tags" in payload:
            row.tags_json = dumps_json(payload.get("tags") or [])
        if "updated_by" in payload:
            row.updated_by = payload.get("updated_by")
        row.updated_at = self._now()
        session.commit()
        return self._to_dict(row)

    def delete_preset(self, session: Session, preset_id: int) -> bool:
        row = session.get(SimulationPreset, preset_id)
        if row is None:
            return False
        session.delete(row)
        session.commit()
        return True

    @staticmethod
    def _validate(payload: dict[str, Any], *, partial: bool) -> None:
        if (not partial or "name" in payload) and not str(payload.get("name") or "").strip():
            raise ValueError("Preset name is required")
        for key in ("symbols", "intervals", "modes"):
            if (not partial or key in payload) and not [str(item).strip() for item in (payload.get(key) or []) if str(item).strip()]:
                raise ValueError(f"Preset {key} must not be empty")

    @staticmethod
    def _to_dict(row: SimulationPreset) -> dict[str, Any]:
        return {
            "id": row.id,
            "name": row.name,
            "description": row.description,
            "profile_id": row.profile_id,
            "symbols": loads_json(row.symbols_json, []),
            "intervals": loads_json(row.intervals_json, []),
            "modes": loads_json(row.modes_json, []),
            "period_start": row.period_start,
            "period_end": row.period_end,
            "capital": row.capital,
            "execution_settings": loads_json(row.execution_settings_json, {}),
            "created_by": row.created_by,
            "updated_by": row.updated_by,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
            "is_shared": bool(row.is_shared),
            "tags": loads_json(row.tags_json, []),
        }
