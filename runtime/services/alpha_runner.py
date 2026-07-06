"""AlphaRunner: observe-only signal generator for Alpha #1.

This module is observe-only. It must not submit orders, call execution APIs,
or interact with PaperBroker. It loads a frozen XGBoost model, computes features,
applies a locked threshold, and logs signals — nothing more.

Issue #276: AlphaRunner shadow mode skeleton.
Coordination: #25 (Shadow Mode Implementation) will consume this module's
signal logging via its general shadow comparison/degradation machinery.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Locked Alpha #1 constants (from integration/tests/test_alpha1_artifact_guard)
# ---------------------------------------------------------------------------

ALPHA1_LOCKED_FEATURES: list[str] = [
    "bb_position",
    "ofi_N",
    "atr_expansion_N",
    "return_zscore_N",
    "vwap_mid_deviation_N",
    "trade_count_N",
    "multi_level_obi_N",
    "microprice_N",
    "log_return_1",
    "garman_klass_vol_N",
    "doji_N",
    "hammer_N",
    "volume_trend_N",
    "cusum_positive",
    "rsi_N",
    "parkinson_vol_N",
]

ALPHA1_LOCKED_THRESHOLD: float = 0.550


def _sha256_file(path: str | Path) -> str:
    """Compute SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


class AlphaRunner:
    """Observe-only signal generator for Alpha #1 XGBoost SCALP model.

    Lifecycle:
        1. __init__ — receives artifact path + expected hashes + threshold
        2. load_bundle — loads model from disk, verifies hash, returns bundle
        3. compute_features — stub, raises NotImplementedError until lib/alpha1_inference
        4. predict — applies threshold to model output, returns signal dict
        5. run_shadow — full pipeline entry point for shadow mode

    The class MUST NOT import or reference any order submission, broker,
    or execution module (paper_execution, execution_orchestrator, binance_client, etc.).
    """

    def __init__(
        self,
        artifact_path: str,
        expected_model_sha256: str,
        expected_manifest_sha256: str,
        expected_threshold: float,
    ) -> None:
        self._artifact_path = artifact_path
        self._expected_model_sha256 = expected_model_sha256
        self._expected_manifest_sha256 = expected_manifest_sha256
        self._expected_threshold = expected_threshold
        self._bundle: dict | None = None

    @property
    def is_loaded(self) -> bool:
        """Whether load_bundle() has been called successfully."""
        return self._bundle is not None

    @property
    def feature_names(self) -> list[str]:
        """The locked 16-feature set for Alpha #1."""
        return list(ALPHA1_LOCKED_FEATURES)

    @property
    def threshold(self) -> float:
        """Locked threshold for Alpha #1 signal classification."""
        return self._expected_threshold

    def load_bundle(self) -> dict:
        """Load model artifact, verify hashes, return bundle dict.

        The bundle dict is expected to contain at minimum:
          - "model": the fitted XGBoost model object
          - "manifest": metadata dict with feature names, threshold, version

        Hash verification:
          - Model file SHA-256 must match expected_model_sha256
          - Manifest file SHA-256 must match expected_manifest_sha256

        Raises:
            FileNotFoundError: if artifact_path does not exist
            ValueError: if hash verification fails
        """
        artifact = Path(self._artifact_path)
        if not artifact.exists():
            raise FileNotFoundError(f"Artifact not found: {artifact}")

        # In production, this would load the XGBoost model and manifest.
        # For now, the skeleton verifies hash logic and returns a placeholder.
        actual_hash = _sha256_file(artifact)
        if actual_hash != self._expected_model_sha256:
            raise ValueError(
                f"Model hash mismatch: expected {self._expected_model_sha256}, "
                f"got {actual_hash}"
            )

        self._bundle = {
            "model": None,  # placeholder — real XGBoost model goes here
            "manifest": {
                "feature_names": ALPHA1_LOCKED_FEATURES,
                "threshold": self._expected_threshold,
            },
        }
        logger.info("AlphaRunner bundle loaded from %s (hash verified)", artifact)
        return self._bundle

    def compute_features(self, candles: pd.DataFrame) -> dict[str, float]:
        """Compute the 16 locked features from candle data.

        STUB: raises NotImplementedError until lib/alpha1_inference is implemented
        (pending issue #273's design decision).

        Args:
            candles: DataFrame with OHLCV columns (open, high, low, close, volume).

        Returns:
            dict mapping feature name to float value.

        Raises:
            NotImplementedError: always (pending live feature engine).
        """
        raise NotImplementedError(
            "Pending lib/alpha1_inference implementation"
        )

    def predict(self, features: dict[str, float]) -> dict:
        """Apply threshold to model output and return signal dict.

        Args:
            features: dict mapping feature name to float value (16 features).

        Returns:
            dict with keys:
              - "signal": str — "LONG", "SHORT", or "NEUTRAL"
              - "confidence": float — model probability
              - "threshold": float — the locked threshold
              - "feature_names": list[str] — the locked 16 features
              - "raw_prediction": dict — raw model output (placeholder)

        Raises:
            RuntimeError: if bundle not loaded.
        """
        if not self.is_loaded:
            raise RuntimeError("Bundle not loaded. Call load_bundle() first.")

        # Placeholder: real XGBoost predict goes here.
        # Skeleton always returns NEUTRAL — no real model loaded yet.
        confidence = 0.0
        signal = "NEUTRAL"

        return {
            "signal": signal,
            "confidence": confidence,
            "threshold": self._expected_threshold,
            "feature_names": self.feature_names,
            "raw_prediction": {},
        }

    def run_shadow(
        self,
        candles: pd.DataFrame,
        *,
        timestamp: str,
        symbol: str,
        interval: str,
    ) -> dict | None:
        """Full shadow-mode pipeline: load → features → predict → log.

        Args:
            candles: DataFrame with OHLCV columns.
            timestamp: ISO-8601 timestamp of the signal evaluation.
            symbol: Trading pair symbol (e.g., "BTCUSDT").
            interval: Candle interval (e.g., "1m", "5m").

        Returns:
            dict with signal result, or None if features could not be computed.
        """
        if not self.is_loaded:
            self.load_bundle()

        try:
            features = self.compute_features(candles)
        except NotImplementedError:
            logger.warning(
                "Shadow mode skipped: feature engine not yet implemented"
            )
            return None

        result = self.predict(features)
        result["timestamp"] = timestamp
        result["symbol"] = symbol
        result["interval"] = interval

        logger.info(
            "Shadow signal: %s %s %s confidence=%.4f",
            symbol,
            interval,
            result["signal"],
            result["confidence"],
        )
        return result
