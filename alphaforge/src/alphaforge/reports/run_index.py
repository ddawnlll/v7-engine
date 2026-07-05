"""Research Artifact Registry + Canonical Run Index (#127).

Maintains a single index file (``alphaforge_report/research_run_index.json``)
that is updated on every research run.  It enforces a clear canonical vs.
superseded distinction so that downstream consumers can always find the latest
authoritative report for each mode.

Index file location (repo-relative)::

    alphaforge_report/research_run_index.json

Entry fields
============

========================  =============================================
Field                     Description
========================  =============================================
``run_id``                Unique run identifier (e.g. run-swing-001)
``mode``                  Trading mode (SCALP / AGGRESSIVE_SCALP / SWING)
``timestamp``             ISO-8601 UTC when the run was indexed
``canonical_report_path`` Path to the primary report JSON
``candidate_count``       Number of alpha candidates evaluated (0 = N/A)
``trial_count``           Number of trials / hypotheses tested
``verdict``               Verdict string from the report
``artifact_paths``        List of paths to associated artifacts
``superseded_reports``    Reports that this entry replaces (paths)
``duplicate_reports``     Duplicate report paths (same run_id detected)
``status``                ``"canonical"``, ``"superseded"``, or ``"duplicate"``
========================  =============================================

Usage::

    from alphaforge.reports.run_index import ResearchRunIndex

    index = ResearchRunIndex()
    index.add_run(
        run_id="run-swing-001",
        mode="SWING",
        canonical_report_path="data/reports/swing/mode_research_report_...json",
        candidate_count=5,
        trial_count=124,
        verdict="BASELINE_VALID",
        artifact_paths=["artifacts/models/swing/xgb_model.json"],
    )
    index.write()   # persists to alphaforge_report/research_run_index.json
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List

from alphaforge.paths import repo_root

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

INDEX_VERSION: str = "1.0.0"

_INDEX_RELATIVE_PATH: str = "alphaforge_report/research_run_index.json"

STATUS_CANONICAL: str = "canonical"
STATUS_SUPERSEDED: str = "superseded"
STATUS_DUPLICATE: str = "duplicate"

VALID_STATUSES: frozenset = frozenset(
    [STATUS_CANONICAL, STATUS_SUPERSEDED, STATUS_DUPLICATE]
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    """Return current UTC time as ISO-8601 string."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _make_entry(
    run_id: str,
    mode: str,
    canonical_report_path: str,
    candidate_count: int,
    trial_count: int,
    verdict: str,
    artifact_paths: List[str],
    superseded_reports: List[str],
    duplicate_reports: List[str],
    status: str,
) -> dict:
    """Build a single run-index entry dict."""
    return {
        "run_id": run_id,
        "mode": mode,
        "timestamp": _now_iso(),
        "canonical_report_path": canonical_report_path,
        "candidate_count": candidate_count,
        "trial_count": trial_count,
        "verdict": verdict,
        "artifact_paths": list(artifact_paths),
        "superseded_reports": list(superseded_reports),
        "duplicate_reports": list(duplicate_reports),
        "status": status,
    }


def _default_index() -> dict:
    """Return a fresh empty index structure."""
    return {
        "index_version": INDEX_VERSION,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "runs": [],
        "canonical": {},  # mode -> run_id
    }


# ---------------------------------------------------------------------------
# Public class
# ---------------------------------------------------------------------------


class ResearchRunIndex:
    """Research artifact registry and canonical run index.

    Maintains the authoritative ``research_run_index.json`` that tracks
    every research run, distinguishes canonical from superseded entries,
    and detects duplicates.

    All public methods are thread-<b>unsafe</b>; callers should serialise
    writes from a single process.
    """

    def __init__(self, index_path: str | Path | None = None) -> None:
        """Initialise the index.

        Args:
            index_path:
                Path to the index JSON file.  Defaults to
                ``<repo-root>/alphaforge_report/research_run_index.json``.
        """
        if index_path is not None:
            self._index_path = Path(index_path)
        else:
            self._index_path = repo_root() / _INDEX_RELATIVE_PATH

        self._data: dict = self._load_or_default()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def index_path(self) -> Path:
        """Return the resolved path of the index file."""
        return self._index_path

    @property
    def runs(self) -> List[dict]:
        """Return the list of run entries (read-only view)."""
        return list(self._data.get("runs", []))

    @property
    def canonical(self) -> dict:
        """Return the mode-to-run_id mapping for canonical entries."""
        return dict(self._data.get("canonical", {}))

    def add_run(
        self,
        run_id: str,
        mode: str,
        canonical_report_path: str,
        candidate_count: int = 0,
        trial_count: int = 0,
        verdict: str = "NOT_EVALUATED",
        artifact_paths: List[str] | None = None,
    ) -> dict:
        """Add or update a run entry and resolve canonical/superseded status.

        If a run with the same ``run_id`` already exists, the new entry
        is marked as **duplicate** and the existing entry's status is
        unchanged.

        Otherwise, the previous canonical entry for the same **mode** (if
        any) is marked **superseded** and the new entry becomes
        **canonical**.

        Args:
            run_id: Unique run identifier.
            mode: Trading mode (``SCALP``, ``AGGRESSIVE_SCALP``, ``SWING``).
            canonical_report_path: Path to the primary report JSON.
            candidate_count: Number of alpha candidates evaluated.
            trial_count: Number of trials / hypotheses tested.
            verdict: Verdict string (e.g. ``REJECT``, ``BASELINE_VALID``).
            artifact_paths: Associated artifact files (model binaries, etc.)

        Returns:
            The newly created entry dict (already inserted into the
            internal index).
        """
        runs = self._data.setdefault("runs", [])
        canonical_map = self._data.setdefault("canonical", {})
        artifact_paths = artifact_paths or []

        # ------------------------------------------------------------------
        # Duplicate detection
        # ------------------------------------------------------------------
        existing_idx, existing_entry = self._find_by_run_id(run_id)
        if existing_entry is not None:
            logger.info(
                "Duplicate run_id '%s' detected — marking new entry as duplicate",
                run_id,
            )
            entry = _make_entry(
                run_id=run_id,
                mode=mode,
                canonical_report_path=canonical_report_path,
                candidate_count=candidate_count,
                trial_count=trial_count,
                verdict=verdict,
                artifact_paths=artifact_paths,
                superseded_reports=[],
                duplicate_reports=[existing_entry["canonical_report_path"]]
                if existing_entry.get("canonical_report_path")
                else [],
                status=STATUS_DUPLICATE,
            )
            runs.append(entry)
            self._data["updated_at"] = _now_iso()
            return entry

        # ------------------------------------------------------------------
        # Supersede previous canonical for this mode
        # ------------------------------------------------------------------
        superseded_paths: List[str] = []
        prev_canonical_run_id = canonical_map.get(mode)
        if prev_canonical_run_id is not None:
            prev_idx, prev_entry = self._find_by_run_id(prev_canonical_run_id)
            if prev_entry is not None and prev_entry.get("status") != STATUS_SUPERSEDED:
                # Mark old canonical as superseded
                prev_entry["status"] = STATUS_SUPERSEDED
                prev_path = prev_entry.get("canonical_report_path", "")
                if prev_path:
                    superseded_paths.append(prev_path)
                logger.info(
                    "Superseded previous canonical run '%s' for mode %s",
                    prev_canonical_run_id,
                    mode,
                )

        # ------------------------------------------------------------------
        # Create new canonical entry
        # ------------------------------------------------------------------
        entry = _make_entry(
            run_id=run_id,
            mode=mode,
            canonical_report_path=canonical_report_path,
            candidate_count=candidate_count,
            trial_count=trial_count,
            verdict=verdict,
            artifact_paths=artifact_paths,
            superseded_reports=superseded_paths,
            duplicate_reports=[],
            status=STATUS_CANONICAL,
        )
        runs.append(entry)

        # Update canonical map
        canonical_map[mode] = run_id
        self._data["updated_at"] = _now_iso()

        logger.info(
            "Indexed run '%s' (%s) — canonical, supersedes %d previous report(s)",
            run_id,
            mode,
            len(superseded_paths),
        )
        return entry

    def get_canonical_for_mode(self, mode: str) -> dict | None:
        """Return the canonical entry for a given mode, or ``None``."""
        canonical_map = self._data.get("canonical", {})
        run_id = canonical_map.get(mode)
        if run_id is None:
            return None
        _, entry = self._find_by_run_id(run_id)
        return entry

    def get_run(self, run_id: str) -> dict | None:
        """Return the entry for *run_id*, or ``None`` if not found."""
        _, entry = self._find_by_run_id(run_id)
        return entry

    def write(self, index_path: str | Path | None = None) -> Path:
        """Persist the index to disk as JSON.

        Args:
            index_path:
                Override output path.  Defaults to the path set at
                construction time.

        Returns:
            Path to the written file.
        """
        output = Path(index_path) if index_path else self._index_path
        output.parent.mkdir(parents=True, exist_ok=True)
        self._data["updated_at"] = _now_iso()

        with open(output, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)

        logger.info("Wrote run index to %s (%d runs)", output, len(self._data.get("runs", [])))
        return output

    def reload(self) -> None:
        """Re-read the index from disk, discarding in-memory changes."""
        self._data = self._load_or_default()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_or_default(self) -> dict:
        """Load the index from disk or return a fresh default."""
        path = self._index_path
        if path.is_file():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data: dict = json.load(f)
                # Ensure canonical map exists
                data.setdefault("canonical", {})
                data.setdefault("runs", [])
                return data
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning(
                    "Failed to load run index from %s: %s — starting fresh",
                    path,
                    exc,
                )
        return _default_index()

    def _find_by_run_id(self, run_id: str) -> tuple[int | None, dict | None]:
        """Linear search for a run entry by ``run_id``.

        Returns ``(index, entry)`` or ``(None, None)`` if not found.
        """
        runs = self._data.get("runs", [])
        for idx, entry in enumerate(runs):
            if entry.get("run_id") == run_id:
                return idx, entry
        return None, None
