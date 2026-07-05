"""Model Evolution Research — XGBoost vs RandomForest vs MLP.

Compares alternative model architectures head-to-head on identical feature
data. Provides per-mode best-model recommendations and inference cost
benchmarks.

Design constraints:
  - sklearn-based alternatives (no torch dependency required)
  - Identical train/val split for fair comparison
  - Deterministic random seeds for reproducibility
  - Mode-aware: each mode gets its own best-model recommendation
  - Inference latency measured in wall-clock time (batched + single-sample)
  - Model size tracked for deployment cost estimation

Architectures compared:
  1. XGBoost (xgboost.XGBClassifier) — current baseline
  2. RandomForest (sklearn.ensemble.RandomForestClassifier) — tree ensemble
  3. MLP (sklearn.neural_network.MLPClassifier) — feedforward neural network

Usage:
    from alphaforge.research.evolution import compare_models

    X, y = load_your_data()
    result = compare_models(X, y, mode="SWING")
    print(result.best_model)       # "xgboost" | "random_forest" | "mlp"
    print(result.comparison_df)    # pandas DataFrame of all metrics
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import xgboost as xgb

from sklearn.base import BaseEstimator
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, log_loss
from sklearn.neural_network import MLPClassifier

from alphaforge.training.xgb_trainer import (
    SWING_DEFAULT_HYPERPARAMS,
    XGBoostTrainer,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

RANDOM_SEED: int = 42

# Default hyperparameters for alternative models (conservative, comparable
# to XGBoost SWING_DEFAULT_HYPERPARAMS).
RF_DEFAULT_PARAMS: Dict[str, Any] = {
    "n_estimators": 200,
    "max_depth": 8,
    "min_samples_split": 10,
    "min_samples_leaf": 5,
    "max_features": "sqrt",
    "random_state": RANDOM_SEED,
    "n_jobs": -1,
    "verbose": 0,
}

MLP_DEFAULT_PARAMS: Dict[str, Any] = {
    "hidden_layer_sizes": (64, 32),
    "activation": "relu",
    "solver": "adam",
    "alpha": 0.001,
    "batch_size": 64,
    "learning_rate_init": 0.001,
    "max_iter": 500,
    "random_state": RANDOM_SEED,
    "early_stopping": True,
    "validation_fraction": 0.15,
    "n_iter_no_change": 20,
    "verbose": False,
}

# Label mapping (same as xgb_trainer)
LABEL_TO_INT: Dict[str, int] = {
    "LONG_NOW": 0,
    "SHORT_NOW": 1,
    "NO_TRADE": 2,
}

NUM_CLASSES: int = 3

# Val fraction used for consistent splits across models
VAL_FRACTION: float = 0.2

# Warmup rounds for inference benchmarking
BENCHMARK_WARMUP: int = 10
BENCHMARK_ROUNDS: int = 100


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class AlternativeModelResult:
    """Result of training a single alternative model.

    Attributes:
        model_name: Short identifier (e.g. 'random_forest', 'mlp', 'xgboost').
        model: Trained sklearn estimator or xgboost XGBClassifier.
        train_accuracy: Accuracy on training set.
        val_accuracy: Accuracy on validation set.
        train_logloss: Cross-entropy loss on training set.
        val_logloss: Cross-entropy loss on validation set.
        training_duration_seconds: Wall-clock training time.
        model_size_bytes: Serialized model size in bytes (via pickle).
        inference_time_batched_us: Mean inference time per sample in
            microseconds for a batched forward pass (benchmark batch).
        inference_time_single_us: Mean inference time for a single sample.
        model_params: Dict of hyperparameters used.
    """

    model_name: str
    model: BaseEstimator
    train_accuracy: float
    val_accuracy: float
    train_logloss: float
    val_logloss: float
    training_duration_seconds: float
    model_size_bytes: int
    inference_time_batched_us: float
    inference_time_single_us: float
    model_params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BenchmarkResult:
    """Aggregated benchmark for one model across samples.

    Attributes:
        model_name: Short identifier.
        mean_batched_us: Mean microseconds per sample under batch inference.
        std_batched_us: Standard deviation of batch inference times.
        mean_single_us: Mean microseconds per single-sample inference.
        std_single_us: Standard deviation of single-sample inference.
    """

    model_name: str
    mean_batched_us: float
    std_batched_us: float
    mean_single_us: float
    std_single_us: float


@dataclass
class InferenceBenchmark:
    """Full inference benchmark results across all compared models.

    Each entry in `per_model` corresponds to one model's batched and
    single-sample latency.

    Attributes:
        per_model: List of BenchmarkResult, one per model.
        fastest_batched_us: Best (lowest) mean batched latency across models.
        fastest_single_us: Best (lowest) mean single-sample latency.
    """

    per_model: List[BenchmarkResult] = field(default_factory=list)
    fastest_batched_us: float = 0.0
    fastest_single_us: float = 0.0


@dataclass
class ModelComparisonResult:
    """Complete head-to-head comparison result.

    Attributes:
        mode: Trading mode used for comparison.
        n_samples: Number of training samples.
        n_features: Number of feature dimensions.
        per_model: List of AlternativeModelResult, one per architecture.
        best_model: Name of the best-performing model (by validation
            accuracy, tie-breaking by speed).
        comparison_df: Tabular comparison as list of dicts (JSON-serializable).
        inference_benchmark: InferenceBenchmark with latency details.
        recommendations: Dict mapping model name to list of modes for which
            this model is recommended.
    """

    mode: str
    n_samples: int
    n_features: int
    per_model: List[AlternativeModelResult] = field(default_factory=list)
    best_model: str = ""
    comparison_df: List[Dict[str, Any]] = field(default_factory=list)
    inference_benchmark: Optional[InferenceBenchmark] = None
    recommendations: Dict[str, List[str]] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Label encoding utilities
# ---------------------------------------------------------------------------


def _encode_labels(y: np.ndarray) -> np.ndarray:
    """Convert string labels to integer labels {0, 1, 2}."""
    if y.dtype.kind in ("i", "u"):
        return y.astype(np.int32)
    result = np.zeros(len(y), dtype=np.int32)
    for i, label in enumerate(y):
        if label not in LABEL_TO_INT:
            raise ValueError(f"Unknown label '{label}'")
        result[i] = LABEL_TO_INT[label]
    return result


# ---------------------------------------------------------------------------
# Alternative Trainers
# ---------------------------------------------------------------------------


class RandomForestTrainer:
    """RandomForest classifier trainer for model comparison.

    Wraps sklearn.ensemble.RandomForestClassifier with a consistent
    interface matching the XGBoostTrainer pattern.

    Usage:
        trainer = RandomForestTrainer(random_seed=42)
        result = trainer.train(X_train, y_train, X_val, y_val)
    """

    def __init__(
        self,
        random_seed: int = RANDOM_SEED,
        hyperparameters: Optional[Dict[str, Any]] = None,
    ):
        """Initialize RandomForest trainer.

        Args:
            random_seed: Random seed for reproducibility.
            hyperparameters: Model hyperparameters. If None, uses
                RF_DEFAULT_PARAMS.
        """
        self._random_seed = random_seed
        self._hyperparameters = hyperparameters or RF_DEFAULT_PARAMS.copy()

    @property
    def hyperparameters(self) -> Dict[str, Any]:
        return self._hyperparameters.copy()

    def train(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_val: np.ndarray,
        y_val: np.ndarray,
    ) -> AlternativeModelResult:
        """Train a RandomForest classifier and return metrics.

        Args:
            X_train: Training feature matrix.
            y_train: Training label vector (string or integer).
            X_val: Validation feature matrix.
            y_val: Validation label vector.

        Returns:
            AlternativeModelResult with trained model and metrics.
        """
        y_train_int = _encode_labels(y_train)
        y_val_int = _encode_labels(y_val)

        params = self._hyperparameters.copy()
        params["random_state"] = self._random_seed

        model = RandomForestClassifier(**params)

        start_time = time.monotonic()
        model.fit(X_train, y_train_int)
        training_duration = time.monotonic() - start_time

        # Predictions
        train_probs = model.predict_proba(X_train)
        val_probs = model.predict_proba(X_val)
        train_preds = np.argmax(train_probs, axis=1)
        val_preds = np.argmax(val_probs, axis=1)

        # Accuracy
        train_acc = float(accuracy_score(y_train_int, train_preds))
        val_acc = float(accuracy_score(y_val_int, val_preds))

        # Log-loss (multi-class)
        try:
            train_ll = float(log_loss(y_train_int, train_probs))
        except Exception:
            train_ll = 0.0
        try:
            val_ll = float(log_loss(y_val_int, val_probs))
        except Exception:
            val_ll = 0.0

        # Model size via pickle estimate
        import pickle
        model_bytes = len(pickle.dumps(model))

        # Inference benchmark on validation set
        bench_batch, bench_single = _benchmark_inference(model, X_val)

        return AlternativeModelResult(
            model_name="random_forest",
            model=model,
            train_accuracy=train_acc,
            val_accuracy=val_acc,
            train_logloss=train_ll,
            val_logloss=val_ll,
            training_duration_seconds=training_duration,
            model_size_bytes=model_bytes,
            inference_time_batched_us=bench_batch,
            inference_time_single_us=bench_single,
            model_params=params,
        )


class MLPTrainer:
    """MLP (Multi-Layer Perceptron) classifier trainer for model comparison.

    Wraps sklearn.neural_network.MLPClassifier with a consistent interface.

    Usage:
        trainer = MLPTrainer(random_seed=42)
        result = trainer.train(X_train, y_train, X_val, y_val)
    """

    def __init__(
        self,
        random_seed: int = RANDOM_SEED,
        hyperparameters: Optional[Dict[str, Any]] = None,
    ):
        """Initialize MLP trainer.

        Args:
            random_seed: Random seed (applied as MLP random_state).
            hyperparameters: Model hyperparameters. If None, uses
                MLP_DEFAULT_PARAMS.
        """
        self._random_seed = random_seed
        self._hyperparameters = hyperparameters or MLP_DEFAULT_PARAMS.copy()

    @property
    def hyperparameters(self) -> Dict[str, Any]:
        return self._hyperparameters.copy()

    def train(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_val: np.ndarray,
        y_val: np.ndarray,
    ) -> AlternativeModelResult:
        """Train an MLP classifier and return metrics.

        Args:
            X_train: Training feature matrix.
            y_train: Training label vector (string or integer).
            X_val: Validation feature matrix.
            y_val: Validation label vector.

        Returns:
            AlternativeModelResult with trained model and metrics.
        """
        y_train_int = _encode_labels(y_train)
        y_val_int = _encode_labels(y_val)

        params = self._hyperparameters.copy()
        params["random_state"] = self._random_seed

        model = MLPClassifier(**params)

        start_time = time.monotonic()
        model.fit(X_train, y_train_int)
        training_duration = time.monotonic() - start_time

        # Predictions
        train_probs = model.predict_proba(X_train)
        val_probs = model.predict_proba(X_val)
        train_preds = np.argmax(train_probs, axis=1)
        val_preds = np.argmax(val_probs, axis=1)

        # Accuracy
        train_acc = float(accuracy_score(y_train_int, train_preds))
        val_acc = float(accuracy_score(y_val_int, val_preds))

        # Log-loss
        try:
            train_ll = float(log_loss(y_train_int, train_probs))
        except Exception:
            train_ll = 0.0
        try:
            val_ll = float(log_loss(y_val_int, val_probs))
        except Exception:
            val_ll = 0.0

        # Model size via pickle
        import pickle
        model_bytes = len(pickle.dumps(model))

        # Inference benchmark
        bench_batch, bench_single = _benchmark_inference(model, X_val)

        return AlternativeModelResult(
            model_name="mlp",
            model=model,
            train_accuracy=train_acc,
            val_accuracy=val_acc,
            train_logloss=train_ll,
            val_logloss=val_ll,
            training_duration_seconds=training_duration,
            model_size_bytes=model_bytes,
            inference_time_batched_us=bench_batch,
            inference_time_single_us=bench_single,
            model_params=params,
        )


# ---------------------------------------------------------------------------
# XGBoost baseline wrapper
# ---------------------------------------------------------------------------


def _train_xgboost_baseline(
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_val: np.ndarray,
    y_val: np.ndarray,
    mode: str = "SWING",
    random_seed: int = RANDOM_SEED,
) -> AlternativeModelResult:
    """Train the XGBoost baseline model using the same split.

    Args:
        X_train: Training feature matrix.
        y_train: Training label vector.
        X_val: Validation feature matrix.
        y_val: Validation label vector.
        mode: Trading mode for profile selection.
        random_seed: Random seed.

    Returns:
        AlternativeModelResult for XGBoost.
    """
    # Use XGBoostTrainer but with the provided split
    y_train_int = _encode_labels(y_train)
    y_val_int = _encode_labels(y_val)

    # Combine back for XGBoostTrainer, but tell it to use val_fraction=0
    # Better: use sklearn-compatible XGBClassifier directly
    import xgboost as xgb

    xgb_hp = SWING_DEFAULT_HYPERPARAMS.copy()
    xgb_hp["random_state"] = random_seed
    xgb_hp["verbosity"] = 0

    # Remove non-XGBClassifier/non-Booster params (kept in dict only for compat)
    xgb_hp.pop("early_stopping_rounds", None)
    n_estimators = xgb_hp.pop("n_estimators", 200)
    xgb_hp.pop("eval_metric", None)

    # Build XGBClassifier with params dict; avoid duplicate kwargs
    model = xgb.XGBClassifier(
        n_estimators=n_estimators,
        eval_metric="mlogloss",
        **xgb_hp,
    )

    start_time = time.monotonic()
    model.fit(
        X_train, y_train_int,
        eval_set=[(X_val, y_val_int)],
        verbose=False,
    )
    training_duration = time.monotonic() - start_time

    # Predictions
    train_probs = model.predict_proba(X_train)
    val_probs = model.predict_proba(X_val)
    train_preds = np.argmax(train_probs, axis=1)
    val_preds = np.argmax(val_probs, axis=1)

    train_acc = float(accuracy_score(y_train_int, train_preds))
    val_acc = float(accuracy_score(y_val_int, val_preds))

    try:
        train_ll = float(log_loss(y_train_int, train_probs))
    except Exception:
        train_ll = 0.0
    try:
        val_ll = float(log_loss(y_val_int, val_probs))
    except Exception:
        val_ll = 0.0

    # Model size
    import pickle
    model_bytes = len(pickle.dumps(model.get_booster()))

    # Inference benchmark
    bench_batch, bench_single = _benchmark_inference(model, X_val)

    return AlternativeModelResult(
        model_name="xgboost",
        model=model,
        train_accuracy=train_acc,
        val_accuracy=val_acc,
        train_logloss=train_ll,
        val_logloss=val_ll,
        training_duration_seconds=training_duration,
        model_size_bytes=model_bytes,
        inference_time_batched_us=bench_batch,
        inference_time_single_us=bench_single,
        model_params=xgb_hp,
    )


# ---------------------------------------------------------------------------
# Inference benchmark utilities
# ---------------------------------------------------------------------------


def _benchmark_inference(
    model: BaseEstimator,
    X_val: np.ndarray,
    warmup: int = BENCHMARK_WARMUP,
    rounds: int = BENCHMARK_ROUNDS,
) -> Tuple[float, float]:
    """Benchmark inference latency for a trained model.

    Measures both batched (full validation set) and single-sample inference
    in microseconds per sample.

    Args:
        model: Trained sklearn-compatible estimator (must have predict_proba).
        X_val: Validation feature matrix.
        warmup: Number of warmup rounds (not timed).
        rounds: Number of timed rounds for batched inference.

    Returns:
        Tuple of (batched_mean_us_per_sample, single_mean_us_per_sample).
    """
    # Batched inference
    for _ in range(warmup):
        model.predict_proba(X_val)

    batch_times: List[float] = []
    for _ in range(rounds):
        t0 = time.perf_counter_ns()
        model.predict_proba(X_val)
        t1 = time.perf_counter_ns()
        batch_times.append((t1 - t0) / 1_000.0)  # ns -> us

    mean_batched_us = float(np.mean(batch_times)) / len(X_val)

    # Single-sample inference
    single_times: List[float] = []
    sample = X_val[:1]
    for _ in range(warmup):
        model.predict_proba(sample)

    for _ in range(rounds):
        t0 = time.perf_counter_ns()
        model.predict_proba(sample)
        t1 = time.perf_counter_ns()
        single_times.append((t1 - t0) / 1_000.0)  # ns -> us

    mean_single_us = float(np.mean(single_times))

    return mean_batched_us, mean_single_us


# ---------------------------------------------------------------------------
# Data splitting (consistent across models)
# ---------------------------------------------------------------------------


def _consistent_split(
    X: np.ndarray,
    y: np.ndarray,
    val_fraction: float = VAL_FRACTION,
    random_seed: int = RANDOM_SEED,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Split data into train/val sets consistently.

    Uses a deterministic shuffle so every model sees the identical split.

    Args:
        X: Feature matrix.
        y: Label vector.
        val_fraction: Fraction of data to hold out for validation.
        random_seed: Random seed for deterministic shuffle.

    Returns:
        (X_train, X_val, y_train, y_val).
    """
    rng = np.random.RandomState(random_seed)
    n = len(y)
    n_val = max(1, int(n * val_fraction))
    indices = np.arange(n)
    rng.shuffle(indices)

    val_idx = indices[:n_val]
    train_idx = indices[n_val:]

    return (
        X[train_idx],
        X[val_idx],
        y[train_idx],
        y[val_idx],
    )


# ---------------------------------------------------------------------------
# Main comparison entry point
# ---------------------------------------------------------------------------


def compare_models(
    X: np.ndarray,
    y: np.ndarray,
    mode: str = "SWING",
    random_seed: int = RANDOM_SEED,
    val_fraction: float = VAL_FRACTION,
    include_xgboost: bool = True,
    include_random_forest: bool = True,
    include_mlp: bool = True,
) -> ModelComparisonResult:
    """Compare multiple model architectures head-to-head on identical data.

    Trains each specified model on the same train/val split, collects
    accuracy, log-loss, training speed, inference speed, and model size
    metrics, then recommends the best model.

    Args:
        X: Feature matrix of shape (n_samples, n_features).
        y: Label vector of shape (n_samples,) — string or integer labels.
        mode: Trading mode label (for metadata only).
        random_seed: Random seed for reproducible split and training.
        val_fraction: Fraction of data for validation.
        include_xgboost: Whether to include XGBoost baseline.
        include_random_forest: Whether to include RandomForest.
        include_mlp: Whether to include MLP.

    Returns:
        ModelComparisonResult with per-model results, best model
        recommendation, and inference benchmark.

    Raises:
        ValueError: If X or y have invalid shape or no models selected.
    """
    if not isinstance(X, np.ndarray) or X.ndim != 2:
        raise ValueError(f"X must be 2D numpy array, got {type(X).__name__} {X.ndim}D")
    if not isinstance(y, np.ndarray):
        raise ValueError(f"y must be numpy array, got {type(y).__name__}")
    if len(X) != len(y):
        raise ValueError(f"X and y length mismatch: {len(X)} vs {len(y)}")
    if len(X) < 20:
        raise ValueError(f"Need at least 20 samples, got {len(X)}")

    active = [include_xgboost, include_random_forest, include_mlp]
    if not any(active):
        raise ValueError("At least one model type must be enabled")

    # Split data consistently
    X_train, X_val, y_train, y_val = _consistent_split(
        X, y, val_fraction=val_fraction, random_seed=random_seed,
    )

    results: List[AlternativeModelResult] = []

    # --- XGBoost baseline ---
    if include_xgboost:
        logger.info("Training XGBoost baseline...")
        xgb_result = _train_xgboost_baseline(
            X_train, y_train, X_val, y_val,
            mode=mode, random_seed=random_seed,
        )
        results.append(xgb_result)

    # --- RandomForest ---
    if include_random_forest:
        logger.info("Training RandomForest...")
        rf_trainer = RandomForestTrainer(random_seed=random_seed)
        rf_result = rf_trainer.train(X_train, y_train, X_val, y_val)
        results.append(rf_result)

    # --- MLP ---
    if include_mlp:
        logger.info("Training MLP...")
        mlp_trainer = MLPTrainer(random_seed=random_seed)
        mlp_result = mlp_trainer.train(X_train, y_train, X_val, y_val)
        results.append(mlp_result)

    # Determine best model (highest val_accuracy, ties broken by speed)
    best = _determine_best(results)

    # Build comparison table
    comparison_df = _build_comparison_table(results)

    # Inference benchmark
    ib = _build_inference_benchmark(results)

    # Per-mode recommendations
    recommendations = _build_recommendations(results, mode)

    return ModelComparisonResult(
        mode=mode,
        n_samples=len(y),
        n_features=X.shape[1],
        per_model=results,
        best_model=best,
        comparison_df=comparison_df,
        inference_benchmark=ib,
        recommendations=recommendations,
    )


# ---------------------------------------------------------------------------
# Best model determination
# ---------------------------------------------------------------------------


def _determine_best(results: List[AlternativeModelResult]) -> str:
    """Pick the best model by validation accuracy, tie-breaking by speed.

    Args:
        results: List of model results.

    Returns:
        Model name string.
    """
    if not results:
        return ""

    # Sort by val_accuracy descending, then batched speed ascending
    sorted_results = sorted(
        results,
        key=lambda r: (-r.val_accuracy, r.inference_time_batched_us),
    )
    return sorted_results[0].model_name


# ---------------------------------------------------------------------------
# Comparison table
# ---------------------------------------------------------------------------


def _build_comparison_table(
    results: List[AlternativeModelResult],
) -> List[Dict[str, Any]]:
    """Build a JSON-serializable comparison table.

    Args:
        results: List of model results.

    Returns:
        List of dicts, one per model, with flattened metrics.
    """
    table: List[Dict[str, Any]] = []
    for r in results:
        table.append({
            "model": r.model_name,
            "train_accuracy": round(r.train_accuracy, 4),
            "val_accuracy": round(r.val_accuracy, 4),
            "train_logloss": round(r.train_logloss, 4),
            "val_logloss": round(r.val_logloss, 4),
            "training_seconds": round(r.training_duration_seconds, 4),
            "model_size_bytes": r.model_size_bytes,
            "inference_batched_us_per_sample": round(r.inference_time_batched_us, 2),
            "inference_single_us": round(r.inference_time_single_us, 2),
        })
    return table


# ---------------------------------------------------------------------------
# Inference benchmark aggregation
# ---------------------------------------------------------------------------


def _build_inference_benchmark(
    results: List[AlternativeModelResult],
) -> InferenceBenchmark:
    """Build InferenceBenchmark from model results.

    Args:
        results: List of model results with inference timing.

    Returns:
        InferenceBenchmark with per-model latencies.
    """
    per_model: List[BenchmarkResult] = []
    for r in results:
        per_model.append(BenchmarkResult(
            model_name=r.model_name,
            mean_batched_us=r.inference_time_batched_us,
            std_batched_us=0.0,  # single-point measure from benchmark
            mean_single_us=r.inference_time_single_us,
            std_single_us=0.0,
        ))

    fastest_batch = min(r.inference_time_batched_us for r in results) if results else 0.0
    fastest_single = min(r.inference_time_single_us for r in results) if results else 0.0

    return InferenceBenchmark(
        per_model=per_model,
        fastest_batched_us=fastest_batch,
        fastest_single_us=fastest_single,
    )


# ---------------------------------------------------------------------------
# Per-mode recommendations
# ---------------------------------------------------------------------------


def _build_recommendations(
    results: List[AlternativeModelResult],
    mode: str,
) -> Dict[str, List[str]]:
    """Build per-model recommendation lists.

    Assigns the current mode to the best model, and notes other models
    as secondary alternatives.

    Args:
        results: List of model results.
        mode: Current trading mode.

    Returns:
        Dict mapping model name to list of modes it is recommended for.
    """
    if not results:
        return {}

    best = _determine_best(results)
    recs: Dict[str, List[str]] = {}

    for r in results:
        if r.model_name == best:
            recs[r.model_name] = ["PRIMARY"]
        else:
            recs[r.model_name] = ["ALTERNATIVE"]

    recs["strategy"] = [f"best_for_{mode.lower()}", best]

    return recs


# ---------------------------------------------------------------------------
# Standalone inference cost benchmark
# ---------------------------------------------------------------------------


def inference_cost_benchmark(
    X: np.ndarray,
    models: Dict[str, BaseEstimator],
    warmup: int = BENCHMARK_WARMUP,
    rounds: int = BENCHMARK_ROUNDS,
) -> InferenceBenchmark:
    """Benchmark inference cost across multiple pre-trained models.

    Useful for comparing latency after training is complete.

    Args:
        X: Feature matrix (validation set) for batched inference.
        models: Dict mapping model_name -> trained estimator (must have
            predict_proba).
        warmup: Warmup rounds.
        rounds: Timed rounds.

    Returns:
        InferenceBenchmark with per-model latencies.
    """
    per_model: List[BenchmarkResult] = []
    for name, model in models.items():
        batch_us, single_us = _benchmark_inference(
            model, X, warmup=warmup, rounds=rounds,
        )
        per_model.append(BenchmarkResult(
            model_name=name,
            mean_batched_us=batch_us,
            std_batched_us=0.0,
            mean_single_us=single_us,
            std_single_us=0.0,
        ))

    fastest_batch = min(r.mean_batched_us for r in per_model) if per_model else 0.0
    fastest_single = min(r.mean_single_us for r in per_model) if per_model else 0.0

    return InferenceBenchmark(
        per_model=per_model,
        fastest_batched_us=fastest_batch,
        fastest_single_us=fastest_single,
    )


# ---------------------------------------------------------------------------
# Convenience: best per mode
# ---------------------------------------------------------------------------


def recommend_best_per_mode(
    results_by_mode: Dict[str, ModelComparisonResult],
) -> Dict[str, Dict[str, Any]]:
    """Aggregate recommendations across multiple mode comparisons.

    Args:
        results_by_mode: Dict mapping mode -> ModelComparisonResult.

    Returns:
        Dict mapping mode -> {'best_model': str, 'metrics': dict}.
    """
    recommendations: Dict[str, Dict[str, Any]] = {}
    for mode, result in results_by_mode.items():
        best_entry = None
        for r in result.per_model:
            if r.model_name == result.best_model:
                best_entry = r
                break
        recommendations[mode] = {
            "best_model": result.best_model,
            "val_accuracy": best_entry.val_accuracy if best_entry else 0.0,
            "val_logloss": best_entry.val_logloss if best_entry else 0.0,
            "training_seconds": best_entry.training_duration_seconds if best_entry else 0.0,
            "inference_batched_us": best_entry.inference_time_batched_us if best_entry else 0.0,
            "n_samples": result.n_samples,
            "n_features": result.n_features,
        }
    return recommendations
