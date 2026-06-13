# Self-Learning Runtime

## Role Boundary

`v4` remains the signal engine. It owns:

- regime interpretation
- signal generation
- factor scoring
- base probability and confidence
- entry, stop, and target proposals

The self-learning layer is an additive decision-correction layer. It owns:

- correcting probability from historical truth
- recommending safe action adjustments from learned context
- retrieving similar historical memory from external storage
- learning which contexts produce wins vs false positives

It does not replace direction logic. Early versions are explicitly read-only with respect to trade direction. The original `v4` signal remains the source signal for any self-learning correction.

## Production Scope

The first production scope is intentionally narrow:

- `SWING` only
- binary outcome prediction first
- action adjustment second

If the self-learning layer is unavailable, `v4` continues unchanged.

## Decision Order

Analyzer flow order:

1. Base analyzer output from `v4`
2. Existing adjustment layers from earlier phases
3. Self-learning correction layer
4. Final acceptance or rejection

Every self-learning result remains attributable to the original `v4` signal through the embedded comparison and attribution payload.

## Storage Roles

- PostgreSQL: transactional truth for signals, orders, failures, audit trails, and structured trade memories
- LanceDB: preferred external nearest-neighbor memory store
- Parquet: preferred offline dataset and evaluation slice format
- MLflow: preferred model lifecycle and promotion history store

Current local runtime keeps the same role split, with JSONL/CSV/JSON fallbacks when preferred libraries are not installed. All artifacts remain local-only and reproducible.

## Backup And Restore

Back up:

- `data/memory/lancedb/`
- `data/datasets/self_learning/`
- `data/mlruns/`
- `data/models/self_learning/`

Restore order:

1. PostgreSQL operational data
2. model registry and artifacts
3. datasets and evaluation snapshots
4. external memory, or rebuild it deterministically from PostgreSQL plus dataset artifacts

## Retention

- raw training sets: latest 20 or 180 days
- model checkpoints: latest 10 or 365 days
- memory embeddings: compact after 90 days, keep enough to rebuild
- evaluation snapshots: latest 30 or 365 days
