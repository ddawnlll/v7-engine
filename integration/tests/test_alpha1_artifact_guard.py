"""Guard test: Alpha #1 frozen artifact contract + metadata invariants."""
import json
import pathlib

import pytest

REGISTRY_PATH = pathlib.Path("contracts/registry.json")

ALPHA1_LOCKED_FEATURES = [
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

ALPHA1_THRESHOLD = 0.550


@pytest.fixture
def registry():
    with open(REGISTRY_PATH) as f:
        return json.load(f)


def _find_entry(registry, name):
    for c in registry["contracts"]:
        if c["object_name"] == name:
            return c
    return None


class TestRegistryEntry:
    def test_entry_exists(self, registry):
        entry = _find_entry(registry, "Alpha1FrozenArtifact")
        assert entry is not None, "Alpha1FrozenArtifact missing from contracts/registry.json"

    def test_required_fields(self, registry):
        entry = _find_entry(registry, "Alpha1FrozenArtifact")
        assert entry is not None
        for field in ["owner_domain", "version", "description", "producers", "consumers"]:
            assert field in entry, f"Missing required field: {field}"

    def test_owner_domain(self, registry):
        entry = _find_entry(registry, "Alpha1FrozenArtifact")
        assert entry["owner_domain"] == "alphaforge"

    def test_producer_consumer(self, registry):
        entry = _find_entry(registry, "Alpha1FrozenArtifact")
        assert "alphaforge" in entry["producers"]
        assert "runtime" in entry["consumers"]
        assert "alphaforge" in entry["consumers"]


class TestFrozenMetadata:
    def test_feature_count(self, registry):
        assert len(ALPHA1_LOCKED_FEATURES) == 16

    def test_feature_set_sorted(self, registry):
        sorted_features = sorted(ALPHA1_LOCKED_FEATURES)
        expected = sorted(
            [
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
        )
        assert sorted_features == expected

    def test_threshold(self, registry):
        assert ALPHA1_THRESHOLD == 0.550
