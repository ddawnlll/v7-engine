# AlphaForge Storage Policy

**Purpose:** Define what AlphaForge stores in the repo vs. external storage for data, models, and artifacts.

**Authority:** This is a repo-wide policy adopted by AlphaForge. LOCKED.

---

## Core Principle

**The repo stores schemas, fixtures, manifests, and reports. It does NOT store large datasets or model binaries.**

This ensures:
- Repo stays cloneable and manageable in size.
- Data and models can live on appropriate storage (local SSD, cloud buckets, etc.).
- Reproducibility is maintained through checksums and manifests, not through data duplication.

---

## What Goes IN the Repo

| Artifact Type | Location | Examples |
|--------------|----------|----------|
| JSON Schemas | `contracts/schemas/alphaforge/` | alpha_thesis.schema.json |
| JSON Fixtures | `contracts/fixtures/alphaforge/` | scalp_mode_research_report_minimal.json |
| Mapping Docs | `contracts/mappings/` | simulation_to_alphaforge.md |
| Authority Docs | `alphaforge/docs/` | discovery_authority.md |
| Report Templates | `alphaforge/docs/` | report_contracts.md |
| Phase Plans | `alphaforge/docs/` | phase_plan.md |
| Decision Logs | `alphaforge/docs/` | decision_log.md |
| Configuration | `alphaforge/docs/configs/` | Research parameter defaults |
| Source Code | `alphaforge/src/` | Implementation code (when started) |
| Tests | `alphaforge/tests/` | Unit/integration tests (when started) |

---

## What Stays OUTSIDE the Repo

| Artifact Type | Storage | Referenced By |
|--------------|---------|--------------|
| Raw market data | External drive / cloud bucket | storage_uri in manifest |
| Normalized data | External drive / cloud bucket | storage_uri in manifest |
| Feature matrices | External drive / cloud bucket | feature_set_id in FeatureSetSpec |
| Label datasets | External drive / cloud bucket | label_dataset_id in LabelDatasetSpec |
| Model binaries | External drive / cloud bucket / model registry | artifact_uri in ModelArtifact |
| Training checkpoints | External drive / cloud bucket | Run manifest |
| Large CSV/Parquet files | External drive / cloud bucket | Data manifest |
| Logs (verbose) | External drive / cloud bucket | Run manifest |

---

## External/Local Artifact Path Policy

### Local Development
```
~/v7-data/
├── raw/              # Raw market data
├── normalized/       # Normalized OHLCV
├── features/         # Feature datasets
├── labels/           # Label datasets
├── models/           # Model binaries
├── artifacts/        # Run artifacts
└── logs/             # Run logs
```

### URI Convention
- Local: `file:///home/user/v7-data/models/xgb_scalp_001.json`
- Cloud: `s3://v7-engine-artifacts/models/xgb_scalp_001.json`

---

## Checksum Requirements

Every external artifact referenced from the repo MUST have:
- A checksum (SHA-256 or equivalent) stored in the repo manifest.
- The checksum algorithm documented.
- A verification command or procedure documented.

### Reproducibility Metadata

Every derived artifact must record:
- Source data checksums.
- Code version (git commit hash).
- Configuration hash.
- Command used to generate the artifact.
- Environment information (Python version, key package versions).

This ensures that any artifact can be independently reproduced.

---

## Lineage Requirements

Every artifact must trace back to its sources:

```
ModelArtifact
    ← Training run (run_id, config_hash)
        ← FeatureDataset (feature_set_id, checksum)
            ← Normalized Market Data (storage_uri, checksum)
                ← Raw Market Data (source, checksum)
        ← LabelDataset (label_dataset_id, checksum)
            ← SimulationOutput (simulation_run_id)
                ← SimulationProfile (profile_id)
```

If any link in the chain is missing, the artifact's reproducibility is compromised and this must be flagged as a limitation.

---

## Related Docs

- [ai_summary.md](ai_summary.md)
- [data_contract.md](data_contract.md)
- [model_artifact_contract.md](model_artifact_contract.md)

## Related Contracts

- All schemas under [../../contracts/schemas/alphaforge/](../../contracts/schemas/alphaforge/) include lineage field requirements.

## Forbidden Assumptions

- Data is NOT committed to git just because it's convenient.
- Model binaries are NOT in the repo even if small.
- "It worked once" without checksums is NOT reproducibility.

## Open Holds

- Actual storage paths determined at implementation time.
- Cloud bucket configuration is an infrastructure decision, not a docs decision.
