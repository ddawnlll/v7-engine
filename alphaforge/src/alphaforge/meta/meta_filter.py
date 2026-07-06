"""MetaFilter — inference-time filtering of primary predictions.

Provides a stateless function and a convenience class for filtering
primary model predictions based on meta-model confidence scores.
"""

from __future__ import annotations

from typing import Optional, Tuple

import numpy as np

from alphaforge.meta.config import META_CONFIDENCE_DEFAULT_THRESHOLD


class MetaFilter:
    """Threshold-based filter for primary model predictions.

    Takes a raw primary prediction and a meta-model confidence score,
    returns whether to trade and the confidence level.

    Usage:
        filter = MetaFilter(threshold=0.5)
        trade, confidence = filter(primary_pred=1, meta_confidence=0.85)
    """

    def __init__(self, threshold: float = META_CONFIDENCE_DEFAULT_THRESHOLD):
        if not 0 <= threshold <= 1:
            raise ValueError(f"threshold must be in [0, 1], got {threshold}")
        self._threshold = threshold

    @property
    def threshold(self) -> float:
        return self._threshold

    def __call__(
        self,
        primary_pred: int,
        meta_confidence: float,
    ) -> Tuple[bool, float]:
        """Filter a single prediction.

        Args:
            primary_pred: Primary model prediction (0=LONG, 1=SHORT, 2=NO_TRADE).
            meta_confidence: Meta-model confidence in [0, 1].

        Returns:
            (trade: bool, confidence: float).
            trade=True when meta_confidence > threshold or primary is NO_TRADE.
            confidence equals meta_confidence for accepted trades, 0 otherwise.
        """
        if primary_pred == 2:
            return True, meta_confidence

        trade = meta_confidence > self._threshold
        confidence = meta_confidence if trade else 0.0
        return trade, confidence


def meta_filter_predictions(
    primary_preds: np.ndarray,
    meta_confidences: np.ndarray,
    threshold: float = META_CONFIDENCE_DEFAULT_THRESHOLD,
) -> Tuple[np.ndarray, np.ndarray]:
    """Filter an array of primary predictions by meta confidence.

    Args:
        primary_preds: Primary predictions, shape (n,). 0=LONG, 1=SHORT, 2=NO_TRADE.
        meta_confidences: Meta confidence scores, shape (n,).
        threshold: Confidence threshold in [0, 1]. Default 0.5.

    Returns:
        (trades: np.ndarray[bool], final_preds: np.ndarray)
        trades[i] = True if prediction i should be executed.
        final_preds[i] = primary_preds[i] if accepted, else 2 (NO_TRADE).
    """
    no_trade_mask = primary_preds == 2
    above_threshold = meta_confidences > threshold

    trades = np.where(no_trade_mask, True, above_threshold)
    final_preds = np.where(trades, primary_preds, 2)

    return trades, final_preds
