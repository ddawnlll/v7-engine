"""run_context.py — Timestamped run folder management."""
from __future__ import annotations
import json, os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

class RunContext:
    def __init__(self, base_dir: str | os.PathLike[str] = "runs", goal: str = "") -> None:
        self._base = Path(base_dir).resolve()
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")[:22]
        self._run_dir = self._base / ts
        self._run_dir.mkdir(parents=True, exist_ok=True)
        self._iter_count = 0
        self._write_json(self._run_dir / "goal.json", {"goal": goal, "started_at": ts})

    @property
    def run_dir(self) -> Path: return self._run_dir
    @property
    def iteration(self) -> int: return self._iter_count

    def iter_dir(self) -> Path:
        d = self._run_dir / f"iter_{self._iter_count:03d}"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def next_iter(self) -> Path:
        self._iter_count += 1
        return self.iter_dir()

    def save_strategist_request(self, data: dict) -> Path: return self._write_json(self.iter_dir() / "strategist_request.json", data)
    def save_strategist_response(self, data: dict) -> Path: return self._write_json(self.iter_dir() / "strategist_response.json", data)
    def save_worker_task(self, task: str) -> Path:
        p = self.iter_dir() / "worker_task.txt"; p.write_text(task, encoding="utf-8"); return p
    def save_worker_log(self, log_text: str) -> Path:
        p = self.iter_dir() / "worker_output.json"; p.write_text(log_text, encoding="utf-8"); return p
    def save_gate_result(self, data: dict) -> Path: return self._write_json(self.iter_dir() / "gate_result.json", data)
    def save_git_snapshot(self, data: dict) -> Path: return self._write_json(self.iter_dir() / "git_snapshot.json", data)
    def save_summary(self, data: dict) -> Path: return self._write_json(self.iter_dir() / "summary.json", data)

    @staticmethod
    def _write_json(path: Path, data: Any) -> Path:
        path.write_text(json.dumps(data, indent=2, default=str, ensure_ascii=False), encoding="utf-8")
        return path
