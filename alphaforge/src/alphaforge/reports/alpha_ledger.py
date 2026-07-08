"""Alpha Ledger — persistent registry of every alpha candidate discovered across runs.

Every time a pipeline run discovers, tests, or evaluates an alpha candidate,
it calls ``AlphaLedger.add_alpha()`` or ``AlphaLedger.upsert_alpha()``. The
ledger persists to ``alphaforge_report/alpha_ledger.json`` and ensures no alpha
is ever lost.

Entry fields
============
=========================  ====================================================
Field                      Description
=========================  ====================================================
``alpha_id``               Unique identifier (e.g. ``bb_position_mean_reversion_v1``)
``run_id``                 Which run discovered/evaluated this alpha
``mode``                   SCALP / SWING / AGGRESSIVE_SCALP
``name``                   Human-readable name
``thesis``                 One-line alpha thesis
``source``                 Where it came from (factor_sprint / xgb / discovery / manual)
``status``                 ACTIVE / SUPERSEDED / REJECTED / CONTAMINATED / HOLD
``data_source``            real / synthetic / mixed
``symbols``                Symbol universe tested
``date_first_seen``        ISO-8601 UTC of first registration
``date_last_updated``      ISO-8601 UTC of last update
``net_R_per_trade``        Average net R per trade
``trade_count``            Total trades
``win_rate``               Win rate (0-1)
``profit_factor``          Profit factor
``max_drawdown_R``         Maximum drawdown in R
``sharpe``                 Sharpe ratio (if available)
``oos_ic``                 Out-of-sample IC (if available)
``oos_rank_ic``            Out-of-sample Rank IC (if available)
``cost_stress_survived``   Did edge survive cost stress? (bool / None)
``holdout_tested``         Was a holdout period tested? (bool)
``holdout_net_R``          Net R on holdout (if available)
``regime_breakdown``       Per-regime performance dict (if available)
``symbol_breakdown``       Per-symbol contribution dict (if available)
``v7_gates``               Dict mapping gate ID to status string
``artifact_paths``         Paths to associated artifacts
``notes``                  Free-form notes / rejections / warnings
``tags``                   List of tags (e.g. ["leakage", "single-feature", "watch"])
``lineage``                Dict with commit, data_refs, feature_set_id, etc.
=========================  ====================================================
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from alphaforge.paths import repo_root

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LEDGER_VERSION: str = "1.0.0"
_LEDGER_RELATIVE_PATH: str = "alphaforge_report/alpha_ledger.json"

# Status values
STATUS_ACTIVE: str = "ACTIVE"
STATUS_SUPERSEDED: str = "SUPERSEDED"
STATUS_REJECTED: str = "REJECTED"
STATUS_CONTAMINATED: str = "CONTAMINATED"
STATUS_HOLD: str = "HOLD"
STATUS_WATCH: str = "WATCH"

VALID_STATUSES: frozenset = frozenset([
    STATUS_ACTIVE, STATUS_SUPERSEDED, STATUS_REJECTED,
    STATUS_CONTAMINATED, STATUS_HOLD, STATUS_WATCH,
])

# Source values
SOURCE_FACTOR_SPRINT: str = "factor_sprint"
SOURCE_XGB: str = "xgb"
SOURCE_DISCOVERY: str = "discovery"
SOURCE_MANUAL: str = "manual"
SOURCE_OP_SCALP: str = "operation_scalp"

# Data source values
DATA_REAL: str = "real"
DATA_SYNTHETIC: str = "synthetic"
DATA_MIXED: str = "mixed"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _make_alpha_entry(
    alpha_id: str,
    run_id: str,
    mode: str,
    name: str,
    thesis: str,
    source: str,
    status: str,
    data_source: str,
    symbols: List[str],
    net_R_per_trade: Optional[float] = None,
    trade_count: Optional[int] = None,
    win_rate: Optional[float] = None,
    profit_factor: Optional[float] = None,
    max_drawdown_R: Optional[float] = None,
    sharpe: Optional[float] = None,
    oos_ic: Optional[float] = None,
    oos_rank_ic: Optional[float] = None,
    cost_stress_survived: Optional[bool] = None,
    holdout_tested: Optional[bool] = None,
    holdout_net_R: Optional[float] = None,
    regime_breakdown: Optional[Dict[str, Any]] = None,
    symbol_breakdown: Optional[Dict[str, Any]] = None,
    v7_gates: Optional[Dict[str, str]] = None,
    artifact_paths: Optional[List[str]] = None,
    notes: str = "",
    tags: Optional[List[str]] = None,
    lineage: Optional[Dict[str, Any]] = None,
) -> dict:
    now = _now_iso()
    return {
        "alpha_id": alpha_id,
        "run_id": run_id,
        "mode": mode,
        "name": name,
        "thesis": thesis,
        "source": source,
        "status": status,
        "data_source": data_source,
        "symbols": list(symbols),
        "date_first_seen": now,
        "date_last_updated": now,
        "net_R_per_trade": net_R_per_trade,
        "trade_count": trade_count,
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "max_drawdown_R": max_drawdown_R,
        "sharpe": sharpe,
        "oos_ic": oos_ic,
        "oos_rank_ic": oos_rank_ic,
        "cost_stress_survived": cost_stress_survived,
        "holdout_tested": holdout_tested,
        "holdout_net_R": holdout_net_R,
        "regime_breakdown": regime_breakdown or {},
        "symbol_breakdown": symbol_breakdown or {},
        "v7_gates": v7_gates or {},
        "artifact_paths": list(artifact_paths or []),
        "notes": notes,
        "tags": list(tags or []),
        "lineage": lineage or {},
    }


# ---------------------------------------------------------------------------
# Public class
# ---------------------------------------------------------------------------

class AlphaLedger:
    """Persistent alpha candidate registry.

    Every alpha discovered, tested, or evaluated in any pipeline run gets
    registered here. The ledger ensures no alpha is ever lost between runs.
    """

    def __init__(self, ledger_path: str | Path | None = None) -> None:
        if ledger_path is not None:
            self._ledger_path = Path(ledger_path)
        else:
            self._ledger_path = repo_root() / _LEDGER_RELATIVE_PATH
        self._data: dict = self._load_or_default()

    @property
    def ledger_path(self) -> Path:
        return self._ledger_path

    @property
    def alphas(self) -> List[dict]:
        return list(self._data.get("alphas", []))

    @property
    def summary(self) -> dict:
        """Quick summary stats of the ledger."""
        alphas = self._data.get("alphas", [])
        by_status: Dict[str, int] = {}
        by_mode: Dict[str, int] = {}
        for a in alphas:
            s = a.get("status", "UNKNOWN")
            by_status[s] = by_status.get(s, 0) + 1
            m = a.get("mode", "UNKNOWN")
            by_mode[m] = by_mode.get(m, 0) + 1
        return {
            "total_alphas": len(alphas),
            "by_status": by_status,
            "by_mode": by_mode,
            "best_net_R": self._best_net_R(),
        }

    def add_alpha(
        self,
        alpha_id: str,
        run_id: str,
        mode: str,
        name: str,
        thesis: str,
        source: str,
        status: str,
        data_source: str,
        symbols: List[str],
        **kwargs: Any,
    ) -> dict:
        """Register a new alpha candidate. Raises if alpha_id already exists."""
        existing = self._find_by_id(alpha_id)
        if existing is not None:
            raise ValueError(
                f"Alpha '{alpha_id}' already exists in ledger. "
                f"Use upsert_alpha() to update."
            )
        entry = _make_alpha_entry(
            alpha_id=alpha_id,
            run_id=run_id,
            mode=mode,
            name=name,
            thesis=thesis,
            source=source,
            status=status,
            data_source=data_source,
            symbols=symbols,
            **kwargs,
        )
        self._data.setdefault("alphas", []).append(entry)
        self._data["updated_at"] = _now_iso()
        logger.info("Added alpha '%s' (mode=%s, status=%s)", alpha_id, mode, status)
        return entry

    def upsert_alpha(
        self,
        alpha_id: str,
        **updates: Any,
    ) -> dict:
        """Update an existing alpha, or create if new.

        Always sets ``date_last_updated`` to now. Preserves ``date_first_seen``.
        """
        existing = self._find_by_id(alpha_id)
        if existing is not None:
            for key, val in updates.items():
                if key in ("alpha_id", "date_first_seen"):
                    continue  # never overwrite identity or first-seen
                existing[key] = val
            existing["date_last_updated"] = _now_iso()
            self._data["updated_at"] = _now_iso()
            logger.info("Updated alpha '%s'", alpha_id)
            return existing
        # Create new entry with partial data
        defaults = {
            "run_id": "", "mode": "", "name": alpha_id, "thesis": "",
            "source": "unknown", "status": STATUS_ACTIVE,
            "data_source": DATA_REAL, "symbols": [],
        }
        defaults.update(updates)
        entry = _make_alpha_entry(alpha_id=alpha_id, **defaults)
        self._data.setdefault("alphas", []).append(entry)
        self._data["updated_at"] = _now_iso()
        logger.info("Created alpha '%s' via upsert", alpha_id)
        return entry

    def get_alpha(self, alpha_id: str) -> dict | None:
        return self._find_by_id(alpha_id)

    def list_alphas(
        self,
        mode: str | None = None,
        status: str | None = None,
        source: str | None = None,
    ) -> List[dict]:
        """List alphas with optional filters."""
        result = self.alphas
        if mode is not None:
            result = [a for a in result if a.get("mode") == mode]
        if status is not None:
            result = [a for a in result if a.get("status") == status]
        if source is not None:
            result = [a for a in result if a.get("source") == source]
        return result

    def write(self, ledger_path: str | Path | None = None) -> Path:
        """Persist the ledger to disk."""
        output = Path(ledger_path) if ledger_path else self._ledger_path
        output.parent.mkdir(parents=True, exist_ok=True)
        self._data["updated_at"] = _now_iso()
        with open(output, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)
        logger.info("Wrote alpha ledger to %s (%d alphas)", output, len(self.alphas))
        return output

    def reload(self) -> None:
        self._data = self._load_or_default()

    def to_csv(self, csv_path: str | Path | None = None) -> str:
        """Export ledger as a human-readable CSV string or write to file."""
        import csv
        import io

        fields = [
            "alpha_id", "mode", "name", "status", "source", "data_source",
            "net_R_per_trade", "trade_count", "win_rate", "profit_factor",
            "max_drawdown_R", "sharpe", "oos_rank_ic", "cost_stress_survived",
            "holdout_tested", "holdout_net_R", "run_id", "date_first_seen",
            "tags", "notes",
        ]
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for a in self.alphas:
            row = {k: a.get(k) for k in fields}
            # Flatten lists/dicts for CSV
            if isinstance(row.get("tags"), list):
                row["tags"] = ";".join(row["tags"])
            writer.writerow(row)
        output = buf.getvalue()
        if csv_path is not None:
            Path(csv_path).write_text(output, encoding="utf-8")
        return output

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_or_default(self) -> dict:
        path = self._ledger_path
        if path.is_file():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                data.setdefault("alphas", [])
                data.setdefault("canonical", {})
                return data
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Failed to load alpha ledger from %s: %s", path, exc)
        return {
            "ledger_version": LEDGER_VERSION,
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
            "alphas": [],
            "canonical": {},
        }

    def _find_by_id(self, alpha_id: str) -> dict | None:
        """Return the alpha entry dict for *alpha_id*, or ``None``."""
        for entry in self._data.get("alphas", []):
            if entry.get("alpha_id") == alpha_id:
                return entry
        return None

    def _best_net_R(self) -> Optional[float]:
        vals = [
            a["net_R_per_trade"]
            for a in self._data.get("alphas", [])
            if a.get("net_R_per_trade") is not None
        ]
        return max(vals) if vals else None
