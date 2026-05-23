# V7 AlphaForge XGB Package

This package contains the requested AI summary and executable phase plan set for the V7-compatible alpha generation model.

## Main files

- `ai_summary__v7_alphaforge_xgb.md` — dense AI summary, V7-style.
- `phase_index.md` — phase overview.
- `model_name_recommendation.md` — recommended model name and artifact slugs.
- `phase_plans/` — 10 v2.5.1-style phase plans with Part 1-4 structure.
- `execution_contracts/` — extracted Part 3 JSON contracts per phase.
- `schemas/` — feature, label, and prediction schemas.
- `configs/` — default mode/model config proposal.
- `diagrams/` — Mermaid diagrams.
- `checklists/` — execution checklist.

## Phase count

10 phases: P0 through P9.

## Recommended model name

**V7 AlphaForge XGB** (`v7_alphaforge_xgb`)


## Review Hardening v1.1

This package includes a hardening addendum that closes four implementation risks: fold-scoped anomaly fitting, deterministic/regime override visibility, symbol encoding future-proofing, and SCALP interval authority. Read `hardening_review_fixes.md` before executing any phase.
