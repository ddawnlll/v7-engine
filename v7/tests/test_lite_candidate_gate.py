"""Tests for V7-Lite immutable candidate admission."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from v7.lite.candidate_gate import (
    CandidateSignal,
    ManifestValidationError,
    admit_and_execute_shadow,
    evaluate_frozen_candidate,
    load_frozen_candidate_manifest,
    parse_frozen_candidate_manifest,
    apply_shadow_portfolio_controls,
)
from v7.shadow_mode import ShadowModeManager
from v7.lite.preregistration import (
    PreregistrationValidationError,
    frozen_holdout_cli_arguments,
    parse_frozen_holdout_preregistration,
)


def _manifest() -> dict:
    return {
        "manifest_version": "v7-lite-candidate-1.0",
        "candidate_id": "af-volume-no-rank-001",
        "mode": "SCALP",
        "model_scope": "scalp_volume_v1",
        "deployment_stage": "SHADOW",
        "artifact": {
            "artifact_id": "af-artifact-001",
            "sha256": "a" * 64,
            "feature_schema_id": "volume-no-rank-v1",
        },
        "scope": {
            "supported_symbols": ["BTCUSDT", "ETHUSDT"],
            "valid_from": "2026-07-01T00:00:00Z",
            "valid_until": "2026-08-01T00:00:00Z",
        },
        "evidence": {
            "gate_statuses": {f"G{index}": "PASS" for index in range(7)},
        },
    }


def _admit(manifest, **overrides):
    values = {
        "symbol": "BTCUSDT",
        "mode": "SCALP",
        "model_scope": "scalp_volume_v1",
        "decision_timestamp": datetime(2026, 7, 15, tzinfo=timezone.utc),
        "artifact_sha256": "a" * 64,
        "feature_schema_id": "volume-no-rank-v1",
    }
    values.update(overrides)
    return evaluate_frozen_candidate(manifest, **values)


def test_valid_frozen_manifest_admits_shadow_evaluation():
    manifest = parse_frozen_candidate_manifest(_manifest())
    admission = _admit(manifest)
    assert admission.allowed is True
    assert admission.reason_codes == ()


@pytest.mark.parametrize(
    ("override", "reason"),
    [
        ({"symbol": "SOLUSDT"}, "unsupported_symbol"),
        ({"mode": "SWING"}, "mode_mismatch"),
        ({"model_scope": "scalp_other_v1"}, "model_scope_mismatch"),
        ({"artifact_sha256": "b" * 64}, "artifact_checksum_mismatch"),
        ({"feature_schema_id": "wrong"}, "feature_schema_mismatch"),
        ({"deployment_stage": "PAPER"}, "deployment_stage_not_shadow"),
    ],
)
def test_manifest_gate_rejects_scope_or_lineage_drift(override, reason):
    manifest = parse_frozen_candidate_manifest(_manifest())
    admission = _admit(manifest, **override)
    assert admission.allowed is False
    assert reason in admission.reason_codes


def test_manifest_gate_rejects_missing_pre_shadow_evidence():
    data = _manifest()
    data["evidence"]["gate_statuses"]["G3"] = "HOLD"
    admission = _admit(parse_frozen_candidate_manifest(data))
    assert admission.allowed is False
    assert "pre_shadow_gate_not_passed:G3" in admission.reason_codes


def test_manifest_parser_requires_shadow_only_stage():
    data = _manifest()
    data["deployment_stage"] = "PAPER"
    with pytest.raises(ManifestValidationError, match="SHADOW"):
        parse_frozen_candidate_manifest(data)


def test_manifest_parser_rejects_scope_mismatch():
    data = _manifest()
    data["model_scope"] = "swing_volume_v1"
    with pytest.raises(ManifestValidationError, match="does not match mode"):
        parse_frozen_candidate_manifest(data)


def test_manifest_loader_reads_json(tmp_path):
    path = tmp_path / "candidate.json"
    path.write_text(json.dumps(_manifest()), encoding="utf-8")
    manifest = load_frozen_candidate_manifest(path)
    assert manifest.candidate_id == "af-volume-no-rank-001"
    assert manifest.supported_symbols == frozenset({"BTCUSDT", "ETHUSDT"})


def test_admitted_signals_still_go_through_v7_portfolio_caps():
    signals = [
        CandidateSignal("a", "SOLUSDT", "LONG", 0.04, 0.8, 10.0),
        CandidateSignal("b", "ADAUSDT", "LONG", 0.03, 0.9, 10.0),
    ]
    result = apply_shadow_portfolio_controls(signals, {}, {"max_cluster_exposure_pct": 10.0})
    assert [item["symbol"] for item in result.ranked] == ["SOLUSDT"]
    assert result.suppressed == ["ADAUSDT"]


def test_hold_candidate_cannot_create_a_shadow_record():
    data = _manifest()
    data["evidence"]["gate_statuses"]["G4"] = "HOLD"
    manager = ShadowModeManager()

    dispatch = admit_and_execute_shadow(
        parse_frozen_candidate_manifest(data),
        shadow_manager=manager,
        proposed_decision={"decision": "LONG", "confidence": 0.8},
        symbol="BTCUSDT",
        mode="SCALP",
        model_scope="scalp_volume_v1",
        decision_timestamp=datetime(2026, 7, 15, tzinfo=timezone.utc),
        artifact_sha256="a" * 64,
        feature_schema_id="volume-no-rank-v1",
    )

    assert dispatch.admission.allowed is False
    assert dispatch.shadow_record is None
    assert manager.get_records("scalp_volume_v1") == []


def test_admitted_candidate_creates_a_shadow_record_after_boundary():
    manager = ShadowModeManager()
    dispatch = admit_and_execute_shadow(
        parse_frozen_candidate_manifest(_manifest()),
        shadow_manager=manager,
        proposed_decision={"decision": "LONG", "confidence": 0.8},
        symbol="BTCUSDT",
        mode="SCALP",
        model_scope="scalp_volume_v1",
        decision_timestamp=datetime(2026, 7, 15, tzinfo=timezone.utc),
        artifact_sha256="a" * 64,
        feature_schema_id="volume-no-rank-v1",
    )

    assert dispatch.admission.allowed is True
    assert dispatch.shadow_record is not None
    assert len(manager.get_records("scalp_volume_v1")) == 1


def test_preregistration_freezes_the_fresh_holdout_cli_contract():
    spec = parse_frozen_holdout_preregistration({
        "preregistration_version": "v7-lite-preregistered-holdout-1.0",
        "candidate_id": "candidate-1",
        "cutoff": "2026-07-12T22:00:00Z",
        "mode": "SCALP",
        "symbols": ["BTCUSDT", "ETHUSDT"],
        "features": "volume",
        "normalization": "none",
        "confidence_threshold": 0.5,
        "position_size_pct": 5.0,
        "portfolio_config": {},
        "output_trace_name": "once.jsonl",
    })
    args = frozen_holdout_cli_arguments(spec, data_dir="/data", output_dir="/out")
    assert args == [
        "--mode", "SCALP", "--symbols", "BTCUSDT,ETHUSDT", "--features", "volume",
        "--normalization", "none", "--data-dir", "/data", "--holdout-cutoff",
        "2026-07-12T22:00:00+00:00", "--frozen-confidence-threshold", "0.5",
        "--frozen-holdout-trace", "/out/once.jsonl",
    ]


def test_preregistration_rejects_feature_or_normalization_drift():
    data = {
        "preregistration_version": "v7-lite-preregistered-holdout-1.0",
        "candidate_id": "candidate-1", "cutoff": "2026-07-12T22:00:00Z", "mode": "SCALP",
        "symbols": ["BTCUSDT"], "features": "volume", "normalization": "none",
        "confidence_threshold": 0.5, "position_size_pct": 5.0, "portfolio_config": {},
        "output_trace_name": "once.jsonl",
    }
    data["features"] = "volume,regime"
    with pytest.raises(PreregistrationValidationError, match="features"):
        parse_frozen_holdout_preregistration(data)
