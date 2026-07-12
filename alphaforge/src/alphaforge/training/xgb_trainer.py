"""XGBoost Trainer — SWING mode alpha model training.

This module trains XGBoost classifier models for AlphaForge mode-specific
alpha evidence. It consumes feature matrices and labels assembled by the
dataset pipeline (features/pipeline.py + labels/adapter.py + dataset/assembler.py).

Produces:
  1. Model binary (XGBoost JSON format) at artifact_uri
  2. ModelArtifact metadata dict per model_artifact_contract.md

Design constraints:
  - Conservative hyperparameters for SWING baseline (LOCKED_INITIAL_BASELINE)
  - Multi-class classification: LONG_NOW, SHORT_NOW, NO_TRADE
  - Deterministic random seed (no stochastic variance between runs)
  - Feature importance computed via xgboost built-in
  - Training metrics tracked: accuracy, logloss, per-class precision/recall
  - Walk-forward fold support: train per fold, aggregate metrics

This module DOES import xgboost. It is intended for the training environment,
NOT the gate-check environment where the ml_pilot gate enforces GBM absence.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import xgboost as xgb

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCHEMA_VERSION: str = "1.0.0"
MODEL_FAMILY: str = "xgboost"
ARTIFACT_DIR_DEFAULT: str = "artifacts/models"

# Label mapping for multi-class classification
LABEL_TO_INT: Dict[str, int] = {
    "LONG_NOW": 0,
    "SHORT_NOW": 1,
    "NO_TRADE": 2,
}

INT_TO_LABEL: Dict[int, str] = {v: k for k, v in LABEL_TO_INT.items()}
NUM_CLASSES: int = 3

# ---------------------------------------------------------------------------
# GPU / ROCm detection
# ---------------------------------------------------------------------------


def _detect_gpu() -> dict[str, str]:
    """Detect available GPU backend for XGBoost.

    Checks CUDA/HIP build-time support AND runtime availability.
    Tries nvidia-smi for CUDA GPUs, rocm-smi for AMD GPUs.
    Falls back to CPU (hist) when no GPU is available at runtime.

    Can be overridden via the environment variable
    ``ALPHAFORGE_XGB_DEVICE`` set to ``cuda`` or ``cpu``.

    Returns {"tree_method": ..., "device": ...} or {"tree_method": "hist"}.
    """
    # Environment override (checked first for SSH/cron environments where
    # nvidia-smi may not be on PATH at import time)
    env_device = os.environ.get("ALPHAFORGE_XGB_DEVICE", "").strip().lower()
    if env_device == "cuda":
        logger.info("XGBoost GPU: ALPHAFORGE_XGB_DEVICE=cuda — forcing device=cuda")
        return {"tree_method": "hist", "device": "cuda"}
    if env_device == "cpu":
        logger.info("XGBoost GPU: ALPHAFORGE_XGB_DEVICE=cpu — forcing CPU hist")
        return {"tree_method": "hist"}

    try:
        info = xgb.build_info()
        has_cuda = info.get("USE_CUDA") or info.get("USE_HIP")

        if has_cuda:
            import subprocess
            # Try NVIDIA CUDA first
            try:
                r = subprocess.run(
                    ["nvidia-smi"], capture_output=True, text=True, timeout=3
                )
                if r.returncode == 0:
                    backend = "ROCm/HIP" if info.get("USE_HIP") else "CUDA"
                    logger.info("XGBoost GPU: %s detected — using device=cuda", backend)
                    # XGBoost 3.x: gpu_hist deprecated, use device='cuda' with tree_method='hist'
                    return {"tree_method": "hist", "device": "cuda"}
            except (FileNotFoundError, subprocess.TimeoutExpired):
                pass

            # Try AMD ROCm as fallback — rocm-smi
            try:
                r = subprocess.run(
                    ["rocm-smi"], capture_output=True, text=True, timeout=3
                )
                if r.returncode == 0:
                    logger.info("XGBoost: AMD ROCm detected but xgboost compiled with CUDA — using CPU hist")
                    # Can't use AMD GPU with CUDA-compiled XGBoost
            except (FileNotFoundError, subprocess.TimeoutExpired):
                pass

            # Check /dev/kfd (ROCm device presence)
            if os.path.exists("/dev/kfd"):
                logger.info("XGBoost: /dev/kfd found (ROCm) but xgboost is CUDA-compiled — CPU fallback")

            logger.info(
                "XGBoost compiled with CUDA/HIP but no compatible GPU available — using CPU hist"
            )
    except Exception:
        pass

    logger.info("XGBoost GPU: none detected — using CPU hist")
    return {"tree_method": "hist"}


GPU_PARAMS: dict[str, str] = _detect_gpu()

# ── Mode-specific default hyperparameters (LOCKED_INITIAL_BASELINE) ──
# Each mode's defaults are derived from the canonical tuning profile
# mid-points (see alphaforge.tuning.mode_profiles).
#
# SWING — secondary baseline, conservative (4h timeframe)
#   Shallow trees (max_depth=4), low learning rate, strong regularisation.
SWING_DEFAULT_HYPERPARAMS: Dict[str, Any] = {
    "objective": "multi:softprob",
    "num_class": NUM_CLASSES,
    "max_depth": 4,
    "learning_rate": 0.05,
    "n_estimators": 80,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "min_child_weight": 5,
    "gamma": 0.1,
    "reg_alpha": 0.1,
    "reg_lambda": 1.0,
    "eval_metric": "mlogloss",
    "early_stopping_rounds": 20,
    "random_state": 42,
    "verbosity": 0,
    **GPU_PARAMS,
}

# SCALP — primary mode, medium-frequency (1h timeframe)
#   Faster learning rate (0.1), shallower trees (max_depth=4),
#   medium regularisation — adapts to noisier 1h data.
SCALP_DEFAULT_HYPERPARAMS: Dict[str, Any] = {
    "objective": "multi:softprob",
    "num_class": NUM_CLASSES,
    "max_depth": 4,
    "learning_rate": 0.1,
    "n_estimators": 120,
    "subsample": 0.9,
    "colsample_bytree": 0.9,
    "min_child_weight": 3,
    "gamma": 0.05,
    "reg_alpha": 0.05,
    "reg_lambda": 0.5,
    "eval_metric": "mlogloss",
    "early_stopping_rounds": 20,
    "random_state": 42,
    "verbosity": 0,
    **GPU_PARAMS,
}

# AGGRESSIVE_SCALP — primary mode, high-frequency (15m/5m timeframe)
#   Fastest learning rate (0.15), shallowest trees (max_depth=3),
#   lighter regularisation for rapid adaptation to microstructure.
AGGRESSIVE_SCALP_DEFAULT_HYPERPARAMS: Dict[str, Any] = {
    "objective": "multi:softprob",
    "num_class": NUM_CLASSES,
    "max_depth": 3,
    "learning_rate": 0.15,
    "n_estimators": 150,
    "subsample": 0.95,
    "colsample_bytree": 0.95,
    "min_child_weight": 2,
    "gamma": 0.02,
    "reg_alpha": 0.01,
    "reg_lambda": 0.2,
    "eval_metric": "mlogloss",
    "early_stopping_rounds": 20,
    "random_state": 42,
    "verbosity": 0,
    **GPU_PARAMS,
}

# Lookup table for mode → default hyperparameters
_MODE_DEFAULT_HP: Dict[str, Dict[str, Any]] = {
    "SWING": SWING_DEFAULT_HYPERPARAMS,
    "SCALP": SCALP_DEFAULT_HYPERPARAMS,
    "AGGRESSIVE_SCALP": AGGRESSIVE_SCALP_DEFAULT_HYPERPARAMS,
}

# Test fraction for hold-out validation within training
VAL_FRACTION: float = 0.2

RANDOM_SEED: int = 42


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class TrainingResult:
    """Result of a single training run.

    Attributes:
        model: Trained xgboost Booster.
        model_artifact: ModelArtifact metadata dict per contract.
        model_binary_bytes: Serialized model bytes.
        train_metrics: Training metrics dict.
        val_metrics: Validation metrics dict.
        training_duration_seconds: Wall-clock training time.
    """

    model: xgb.Booster
    model_artifact: Dict[str, Any]
    model_binary_bytes: bytes
    train_metrics: Dict[str, Any]
    val_metrics: Dict[str, Any]
    training_duration_seconds: float


# ---------------------------------------------------------------------------
# XGBoostTrainer
# ---------------------------------------------------------------------------


class XGBoostTrainer:
    """XGBoost classifier trainer for AlphaForge mode-specific models.

    Public methods:
        train(X, y, **kwargs) -> TrainingResult
        save_artifact(result, artifact_dir) -> Path (model binary path)
        build_model_artifact_metadata(result, artifact_uri, **kwargs) -> dict

    Usage:
        trainer = XGBoostTrainer(mode="SWING", random_seed=42)
        result = trainer.train(X_train, y_train)
        artifact_path = trainer.save_artifact(result, "artifacts/models")
        metadata = trainer.build_model_artifact_metadata(
            result, f"file://{artifact_path}"
        )
    """

    def __init__(
        self,
        mode: str = "SWING",
        random_seed: int = RANDOM_SEED,
        hyperparameters: Optional[Dict[str, Any]] = None,
        objective: str = "multi:softprob",
    ):
        """Initialize trainer.

        Args:
            mode: Trading mode (SWING, SCALP, AGGRESSIVE_SCALP).
            random_seed: Random seed for reproducibility.
            hyperparameters: Training hyperparameters. If None, uses
                mode-specific defaults from _MODE_DEFAULT_HP.
        """
        if mode not in ("SWING", "SCALP", "AGGRESSIVE_SCALP"):
            raise ValueError(
                f"Unsupported mode: '{mode}'. Must be SWING, SCALP, or AGGRESSIVE_SCALP."
            )
        self._mode = mode
        self._random_seed = random_seed
        if hyperparameters is not None:
            self._hyperparameters = hyperparameters.copy()
        else:
            self._hyperparameters = _MODE_DEFAULT_HP.get(mode, SWING_DEFAULT_HYPERPARAMS).copy()
        self._rng = np.random.RandomState(random_seed)
        self._objective = objective

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def hyperparameters(self) -> Dict[str, Any]:
        return self._hyperparameters.copy()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def train(
        self,
        X: np.ndarray,
        y: np.ndarray,
        feature_names: Optional[List[str]] = None,
        val_fraction: float = VAL_FRACTION,
        pruning_callback: Optional["xgb.callback.TrainingCallback"] = None,
    ) -> TrainingResult:
        """Train an XGBoost classifier model.

        Args:
            X: Feature matrix of shape (n_samples, n_features). Must be float64.
            y: Label vector of shape (n_samples,). Can be string labels
               (LONG_NOW/SHORT_NOW/NO_TRADE) or integer labels (0/1/2).
            feature_names: Optional list of feature names for importance.
            val_fraction: Fraction of training data to use for validation.
            pruning_callback: Optional Optuna/XGBoost pruning callback.
                When provided, it is passed as a training callback so that
                the pruner can kill bad trials during hyperparameter search.

        Returns:
            TrainingResult with trained model, artifact metadata, and metrics.

        Raises:
            ValueError: If inputs are invalid (wrong shape, all NaN, etc.).
        """
        self._validate_inputs(X, y)

        # Convert string labels to int if needed
        y_int = self._encode_labels(y)

        # Split into train/val — chronological tail split (rows entering
        # train() are time-ordered from build_aligned_training_frame's lexsort).
        # Using a chronological split prevents temporal leakage into early
        # stopping that would occur with a random shuffle.
        n_samples = len(y_int)
        n_val = max(1, int(n_samples * val_fraction))
        val_indices = np.arange(n_samples - n_val, n_samples)
        train_indices = np.arange(0, n_samples - n_val)

        X_train = X[train_indices]
        y_train = y_int[train_indices]
        X_val = X[val_indices]
        y_val = y_int[val_indices]

        # ── Class imbalance weighting (inverse frequency) ────────────────
        # Compute per-class frequency on TRAIN fold only.
        # Apply inverse-frequency weight to each training sample so that
        # minority classes are not dominated by majority class during
        # gradient computation. Validation set uses NO sample weights.
        classes, counts = np.unique(y_train, return_counts=True)
        n_classes = len(classes)
        if n_classes < 2:
            # Single class — no meaningful weighting
            sample_weight_train = np.ones(len(y_train), dtype=np.float64)
            class_weight_map = {int(c): 1.0 for c in classes}
        else:
            max_count = float(counts.max())
            # Inverse frequency: minority classes get weight > 1
            class_weight_map = {
                int(c): max_count / float(cnt) for c, cnt in zip(classes, counts)
            }
            sample_weight_train = np.array(
                [class_weight_map[int(y)] for y in y_train], dtype=np.float64
            )
        # Normalise weights so mean = 1 (scale-preserving)
        n_train = len(sample_weight_train)
        if n_train > 0:
            sample_weight_train *= float(n_train) / sample_weight_train.sum()

        self._last_class_weights = class_weight_map
        self._last_class_counts = dict(zip(classes, counts))

        # Prepare DMatrix — use QuantileDMatrix for GPU (lower memory, faster binning)
        _device = self._hyperparameters.get("device", "cpu")
        if _device == "cuda":
            _X_train_32 = X_train.astype(np.float32, copy=False)
            _X_val_32 = X_val.astype(np.float32, copy=False)
            dtrain = xgb.QuantileDMatrix(_X_train_32, label=y_train, weight=sample_weight_train)
            if feature_names:
                dtrain.feature_names = feature_names
            dval = xgb.QuantileDMatrix(_X_val_32, label=y_val, ref=dtrain)
            if feature_names:
                dval.feature_names = feature_names
        else:
            dtrain = xgb.DMatrix(X_train, label=y_train, weight=sample_weight_train)
            if feature_names:
                dtrain.feature_names = feature_names
            dval = xgb.DMatrix(X_val, label=y_val)
            if feature_names:
                dval.feature_names = feature_names

        # Extract training params (strip non-xgb params)
        params = self._extract_xgb_params()

        # Build callbacks list (only pruning_callback if provided)
        callbacks: List = []
        if pruning_callback is not None:
            callbacks.append(pruning_callback)

        # Train
        start_time = time.monotonic()

        evals_result: Dict[str, Any] = {}
        booster = xgb.train(
            params=params,
            dtrain=dtrain,
            num_boost_round=self._hyperparameters.get("n_estimators", 200),
            evals=[(dtrain, "train"), (dval, "val")],
            evals_result=evals_result,
            early_stopping_rounds=self._hyperparameters.get("early_stopping_rounds", 20),
            callbacks=callbacks if callbacks else None,
            verbose_eval=False,
        )

        training_duration = time.monotonic() - start_time

        # Compute metrics
        train_metrics = self._compute_metrics(booster, dtrain, y_train)
        val_metrics = self._compute_metrics(booster, dval, y_val)

        # Feature importance
        feature_importance = self._compute_feature_importance(
            booster, feature_names
        )

        # Build model artifact metadata
        model_binary = booster.save_raw()
        checksum = hashlib.sha256(model_binary).hexdigest()

        now_iso = datetime.now(timezone.utc).isoformat()

        model_artifact: Dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "model_artifact_id": "",
            "model_family": MODEL_FAMILY,
            "mode": self._mode,
            "training_run_id": "",
            "feature_set_id": "",
            "label_dataset_id": "",
            "validation_report_id": "",
            "artifact_uri": "",
            "checksum": checksum,
            "checksum_algorithm": "SHA-256",
            "created_at": now_iso,
            "limitations": [
                f"{self._mode} baseline model — mode-specific hyperparameters",
                "Trained on synthetic/deterministic feature data only",
                "Walk-forward fold metrics not yet populated — placeholder only",
                "Calibration not applied — model outputs are raw probabilities",
                "NO_TRADE is a learned class; threshold tuning required for deployment",
            ],
            "hyperparameters": self._hyperparameters.copy(),
            "feature_importance": feature_importance,
            "training_metrics": {
                "train_accuracy": train_metrics.get("accuracy", 0.0),
                "val_accuracy": val_metrics.get("accuracy", 0.0),
                "train_logloss": train_metrics.get("logloss", 0.0),
                "val_logloss": val_metrics.get("logloss", 0.0),
            },
            "class_weights": getattr(self, "_last_class_weights", {}),
            "class_counts": getattr(self, "_last_class_counts", {}),
            "model_size_bytes": len(model_binary),
            "framework_version": f"xgboost=={xgb.__version__}",
            "training_duration_seconds": training_duration,
            "environment_hash": "",
        }

        return TrainingResult(
            model=booster,
            model_artifact=model_artifact,
            model_binary_bytes=model_binary,
            train_metrics=train_metrics,
            val_metrics=val_metrics,
            training_duration_seconds=training_duration,
        )

    def save_artifact(
        self,
        result: TrainingResult,
        artifact_dir: str = ARTIFACT_DIR_DEFAULT,
        model_artifact_id: str = "",
        artifact_filename: Optional[str] = None,
    ) -> Path:
        """Save model binary to disk and return the path.

        Args:
            result: TrainingResult from train().
            artifact_dir: Directory to save the model artifact.
            model_artifact_id: Identifier for the model artifact.
            artifact_filename: Optional filename override.

        Returns:
            Path to the saved model binary file.
        """
        dir_path = Path(artifact_dir)
        dir_path.mkdir(parents=True, exist_ok=True)

        if artifact_filename is None:
            ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            artifact_filename = f"xgb_{self._mode.lower()}_{ts}.json"

        file_path = dir_path / artifact_filename

        result.model.save_model(str(file_path))
        logger.info(f"Model saved to {file_path}")
        return file_path

    def build_model_artifact_metadata(
        self,
        result: TrainingResult,
        artifact_uri: str,
        model_artifact_id: str = "",
        training_run_id: str = "",
        feature_set_id: str = "",
        label_dataset_id: str = "",
        validation_report_id: str = "",
    ) -> Dict[str, Any]:
        """Build final ModelArtifact metadata dict.

        Args:
            result: TrainingResult from train().
            artifact_uri: URI to the model binary (e.g., file:///path/to/model.json).
            model_artifact_id: Unique model artifact identifier.
            training_run_id: ResearchRunManifest run_id.
            feature_set_id: FeatureSetSpec ID.
            label_dataset_id: LabelDatasetSpec ID.
            validation_report_id: Associated ValidationReport ID.

        Returns:
            ModelArtifact-compatible dict per model_artifact_contract.md.
        """
        metadata = result.model_artifact.copy()
        metadata["artifact_uri"] = artifact_uri
        metadata["model_artifact_id"] = model_artifact_id
        metadata["training_run_id"] = training_run_id
        metadata["feature_set_id"] = feature_set_id
        metadata["label_dataset_id"] = label_dataset_id
        metadata["validation_report_id"] = validation_report_id

        # Recompute checksum from actual saved bytes
        if result.model_binary_bytes:
            metadata["checksum"] = hashlib.sha256(
                result.model_binary_bytes
            ).hexdigest()

        return metadata

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _validate_inputs(self, X: np.ndarray, y: np.ndarray) -> None:
        """Validate training inputs."""
        if not isinstance(X, np.ndarray):
            raise TypeError(f"X must be numpy.ndarray, got {type(X).__name__}")
        if not isinstance(y, np.ndarray):
            raise TypeError(f"y must be numpy.ndarray, got {type(y).__name__}")

        if X.ndim != 2:
            raise ValueError(f"X must be 2D, got {X.ndim}D")
        if y.ndim != 1:
            raise ValueError(f"y must be 1D, got {y.ndim}D")

        if len(X) != len(y):
            raise ValueError(
                f"X and y must have same length, got {len(X)} and {len(y)}"
            )

        if len(X) < 10:
            raise ValueError(
                f"Need at least 10 samples for training, got {len(X)}"
            )

        if np.all(np.isnan(X)):
            raise ValueError("X contains all NaN values")

    def _encode_labels(self, y: np.ndarray) -> np.ndarray:
        """Encode string labels to integers."""
        if y.dtype.kind in ("i", "u"):  # Already integer
            unique = set(y)
            if not unique.issubset({0, 1, 2}):
                raise ValueError(
                    f"Integer labels must be in {{0, 1, 2}}, got {unique}"
                )
            return y.astype(int)

        if y.dtype.kind in ("U", "S"):  # String
            result = np.zeros(len(y), dtype=int)
            for i, label in enumerate(y):
                if label not in LABEL_TO_INT:
                    raise ValueError(
                        f"Unknown label '{label}'. Must be LONG_NOW, SHORT_NOW, or NO_TRADE."
                    )
                result[i] = LABEL_TO_INT[label]
            return result

        raise ValueError(
            f"Unsupported label dtype: {y.dtype}. Use string or integer labels."
        )

    def _extract_xgb_params(self) -> Dict[str, Any]:
        """Extract params that xgboost.train() accepts."""
        xgb_param_keys = {
            "objective", "num_class", "max_depth", "learning_rate",
            "subsample", "colsample_bytree", "min_child_weight",
            "gamma", "reg_alpha", "reg_lambda", "eval_metric",
            "random_state", "verbosity", "tree_method", "device",
        }
        params = {}
        for k in xgb_param_keys:
            if k in self._hyperparameters:
                params[k] = self._hyperparameters[k]
        # Override objective from constructor (enables regression mode)
        params["objective"] = self._objective
        return params

    def _compute_metrics(
        self,
        booster: xgb.Booster,
        dmatrix: xgb.DMatrix,
        y_true: np.ndarray,
    ) -> Dict[str, Any]:
        """Compute classification metrics."""
        y_pred_prob = booster.predict(dmatrix)
        y_pred = np.argmax(y_pred_prob, axis=1)

        accuracy = float(np.mean(y_pred == y_true))

        # Per-class precision/recall
        per_class: Dict[str, Dict[str, float]] = {}
        for cls_idx in range(NUM_CLASSES):
            tp = int(np.sum((y_pred == cls_idx) & (y_true == cls_idx)))
            fp = int(np.sum((y_pred == cls_idx) & (y_true != cls_idx)))
            fn = int(np.sum((y_pred != cls_idx) & (y_true == cls_idx)))

            precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
            recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
            f1 = (
                2.0 * precision * recall / (precision + recall)
                if (precision + recall) > 0
                else 0.0
            )
            label_name = INT_TO_LABEL.get(cls_idx, str(cls_idx))
            per_class[label_name] = {
                "precision": float(precision),
                "recall": float(recall),
                "f1": float(f1),
                "support": int(np.sum(y_true == cls_idx)),
            }

        # Log-loss from eval results if available
        logloss = 0.0
        eval_result = booster.eval(dmatrix)
        if eval_result:
            # eval_result is a string like "[0]\teval-mlogloss:1.0986"
            try:
                _, value_str = eval_result.split(":")
                logloss = float(value_str.strip())
            except (ValueError, AttributeError):
                pass

        return {
            "accuracy": accuracy,
            "logloss": logloss,
            "per_class": per_class,
        }

    @staticmethod
    def _compute_feature_importance(
        booster: xgb.Booster,
        feature_names: Optional[List[str]] = None,
    ) -> Dict[str, float]:
        """Compute feature importance scores.

        Uses total_gain if available, falls back to total_cover, then weight.
        """
        try:
            score_map = booster.get_score(importance_type="total_gain")
        except Exception:
            try:
                score_map = booster.get_score(importance_type="total_cover")
            except Exception:
                score_map = booster.get_score(importance_type="weight")

        if not score_map:
            return {}

        # score_map keys are f0, f1, f2, ...
        if feature_names:
            result: Dict[str, float] = {}
            for key, value in score_map.items():
                try:
                    idx = int(key[1:])  # f0 -> 0, f1 -> 1, ...
                except (ValueError, IndexError):
                    result[key] = float(value)
                    continue
                if idx < len(feature_names):
                    result[feature_names[idx]] = float(value)
                else:
                    result[key] = float(value)
            return result

        # Normalize: all scores sum to 1.0
        total = sum(score_map.values())
        if total > 0:
            return {k: float(v / total) for k, v in score_map.items()}
        return {k: float(v) for k, v in score_map.items()}


# ===========================================================================
# SHAP Analysis (using XGBoost native gain as SHAP proxy)
# ===========================================================================

DEFAULT_SHAP_SUBSAMPLE: int = 1000


def compute_shap_analysis(
    boosters: List[xgb.Booster],
    X: np.ndarray,
    feature_names: Optional[List[str]] = None,
    subsample: int = DEFAULT_SHAP_SUBSAMPLE,
) -> Dict[str, Any]:
    """Compute SHAP-like feature attribution from XGBoost boosters.

    Uses XGBoost's native total_gain importance as an aggregate proxy for
    SHAP values (the SHAP package is not required). When the SHAP package
    is available, falls back to TreeExplainer for per-sample attribution.

    Args:
        boosters: List of trained XGBoost Boosters (one per walk-forward fold).
        X: Feature matrix used for training.
        feature_names: Optional list of feature names for human-readable keys.
        subsample: Number of samples for SHAP estimation (default 1000).
            Only used when shap package is available.

    Returns:
        Dict with keys:
            method: str — "xgboost_total_gain" or "shap".
            n_folds: int — number of boosters.
            mean_importance: Dict[str, float] — mean importance per feature.
            std_importance: Dict[str, float] — std importance per feature.
            top_features: List[str] — top-10 features by mean importance.

    Raises:
        ValueError: If boosters list is empty.
    """
    if not boosters:
        raise ValueError("boosters list cannot be empty")

    # Try shap package first
    try:
        import shap
        has_shap = True
    except ImportError:
        has_shap = False

    if has_shap:
        # Use TreeExplainer on the first booster
        n_samples = min(subsample, len(X))
        idx = np.random.RandomState(42).choice(len(X), size=n_samples, replace=False)
        X_sub = X[idx]

        try:
            explainer = shap.TreeExplainer(boosters[0])
            shap_values = explainer.shap_values(X_sub)

            # shap_values shape: (n_samples, n_features, n_classes) or (n_samples, n_features)
            if shap_values.ndim == 3:
                # Multi-class: average absolute SHAP across classes
                imp = np.mean(np.abs(shap_values), axis=(0, 2))
            else:
                imp = np.mean(np.abs(shap_values), axis=0)

            importance = {str(i): float(imp[i]) for i in range(len(imp))}
            method = "shap"
        except Exception:
            # Fallback to gain importance
            has_shap = False

    if not has_shap:
        # Fallback: aggregate total_gain across all boosters
        all_importance: List[Dict[str, float]] = []
        for booster in boosters:
            imp = compute_per_fold_importance(booster, feature_names)
            all_importance.append(imp)

        # Aggregate
        from alphaforge.research.feature_importance import aggregate_fold_importance
        aggregated = aggregate_fold_importance(all_importance, normalize=True)
        importance = aggregated.get("mean", {})
        method = "xgboost_total_gain"

    # Sort by importance descending
    sorted_imp = sorted(importance.items(), key=lambda x: x[1], reverse=True)
    mean_imp = dict(sorted_imp)

    # Top-10 features
    top_features = [name for name, _ in sorted_imp[:10]]

    # Compute std if not already present
    if method == "xgboost_total_gain":
        std_imp = aggregated.get("std", {})
    else:
        std_imp = {name: 0.0 for name in importance}

    return {
        "method": method,
        "n_folds": len(boosters),
        "mean_importance": mean_imp,
        "std_importance": std_imp,
        "top_features": top_features,
    }


def compute_per_fold_importance(
    booster: xgb.Booster,
    feature_names: Optional[List[str]] = None,
) -> Dict[str, float]:
    """Compute per-fold feature importance from a booster.

    Delegates to the feature_importance module for consistency.
    """
    from alphaforge.research.feature_importance import compute_per_fold_importance as _per_fold
    return _per_fold(booster, feature_names)


# ===========================================================================
# MetaLabelingTrainer — two-stage meta-labeling
# ===========================================================================


class MetaLabelingTrainer:
    """Two-stage meta-labeling trainer wrapping two XGBoostTrainer instances.

    Stage 1 (primary): Multi-class classifier predicting LONG_NOW / SHORT_NOW / NO_TRADE.
    Stage 2 (meta):    Binary classifier predicting whether the primary label
                       will succeed (1) or fail (0).

    Usage:
        meta_trainer = MetaLabelingTrainer(mode="SWING")
        meta_trainer.train(X, y_primary, y_meta_binary)
        result = meta_trainer.predict(X)

    Reference:
        Lopez de Prado, M. (2018). Advances in Financial Machine Learning.
        Chapter 9: Meta-Labeling.
    """

    def __init__(
        self,
        mode: str = "SWING",
        random_seed: int = RANDOM_SEED,
        primary_hyperparams: Optional[Dict[str, Any]] = None,
        meta_hyperparams: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Initialize MetaLabelingTrainer.

        Args:
            mode: Trading mode.
            random_seed: Random seed for reproducibility.
            primary_hyperparams: Hyperparameters for the primary classifier.
                If None, uses mode-specific defaults.
            meta_hyperparams: Hyperparameters for the meta classifier.
                If None, uses mode-specific defaults with binary objective.
        """
        primary_hp = (primary_hyperparams or _MODE_DEFAULT_HP.get(mode, SWING_DEFAULT_HYPERPARAMS)).copy()
        meta_hp = (meta_hyperparams or _MODE_DEFAULT_HP.get(mode, SWING_DEFAULT_HYPERPARAMS)).copy()
        meta_hp["objective"] = "binary:logistic"
        meta_hp.pop("num_class", None)

        self._primary = XGBoostTrainer(
            mode=mode,
            random_seed=random_seed,
            hyperparameters=primary_hp,
        )
        self._meta = XGBoostTrainer(
            mode=mode,
            random_seed=random_seed,
            hyperparameters=meta_hp,
        )
        self._primary_result: Optional[TrainingResult] = None
        self._meta_result: Optional[TrainingResult] = None

    @property
    def primary_trainer(self) -> XGBoostTrainer:
        return self._primary

    @property
    def meta_trainer(self) -> XGBoostTrainer:
        return self._meta

    def train(
        self,
        X: np.ndarray,
        y_primary: np.ndarray,
        y_meta_binary: np.ndarray,
        feature_names: Optional[List[str]] = None,
    ) -> Dict[str, TrainingResult]:
        """Train both stages sequentially.

        Args:
            X: Feature matrix of shape (n_samples, n_features).
            y_primary: Primary labels (LONG_NOW / SHORT_NOW / NO_TRADE or 0/1/2).
            y_meta_binary: Meta-labels (0 = fail, 1 = succeed).
            feature_names: Optional list of feature names.

        Returns:
            Dict with keys 'primary' and 'meta' mapping to TrainingResult.
        """
        self._primary_result = self._primary.train(
            X, y_primary, feature_names=feature_names,
        )
        self._meta_result = self._meta.train(
            X, y_meta_binary, feature_names=feature_names,
        )
        return {"primary": self._primary_result, "meta": self._meta_result}

    def predict(
        self,
        X: np.ndarray,
        feature_names: Optional[List[str]] = None,
    ) -> np.ndarray:
        """Predict using meta-labeling decision logic.

        Returns the primary prediction only when meta predicts 1 (success).

        Args:
            X: Feature matrix of shape (n_samples, n_features).
            feature_names: Optional feature names (used for DMatrix only).

        Returns:
            numpy array of shape (n_samples,) with final predictions:
            - Primary label when meta predicts success (1).
            - NO_TRADE (2) when meta predicts failure (0).
        """
        if self._primary_result is None or self._meta_result is None:
            raise RuntimeError("Train must be called before predict")

        dmat = xgb.DMatrix(X)
        if feature_names:
            dmat.feature_names = feature_names

        primary_pred = self._primary_result.model.predict(dmat)
        meta_pred = self._meta_result.model.predict(dmat)

        # Primary: argmax over 3 classes
        if primary_pred.ndim == 1:
            primary_pred = primary_pred.reshape(-1, NUM_CLASSES)
        primary_label = np.argmax(primary_pred, axis=1)

        # Meta: binary probability, threshold 0.5
        meta_label = (meta_pred > 0.5).astype(int).flatten()

        # Final: only take primary when meta says success
        final = np.where(meta_label == 1, primary_label, 2)  # 2 = NO_TRADE
        return final.astype(np.int64)

    def save_artifacts(
        self,
        artifact_dir: str = ARTIFACT_DIR_DEFAULT,
    ) -> Dict[str, Path]:
        """Save both model artifacts.

        Args:
            artifact_dir: Directory to save models.

        Returns:
            Dict with keys 'primary' and 'meta' mapping to Path.
        """
        from datetime import datetime, timezone

        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        primary_path = self._primary.save_artifact(
            self._primary_result,
            artifact_dir=artifact_dir,
            artifact_filename=f"xgb_meta_primary_{ts}.json",
        )
        meta_path = self._meta.save_artifact(
            self._meta_result,
            artifact_dir=artifact_dir,
            artifact_filename=f"xgb_meta_meta_{ts}.json",
        )
        return {"primary": primary_path, "meta": meta_path}


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------


def train_swing_model(
    X: np.ndarray,
    y: np.ndarray,
    feature_names: Optional[List[str]] = None,
    artifact_dir: str = ARTIFACT_DIR_DEFAULT,
) -> TrainingResult:
    """Train a SWING mode XGBoost classifier with conservative hyperparameters.

    This is the primary entry point for SWING baseline model training.
    Uses LOCKED_INITIAL_BASELINE conservative hyperparameters.

    Args:
        X: Feature matrix (n_samples, n_features).
        y: Label vector — string labels or integer labels.
        feature_names: Optional list of feature names.
        artifact_dir: Directory to save the model artifact.

    Returns:
        TrainingResult with trained model, artifact metadata, and metrics.
    """
    trainer = XGBoostTrainer(
        mode="SWING",
        random_seed=RANDOM_SEED,
        hyperparameters=SWING_DEFAULT_HYPERPARAMS,
    )
    result = trainer.train(X, y, feature_names=feature_names)

    # Generate IDs for artifact metadata
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    model_artifact_id = f"v7_alphaforge_xgb_swing_classifier_{ts}"
    training_run_id = f"tr_swing_baseline_{ts}"

    # Save model binary
    artifact_path = trainer.save_artifact(
        result,
        artifact_dir=artifact_dir,
        model_artifact_id=model_artifact_id,
    )

    # Build final metadata
    result.model_artifact = trainer.build_model_artifact_metadata(
        result,
        artifact_uri=f"file://{artifact_path.resolve()}",
        model_artifact_id=model_artifact_id,
        training_run_id=training_run_id,
        feature_set_id="swing_v1_features",
        label_dataset_id="swing_v1_labels",
        validation_report_id="VR-SWING-baseline-0000",
    )

    return result
