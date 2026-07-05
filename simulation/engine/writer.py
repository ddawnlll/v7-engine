"""
SimulationWriter — persist SimulationOutput as Parquet with checksum.

Flattens nested SimulationOutput dataclasses into a tabular format suitable
for downstream analysis and training pipelines.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import asdict
from typing import Any, Dict, List

import pandas as pd

from simulation.contracts.models import SimulationOutput

logger = logging.getLogger(__name__)


class SimulationWriter:
    """Writes SimulationOutput lists to Parquet with SHA-256 sidecar.

    The writer flattens nested structures (ActionOutcome, PathMetrics,
    NoTradeOutcome, SimulationLineage) into flat column names using dot
    notation (e.g. ``long_outcome.realized_r_net``).
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def write(self, outputs: List[SimulationOutput], path: str) -> str:
        """Flatten and write SimulationOutputs to Parquet.

        Args:
            outputs: List of SimulationOutput to persist.
            path: Output ``.parquet`` file path.

        Returns:
            The *path* argument for caller convenience (e.g. chaining).
        """
        flat_records = [self._flatten(o) for o in outputs]
        df = pd.DataFrame(flat_records)
        df.to_parquet(path, index=False)
        logger.info("Wrote %d simulation outputs to %s", len(outputs), path)
        return path

    def write_checksum(self, path: str) -> str:
        """Write a SHA-256 sidecar file for the given Parquet file.

        Args:
            path: Path to the parquet file. Sidecar written to ``path + '.sha256'``.

        Returns:
            The computed SHA-256 hex digest.
        """
        sha256 = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                sha256.update(chunk)
        digest = sha256.hexdigest()

        sidecar_path = path + ".sha256"
        with open(sidecar_path, "w") as f:
            f.write(digest + "\n")

        logger.info("Wrote SHA-256 checksum to %s", sidecar_path)
        return digest

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _flatten(output: SimulationOutput) -> Dict[str, Any]:
        """Flatten a SimulationOutput dataclass to a single flat dict.

        Nested fields are prefixed with their parent name using dot notation.
        """
        raw = asdict(output)
        flat: Dict[str, Any] = {}

        # --- Top-level scalar fields ---
        for key in (
            "simulation_run_id",
            "symbol",
            "decision_timestamp",
            "mode",
            "primary_interval",
            "resolution_status",
            "best_action",
            "second_best_action",
            "action_gap_r",
            "regret_r",
            "is_ambiguous",
            "invalidity_reason",
            "monte_carlo_run_id",
            "monte_carlo_family_version",
        ):
            flat[key] = raw.get(key, "")

        # --- long_outcome / short_outcome ---
        for prefix in ("long", "short"):
            outcome = raw.get(f"{prefix}_outcome", {})
            SimulationWriter._flatten_outcome(flat, outcome, prefix)

        # --- no_trade_outcome ---
        nt = raw.get("no_trade_outcome", {})
        for key in (
            "saved_loss_r",
            "saved_loss_score",
            "missed_opportunity_r",
            "missed_opportunity_score",
            "no_trade_quality",
            "was_correct_skip",
        ):
            flat[f"no_trade_{key}"] = nt.get(key, "")

        # --- lineage ---
        lineage = raw.get("lineage", {})
        for key in (
            "simulation_family_version",
            "simulation_profile_version",
            "cost_model_version",
            "fee_model_version",
            "slippage_model_version",
            "horizon_family",
            "stop_family",
            "target_family",
            "time_exit_family",
            "adapter_kind",
        ):
            flat[f"lineage_{key}"] = lineage.get(key, "")

        return flat

    @staticmethod
    def _flatten_outcome(
        flat: Dict[str, Any],
        outcome: Dict[str, Any],
        prefix: str,
    ) -> None:
        """Flatten an ActionOutcome dict into the flat record with a prefix.

        Also flattens the nested ``path_metrics`` sub-struct.
        """
        for key in (
            "action",
            "realized_r_gross",
            "realized_r_net",
            "fee_cost_r",
            "slippage_cost_r",
            "funding_cost_r",
            "total_cost_r",
            "exit_reason",
            "exit_price",
            "exit_bar_index",
            "hold_duration_bars",
            "action_utility",
        ):
            flat[f"{prefix}_outcome_{key}"] = outcome.get(key, "")

        # PathMetrics
        pm = outcome.get("path_metrics", {})
        for key in (
            "mfe",
            "mae",
            "mfe_r",
            "mae_r",
            "time_to_mfe",
            "time_to_mae",
            "path_quality_score",
            "path_quality_bucket",
        ):
            flat[f"{prefix}_outcome_path_{key}"] = pm.get(key, "")
