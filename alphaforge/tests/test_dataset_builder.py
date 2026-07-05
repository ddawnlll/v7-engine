"""Tests for alphaforge.dataset.builder — dataset assembly and fold generation."""

import pytest
from alphaforge.dataset.builder import (
    align_features_and_labels,
    build_dataset,
    get_feature_keys,
    AlphaForgeError,
)


def _feat(symbol: str = "BTCUSDT", ts: str = "2026-06-01T12:00:00Z", **extra) -> dict:
    return {"symbol": symbol, "timestamp": ts, "features": {"rsi_14": 55.0, "return_1": 0.01, **extra}}


def _label(symbol: str = "BTCUSDT", ts: str = "2026-06-01T12:00:00Z",
           validity: str = "VALID", action: str = "LONG_NOW", **extra) -> dict:
    return {
        "symbol": symbol, "timestamp": ts, "mode": "SWING",
        "label_validity": validity, "best_action_label": action,
        "long_R_net": 1.0, "short_R_net": -0.5,
        "simulation_family_version": "simfam-1.0.0",
        "label_interpretation_version": "labelint-1.0.0",
        **extra,
    }


class TestAlignFeaturesAndLabels:
    def test_basic_alignment(self):
        feats = [_feat()]
        labels = [_label()]
        merged = align_features_and_labels(feats, labels)
        assert len(merged) == 1
        assert merged[0]["features"]["rsi_14"] == 55.0
        assert merged[0]["label"]["best_action_label"] == "LONG_NOW"

    def test_unmatched_features_dropped(self):
        feats = [_feat(ts="2026-06-01T12:00:00Z"), _feat(ts="2026-06-02T12:00:00Z")]
        labels = [_label(ts="2026-06-01T12:00:00Z")]
        merged = align_features_and_labels(feats, labels)
        assert len(merged) == 1

    def test_duplicate_labels_raises(self):
        feats = [_feat()]
        labels = [_label(), _label()]
        with pytest.raises(AlphaForgeError, match="Duplicate"):
            align_features_and_labels(feats, labels)

    def test_sorts_by_timestamp(self):
        feats = [
            _feat(ts="2026-06-02T12:00:00Z"),
            _feat(ts="2026-06-01T12:00:00Z"),
        ]
        labels = [
            _label(ts="2026-06-01T12:00:00Z"),
            _label(ts="2026-06-02T12:00:00Z"),
        ]
        merged = align_features_and_labels(feats, labels)
        assert merged[0]["timestamp"] < merged[1]["timestamp"]

    def test_empty_inputs(self):
        assert align_features_and_labels([], []) == []

    def test_features_without_labels_return_empty(self):
        assert align_features_and_labels([_feat()], []) == []


class TestBuildDataset:
    def test_basic_build(self):
        rows = [
            {"symbol": "BTCUSDT", "timestamp": "2025-01-01T12:00:00Z", "mode": "SWING",
             "features": {}, "label": {"label_validity": "VALID", "best_action_label": "LONG_NOW"}},
            {"symbol": "ETHUSDT", "timestamp": "2025-03-01T12:00:00Z", "mode": "SWING",
             "features": {}, "label": {"label_validity": "VALID", "best_action_label": "SHORT_NOW"}},
            {"symbol": "SOLUSDT", "timestamp": "2025-06-01T12:00:00Z", "mode": "SWING",
             "features": {}, "label": {"label_validity": "VALID", "best_action_label": "NO_TRADE"}},
        ]
        result = build_dataset(rows, "SWING", fold_config={"min_train_days": 30, "train_window_days": 60, "val_window_days": 30})
        assert result["mode"] == "SWING"
        assert result["total_rows"] == 3
        assert result["status"] in ("ready", "insufficient_data")

    def test_excludes_ambiguous(self):
        rows = [
            {"symbol": "BTC", "timestamp": "2026-06-01T12:00:00Z", "mode": "SWING",
             "features": {}, "label": {"label_validity": "VALID", "best_action_label": "LONG_NOW"}},
            {"symbol": "ETH", "timestamp": "2026-06-15T12:00:00Z", "mode": "SWING",
             "features": {}, "label": {"label_validity": "AMBIGUOUS", "best_action_label": "AMBIGUOUS_STATE"}},
        ]
        result = build_dataset(rows, "SWING")
        assert result["total_rows"] == 1
        assert result["excluded_counts"]["ambiguous"] == 1

    def test_excludes_invalid(self):
        rows = [
            {"symbol": "BTC", "timestamp": "2026-06-01T12:00:00Z", "mode": "SWING",
             "features": {}, "label": {"label_validity": "INVALID", "best_action_label": "INVALID_OR_UNRESOLVED"}},
        ]
        result = build_dataset(rows, "SWING")
        assert result["total_rows"] == 0

    def test_insufficient_data(self):
        result = build_dataset([], "SWING")
        assert result["status"] == "insufficient_data"

    def test_fold_structure(self):
        # 18 months of data to ensure folds can form
        rows = [
            {"symbol": "BTC", "timestamp": f"2025-{m:02d}-01T12:00:00Z", "mode": "SWING",
             "features": {}, "label": {"label_validity": "VALID", "best_action_label": "LONG_NOW"}}
            for m in range(1, 13)
        ] + [
            {"symbol": "BTC", "timestamp": f"2026-{m:02d}-01T12:00:00Z", "mode": "SWING",
             "features": {}, "label": {"label_validity": "VALID", "best_action_label": "LONG_NOW"}}
            for m in range(1, 7)
        ]
        result = build_dataset(rows, "SWING", fold_config={"min_train_days": 90, "train_window_days": 180, "val_window_days": 60})
        if result["folds"]:
            fold = result["folds"][0]
            assert "train_start" in fold
            assert "fold_id" in fold


class TestGetFeatureKeys:
    def test_basic(self):
        rows = [
            {"features": {"rsi_14": 50, "atr": 100}},
            {"features": {"rsi_14": 55, "volume": 200}},
        ]
        assert get_feature_keys(rows) == ["atr", "rsi_14", "volume"]

    def test_empty(self):
        assert get_feature_keys([]) == []
