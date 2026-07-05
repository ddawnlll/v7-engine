"""Optuna multi-objective tuner — NSGAII-based Pareto optimization.

Provides:
1. `create_moo_study` — factory for a multi-objective Optuna study.
2. `optimize_moo_study` — run n_trials with progress logging.
3. `extract_pareto_front` — collect Pareto-optimal trials as structured dicts.
4. `pareto_front_summary` — compact numeric summary of the Pareto frontier.

Uses optuna.samplers.NSGAIISampler (NSGA-II genetic algorithm) which is
available in Optuna >= 3.0 and is the recommended sampler for multi-objective
optimization. MOTPESampler was deprecated in Optuna v4; NSGAII is the
production-grade replacement.

Domain boundary: AlphaForge owns hyperparameter optimization evidence.
V7 owns final acceptance of Pareto-optimal models.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optuna lazy import — NSGAIISampler is the go-to multi-objective sampler
# ---------------------------------------------------------------------------

try:
    import optuna
    from optuna.samplers import NSGAIISampler

    _HAS_OPTUNA = True
except ImportError:
    NSGAIISampler = None  # type: ignore
    _HAS_OPTUNA = False

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_N_TRIALS: int = 100
DEFAULT_N_WARMUP_STARTUPS: int = 10
DEFAULT_POPULATION_SIZE: int = 50

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class ParetoPoint:
    """A single Pareto-optimal trial result.

    Attributes:
        trial_number: Optuna trial number.
        sharpe: Annualized Sharpe ratio.
        profit_factor: Profit factor (gross profit / gross loss).
        params: The hyperparameter dict that produced this result.
    """

    trial_number: int
    sharpe: float
    profit_factor: float
    params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ParetoFrontier:
    """The Pareto frontier from a multi-objective study.

    Attributes:
        points: List of Pareto-optimal points, sorted by descending Sharpe.
        n_trials_total: Total number of trials run.
        n_pareto: Number of points on the Pareto frontier.
    """

    points: List[ParetoPoint] = field(default_factory=list)
    n_trials_total: int = 0
    n_pareto: int = 0

    def best_sharpe(self) -> Optional[ParetoPoint]:
        """Return the Pareto point with the highest Sharpe ratio."""
        if not self.points:
            return None
        return max(self.points, key=lambda p: p.sharpe)

    def best_profit_factor(self) -> Optional[ParetoPoint]:
        """Return the Pareto point with the highest Profit Factor."""
        if not self.points:
            return None
        return max(self.points, key=lambda p: p.profit_factor)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a JSON-compatible dictionary."""
        return {
            "n_trials_total": self.n_trials_total,
            "n_pareto": self.n_pareto,
            "points": [
                {
                    "trial_number": p.trial_number,
                    "sharpe": round(p.sharpe, 6),
                    "profit_factor": round(p.profit_factor, 6),
                    "params": p.params,
                }
                for p in self.points
            ],
        }


# ---------------------------------------------------------------------------
# Study creation
# ---------------------------------------------------------------------------


def create_moo_study(
    study_name: Optional[str] = None,
    storage: Optional[str] = None,
    load_if_exists: bool = False,
    population_size: int = DEFAULT_POPULATION_SIZE,
    n_startup_trials: int = DEFAULT_N_WARMUP_STARTUPS,
    seed: Optional[int] = None,
) -> Any:
    """Create a multi-objective Optuna study maximizing Sharpe and Profit Factor.

    Uses NSGAIISampler with directions=['maximize', 'maximize'].

    Args:
        study_name: Optional name for the study. Auto-generated if None.
        storage: Optional database URL for persistent storage (e.g., 'sqlite:///...').
                 If None, uses in-memory storage.
        load_if_exists: If True and a study with the same name exists in storage,
                        load it instead of raising DuplicatedStudyError.
        population_size: NSGAII population size (default 50).
        n_startup_trials: Number of random-start trials before NSGAII kicks in.
        seed: Random seed for reproducibility.

    Returns:
        optuna.Study object configured for multi-objective optimization.

    Raises:
        RuntimeError: If optuna is not installed.
    """
    if not _HAS_OPTUNA:
        raise RuntimeError(
            "optuna is not installed. Install it with: pip install optuna"
        )

    sampler = NSGAIISampler(
        population_size=population_size,
        seed=seed,
    )

    study = optuna.create_study(
        study_name=study_name,
        storage=storage,
        load_if_exists=load_if_exists,
        directions=["maximize", "maximize"],
        sampler=sampler,
    )

    logger.info(
        "Created MOO study '%s' with NSGAIISampler (pop=%d, directions=max,max)",
        study.study_name,
        population_size,
    )
    return study


# ---------------------------------------------------------------------------
# Optimization
# ---------------------------------------------------------------------------


def optimize_moo_study(
    study: Any,
    objective_fn: Callable[[Any], Tuple[float, float]],
    n_trials: int = DEFAULT_N_TRIALS,
    callbacks: Optional[List[Callable]] = None,
    gc_after_trial: bool = False,
) -> Any:
    """Run multi-objective optimization on a study.

    Args:
        study: An optuna.Study created by `create_moo_study`.
        objective_fn: A callable(trial) -> Tuple[float, float] returning
                      (sharpe, profit_factor). Both values are maximized.
        n_trials: Number of optimization trials to run.
        callbacks: Optional list of Optuna callbacks.
        gc_after_trial: Run gc.collect() after each trial (useful for large models).

    Returns:
        The study with completed trials (same object, modified in-place).

    Raises:
        RuntimeError: If optuna is not installed.
    """
    if not _HAS_OPTUNA:
        raise RuntimeError("optuna is not installed")

    if study is None:
        raise ValueError("study is required — call create_moo_study() first")

    logger.info(
        "Starting MOO optimization: study='%s', n_trials=%d",
        study.study_name,
        n_trials,
    )

    study.optimize(
        objective_fn,
        n_trials=n_trials,
        callbacks=callbacks,
        gc_after_trial=gc_after_trial,
    )

    n_complete = len(study.trials)
    n_pareto = len(study.best_trials)
    logger.info(
        "MOO optimization complete: %d trials, %d Pareto-optimal",
        n_complete,
        n_pareto,
    )

    return study


# ---------------------------------------------------------------------------
# Pareto frontier extraction
# ---------------------------------------------------------------------------


def extract_pareto_front(study: Any) -> ParetoFrontier:
    """Extract the Pareto frontier from a completed multi-objective study.

    Iterates over `study.best_trials` and builds a structured `ParetoFrontier`
    with points sorted by descending Sharpe ratio.

    Args:
        study: An optuna.Study with directions=['maximize', 'maximize'].

    Returns:
        ParetoFrontier dataclass containing all Pareto-optimal points.

    Raises:
        RuntimeError: If optuna is not installed.
        ValueError: If the study has no completed trials.
    """
    if not _HAS_OPTUNA:
        raise RuntimeError("optuna is not installed")

    if study is None:
        raise ValueError("study is required")

    trials = study.trials
    if not trials:
        raise ValueError("Study has no completed trials")

    # best_trials gives the Pareto-optimal set
    best = study.best_trials
    points: List[ParetoPoint] = []

    for t in best:
        # values[0] = sharpe, values[1] = profit_factor
        sharpe_val = float(t.values[0]) if t.values is not None else -1e6
        pf_val = float(t.values[1]) if t.values is not None else -1.0
        points.append(
            ParetoPoint(
                trial_number=t.number,
                sharpe=sharpe_val,
                profit_factor=pf_val,
                params=dict(t.params),
            )
        )

    # Sort by descending Sharpe
    points.sort(key=lambda p: p.sharpe, reverse=True)

    return ParetoFrontier(
        points=points,
        n_trials_total=len(trials),
        n_pareto=len(points),
    )


def pareto_front_summary(study: Any) -> Dict[str, Any]:
    """Return a compact JSON-serializable summary of the Pareto frontier.

    Args:
        study: An optuna.Study with directions=['maximize', 'maximize'].

    Returns:
        Dict with keys:
            n_trials_total: Total completed trials.
            n_pareto: Number of points on the Pareto frontier.
            sharpe_range: [min, max] Sharpe on the frontier.
            profit_factor_range: [min, max] Profit Factor on the frontier.
            best_sharpe_point: Dict with trial_number, sharpe, profit_factor, params.
            best_profit_factor_point: Dict with trial_number, sharpe, profit_factor, params.
    """
    frontier = extract_pareto_front(study)

    result: Dict[str, Any] = {
        "n_trials_total": frontier.n_trials_total,
        "n_pareto": frontier.n_pareto,
    }

    if frontier.points:
        sharpe_vals = [p.sharpe for p in frontier.points]
        pf_vals = [p.profit_factor for p in frontier.points]
        result["sharpe_range"] = [round(min(sharpe_vals), 6), round(max(sharpe_vals), 6)]
        result["profit_factor_range"] = [
            round(min(pf_vals), 6),
            round(max(pf_vals), 6),
        ]

        best_s = frontier.best_sharpe()
        if best_s is not None:
            result["best_sharpe_point"] = {
                "trial_number": best_s.trial_number,
                "sharpe": round(best_s.sharpe, 6),
                "profit_factor": round(best_s.profit_factor, 6),
                "params": best_s.params,
            }

        best_pf = frontier.best_profit_factor()
        if best_pf is not None:
            result["best_profit_factor_point"] = {
                "trial_number": best_pf.trial_number,
                "sharpe": round(best_pf.sharpe, 6),
                "profit_factor": round(best_pf.profit_factor, 6),
                "params": best_pf.params,
            }
    else:
        result["sharpe_range"] = [0.0, 0.0]
        result["profit_factor_range"] = [0.0, 0.0]

    return result


# ---------------------------------------------------------------------------
# Pareto frontier visualization (optional — requires plotly)
# ---------------------------------------------------------------------------


def plot_pareto_frontier(
    study: Any,
    save_path: Optional[str] = None,
    target_names: Optional[List[str]] = None,
) -> Optional[bytes]:
    """Plot the Pareto frontier using optuna's built-in visualization.

    Requires `plotly` to be installed.

    Args:
        study: An optuna.Study with directions=['maximize', 'maximize'].
        save_path: If provided, save the plot as an HTML file at this path.
        target_names: Axis labels for the Pareto front plot.
                      Defaults to ['Sharpe', 'Profit Factor'].

    Returns:
        If save_path is None, returns the HTML bytes of the plot.
        If save_path is set, saves to file and returns None.

    Raises:
        ImportError: If plotly is not installed.
        RuntimeError: If optuna is not installed.
    """
    if not _HAS_OPTUNA:
        raise RuntimeError("optuna is not installed")

    try:
        from optuna.visualization import plot_pareto_front
    except ImportError:
        raise ImportError(
            "plotly is required for Pareto front visualization. "
            "Install it with: pip install plotly"
        )

    if target_names is None:
        target_names = ["Sharpe", "Profit Factor"]

    fig = plot_pareto_front(study, target_names=target_names)

    if save_path:
        fig.write_html(save_path)
        logger.info("Pareto front plot saved to %s", save_path)
        return None
    else:
        return fig.to_html().encode("utf-8")


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------


def save_pareto_frontier(
    frontier: ParetoFrontier,
    path: Path,
) -> None:
    """Save the Pareto frontier to a JSON file.

    Args:
        frontier: ParetoFrontier dataclass to serialize.
        path: Filesystem path for the JSON output.

    Raises:
        IOError: If the file cannot be written.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(frontier.to_dict(), f, indent=2)
    logger.info("Pareto frontier saved to %s (%d points)", path, frontier.n_pareto)


def load_pareto_frontier(path: Path) -> ParetoFrontier:
    """Load a Pareto frontier from a JSON file.

    Args:
        path: Path to a JSON file produced by `save_pareto_frontier`.

    Returns:
        ParetoFrontier dataclass.
    """
    path = Path(path)
    with open(path, "r") as f:
        data = json.load(f)

    points = [
        ParetoPoint(
            trial_number=p["trial_number"],
            sharpe=p["sharpe"],
            profit_factor=p["profit_factor"],
            params=p.get("params", {}),
        )
        for p in data.get("points", [])
    ]

    return ParetoFrontier(
        points=points,
        n_trials_total=data.get("n_trials_total", 0),
        n_pareto=data.get("n_pareto", 0),
    )
