"""JSONL append-only experiment memory ledger for AlphaForge.

Tracks every factor/combo evaluation so the sprint runner never re-tries
the same factor constellation.  Pure stdlib — no AlphaForge or v7 internals.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------
# File:   alphaforge/src/alphaforge/sprint/ledger.py
# 1 parent:           sprint/
# 2 parent:           alphaforge/  (inside src/)
# 3 parent:           src/
# 4 parent:           alphaforge/  (repo-level)
# 5 parent:           <repo-root>
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent

# ---------------------------------------------------------------------------
# Module-level constant  (can be overridden at import time)
# ---------------------------------------------------------------------------
DEFAULT_LEDGER_PATH: Path = _REPO_ROOT / "reports" / "research" / "experiment_ledger.jsonl"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def record_key(factor_names: list[str], mode: str, horizon: str) -> str:
    """Return a stable SHA-256 hex digest for a (factor_names, mode, horizon) triplet.

    The factor list is sorted before hashing so that the same set of factors
    always produces the same key regardless of input order.

    Args:
        factor_names: Names of the factors being evaluated.
        mode:         Trading mode, e.g. ``"SWING"``, ``"INTRADAY"``.
        horizon:      Forecast horizon, e.g. ``"1h"``, ``"4h"``, ``"1d"``.

    Returns:
        Hex-encoded SHA-256 hash (64 characters).
    """
    canonical = json.dumps(
        sorted(factor_names),
        sort_keys=True,
        ensure_ascii=True,
    )
    payload = f"{canonical}||{mode}||{horizon}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def append_record(
    record: dict[str, Any],
    ledger_path: Optional[Path] = None,
) -> None:
    """Append one JSON record to the experiment ledger.

    Creates the parent directory and the ledger file if they do not exist.
    Every call writes a single JSON line (JSONL format).

    Args:
        record:      Dictionary to serialise.  Callers are strongly encouraged
                     to include a ``"key"`` field produced by :func:`record_key`
                     so that :func:`load_seen_keys` can identify duplicates.
        ledger_path: Path to the JSONL file.  Defaults to
                     :data:`DEFAULT_LEDGER_PATH`.
    """
    path = ledger_path or DEFAULT_LEDGER_PATH

    # Ensure parent directory exists atomically (race-safe on most OSes).
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=True, sort_keys=True))
        fh.write("\n")


def load_seen_keys(
    max_age_days: Optional[int] = None,
    ledger_path: Optional[Path] = None,
) -> set[str]:
    """Return the set of ``"key"`` values seen in the ledger.

    Entries that do not carry a ``"key"`` field are silently skipped.

    Args:
        max_age_days: If given, only include records whose ``"timestamp"``
                      (ISO-8601 string) is newer than this many days.
                      Records without a parseable ``"timestamp"`` are
                      **always included** to avoid accidentally re-running
                      old, non-timestamped entries.
        ledger_path:  Path to the JSONL file.  Defaults to
                      :data:`DEFAULT_LEDGER_PATH`.

    Returns:
        Set of unique key strings.
    """
    path = ledger_path or DEFAULT_LEDGER_PATH

    if not path.is_file():
        return set()

    now = datetime.now(timezone.utc)
    seen: set[str] = set()

    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                record: dict[str, Any] = json.loads(line)
            except json.JSONDecodeError:
                continue  # skip corrupt lines

            key = record.get("key")
            if key is None:
                continue

            # Age filter ----------------------------------------------------
            if max_age_days is not None:
                ts_str = record.get("timestamp")
                if ts_str is not None:
                    try:
                        ts = datetime.fromisoformat(ts_str)
                        # If the timestamp is naive, assume UTC.
                        if ts.tzinfo is None:
                            ts = ts.replace(tzinfo=timezone.utc)
                        age = (now - ts).total_seconds()
                        if age > max_age_days * 86400:
                            continue  # too old, skip
                    except (ValueError, TypeError):
                        pass  # unparseable timestamp -> include

            seen.add(key)

    return seen
