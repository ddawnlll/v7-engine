# AlphaForge Model Artifact Contract

**Purpose:** Define the ModelArtifact and CalibrationCandidate formats — what AlphaForge produces from training and how V7 receives model metadata.

**Authority:** AlphaForge owns model artifact specification. V7 owns model acceptance for policy use. This document is LOCKED.

---

## ModelArtifact

**Schema:** [model_artifact.schema.json](../../contracts/schemas/alphaforge/model_artifact.schema.json)

### Required Fields

| Field | Type | Description |
|-------|------|-------------|
| schema_version | string | Schema version for compatibility tracking |
| model_artifact_id | string | Unique model artifact identifier |
| model_family | string | Model family/type (e.g., "xgboost", "lightgbm", "ensemble") |
| mode | enum | SCALP, AGGRESSIVE_SCALP, SWING |
| training_run_id | string | ResearchRunManifest run_id that produced this artifact |
| feature_set_id | string | FeatureSetSpec used for training |
| label_dataset_id | string | LabelDatasetSpec used for training |
| validation_report_id | string | Associated ValidationReport ID |
| artifact_uri | string | URI to model binary (NOT stored in repo) |
| checksum | string | Content hash of the model binary |
| created_at | string (ISO 8601) | Artifact creation timestamp |
| limitations | array of strings | Known limitations of this model |

### Optional Fields

| Field | Type | Description |
|-------|------|-------------|
| hyperparameters | object | Training hyperparameters |
| feature_importance | object | Feature importance scores |
| training_metrics | object | Training/validation metrics |
| model_size_bytes | integer | Size of model binary |
| framework_version | string | ML framework version used |
| training_duration_seconds | number | Training wall-clock time |
| environment_hash | string | Hash of training environment for reproducibility |

---

## Artifact Storage Policy

**NOT in repo:** Model binaries, serialized models, large checkpoint files.
**In repo:** ModelArtifact metadata records.

The `artifact_uri` field points to external/local storage. Valid URIs:
- `file:///path/to/models/...` (local development)
- `s3://bucket/path/...` (cloud storage)
- `gs://bucket/path/...` (GCP storage)

The `checksum` field ensures integrity: if the binary at artifact_uri doesn't match the checksum, the artifact is invalid.

---

## CalibrationCandidate

**Schema:** [calibration_candidate.schema.json](../../contracts/schemas/alphaforge/calibration_candidate.schema.json)

### Purpose
Model probability/confidence outputs are rarely well-calibrated out of the box. The CalibrationCandidate documents how the model's outputs were calibrated and whether the calibration is usable.

### Required Fields

| Field | Type | Description |
|-------|------|-------------|
| schema_version | string | Schema version |
| calibration_candidate_id | string | Unique identifier |
| mode | enum | SCALP, AGGRESSIVE_SCALP, SWING |
| model_artifact_id | string | Associated ModelArtifact |
| calibration_method | string | Method used (e.g., "isotonic", "platt", "beta", "none") |
| calibration_metrics | object | Calibration quality metrics |
| confidence_bins | array | Per-bin calibration assessment |
| limitations | array of strings | Known calibration limitations |
| status | enum | CALIBRATED, UNCALIBRATED, UNRELIABLE |

### Calibration Metrics

| Metric | Description |
|--------|-------------|
| expected_calibration_error | ECE score (lower is better) |
| maximum_calibration_error | MCE score |
| brier_score | Brier score (if probability outputs) |
| reliability_curve | Binned reliability data |
| sharpness | How concentrated predictions are |

### Confidence Bins

Each bin reports:
- Bin range (e.g., 0.0-0.1, 0.1-0.2, ...)
- Number of samples in bin
- Actual outcome rate (empirical probability)
- Bin deviation (predicted - actual)

### Usability Criteria

| Status | Criteria |
|--------|----------|
| CALIBRATED | ECE < 0.05, all bins within tolerance |
| UNCALIBRATED | ECE ≥ 0.05, calibration needed |
| UNRELIABLE | ECE > 0.10, calibration failed or not possible |

---

## Model Artifact NOT Executable by V7

Important: V7 does NOT execute the model directly. V7 receives:
1. ModelArtifact metadata (this contract)
2. CalibrationCandidate (calibration assessment)
3. ModeResearchReport (validation evidence)
4. V7HandoffPackage (handoff assembly)

V7 decides whether to ACCEPT or REJECT based on the evidence package. V7 may choose to load the model for shadow/promotion evaluation, but this is a V7 decision, not an AlphaForge command.

---

## Related Docs

- [ai_summary.md](ai_summary.md)
- [alpha_thesis_lifecycle.md](alpha_thesis_lifecycle.md)
- [report_contracts.md](report_contracts.md)
- [validation_contract.md](validation_contract.md)
- [handoff_to_v7.md](handoff_to_v7.md)
- [storage_policy.md](storage_policy.md)

## Related Contracts

- [../../contracts/schemas/alphaforge/model_artifact.schema.json](../../contracts/schemas/alphaforge/model_artifact.schema.json)
- [../../contracts/schemas/alphaforge/calibration_candidate.schema.json](../../contracts/schemas/alphaforge/calibration_candidate.schema.json)

## Forbidden Assumptions

- Model binary is NOT stored in repo.
- Model is NOT executable by V7 without V7's explicit acceptance.
- Training metrics alone do NOT warrant V7 handoff.
- Calibration is required, not optional.

## Open Holds

- Model family selection (XGBoost, LightGBM, etc.) determined during implementation.
- Calibration method selection depends on model family.
