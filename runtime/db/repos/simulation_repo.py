"""Simulation run/result repository for v4."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from sqlalchemy import delete
from sqlalchemy.orm import Session

from runtime.db.models import SimulationResult, SimulationRun
from runtime.db.repos._helpers import dumps_json, loads_json


class SimulationRepository:
    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    def create_run(self, session: Session, name: str, parameters: dict, requested_by: str = "system", status: str = "PENDING") -> dict:
        row = SimulationRun(
            name=name,
            status=status,
            requested_by=requested_by,
            parameters_json=dumps_json(parameters or {}),
            metrics_json=dumps_json({}),
            created_at_utc=parameters.get("created_at_utc") or parameters.get("created_at") or "",
            started_at_utc=None,
            finished_at_utc=None,
        )
        if not row.created_at_utc:
            row.created_at_utc = self._utc_now_iso()
        session.add(row)
        session.commit()
        return self._run_to_dict(row)

    def update_run(
        self,
        session: Session,
        run_id: int,
        *,
        status: str | None = None,
        metrics: dict | None = None,
        started: bool = False,
        finished: bool = False,
    ) -> dict | None:
        row = session.get(SimulationRun, run_id)
        if row is None:
            return None
        current_metrics = loads_json(row.metrics_json, {})
        force_stopped = bool(current_metrics.get("force_stopped"))
        incoming_metrics = dict(metrics or {}) if metrics is not None else None
        if incoming_metrics is not None and incoming_metrics.get("force_stopped"):
            force_stopped = True
        if force_stopped and status not in {None, "STOPPED"}:
            # Force-stop is authoritative. Late background workers may still call
            # update_run(RUNNING/COMPLETED) after the operator has killed the run;
            # keep the persisted status stopped and preserve the force-stop flag.
            status = "STOPPED"
        if status is not None:
            row.status = status
        if incoming_metrics is not None:
            if force_stopped:
                incoming_metrics = {**incoming_metrics, "force_stopped": True, "stop_requested": True}
            row.metrics_json = dumps_json(incoming_metrics)
        if started:
            row.started_at_utc = self._utc_now_iso()
        if finished:
            row.finished_at_utc = self._utc_now_iso()
        session.commit()
        return self._run_to_dict(row)

    def delete_results_for_run(self, session: Session, run_id: int) -> int:
        result = session.execute(delete(SimulationResult).where(SimulationResult.run_id == run_id))
        session.commit()
        return int(result.rowcount or 0)

    def bulk_insert_results(self, session: Session, run_id: int, results: Iterable[dict]) -> int:
        rows = list(results)
        inserted = 0
        for item in rows:
            session.add(
                SimulationResult(
                    run_id=run_id,
                    symbol=str(item.get("symbol") or ""),
                    interval=str(item.get("interval") or ""),
                    mode=str(item.get("mode") or ""),
                    direction=item.get("direction"),
                    confidence=item.get("confidence"),
                    outcome=item.get("outcome"),
                    realized_r=item.get("realized_r"),
                    details_json=dumps_json(item.get("details") or item),
                    created_at_utc=item.get("created_at_utc") or self._utc_now_iso(),
                )
            )
            inserted += 1
        session.commit()
        return inserted

    def get_run(self, session: Session, run_id: int) -> dict | None:
        row = session.get(SimulationRun, run_id)
        return self._run_to_dict(row) if row else None

    def list_runs(self, session: Session, limit: int = 50) -> list[dict]:
        rows = session.query(SimulationRun).order_by(SimulationRun.id.desc()).limit(limit).all()
        return [self._run_to_dict(row) for row in rows]

    def results_for_run(self, session: Session, run_id: int, limit: int = 500) -> list[dict]:
        rows = session.query(SimulationResult).filter(SimulationResult.run_id == run_id).order_by(SimulationResult.id.asc()).limit(limit).all()
        return [self._result_to_dict(row) for row in rows]

    def summary(self, session: Session) -> dict:
        runs = self.list_runs(session, limit=20)
        by_status: dict[str, int] = {}
        for run in runs:
            status = str(run.get("status") or "UNKNOWN").upper()
            by_status[status] = by_status.get(status, 0) + 1
        return {"recent_runs": runs, "count": len(runs), "by_status": by_status}

    @staticmethod
    def _run_to_dict(row: SimulationRun) -> dict:
        metrics = loads_json(row.metrics_json, {})
        status = "STOPPED" if metrics.get("force_stopped") else row.status
        return {
            "id": row.id,
            "name": row.name,
            "status": status,
            "requested_by": row.requested_by,
            "parameters": loads_json(row.parameters_json, {}),
            "metrics": metrics,
            "created_at": row.created_at_utc,
            "started_at": row.started_at_utc,
            "finished_at": row.finished_at_utc,
        }

    @staticmethod
    def _result_to_dict(row: SimulationResult) -> dict:
        return {
            "id": row.id,
            "run_id": row.run_id,
            "symbol": row.symbol,
            "interval": row.interval,
            "mode": row.mode,
            "direction": row.direction,
            "confidence": row.confidence,
            "outcome": row.outcome,
            "realized_r": row.realized_r,
            "details": loads_json(row.details_json, {}),
            "created_at": row.created_at_utc,
        }
