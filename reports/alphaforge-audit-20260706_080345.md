# AlphaForge Nightshift — Dataset Audit

**Date:** 2026-07-06 08:03:45
**Phase:** Dataset Audit (audit)
**Attempt:** 1

## Output

```
   status: "LOCKABLE_WITH_HOLDS"
+    evidence: "MATICUSDT 50.33% NaN (delisted), BTCUSDT 21.81% NaN (gap), BNB/ETH/SOL ~19.5% NaN (early data), SUI 9.84%, ARB 6.55%"
+    holds:
+      - "Document NaN handling strategy for cache panels — confirm XGBoost built-in missing value handling or explicit masking"
+      - "BTCUSDT cache NaN% correlates with raw data gap — fix raw data to reduce cache NaN"
+  - id: "AUDIT_LOOKAHEAD_RISK"
+    description: "Simulation outcome columns (net_R, gross_R, mfe_R, mae_R, exit_reason, hold_duration) in candidates datasets are forward-looking by nature"
+    status: "LOCKED"
+    evidence: "These are simulation outputs stored as labels/targets. Column names contain no suspicious lookahead patterns. This is correct usage."
+    release_condition: "N/A — storage as labels is correct. Training code must be verified separately."
+
+remaining_holds:
+  - "BTCUSDT deduplication — remove 4 duplicate rows"
+  - "BTCUSDT 59-day gap — backfill or document acceptable gap"
+  - "Cache panel NaN documentation — ensure downstream code handles NaN correctly"
+  - "Training pipeline code audit — verify outcome columns not used as features"
+
+safe_next_step:
+  - "Run df.drop_duplicates(subset=['timestamp']) on BTCUSDT_1h_full.parquet to fix duplicates"
+  - "Check if BTC data gap is acceptable for training splits that don't span Q1 2024"
+  - "Add NaN handling documentation to cache factor panel pipeline"
+
+commands_run:
+  - "PYTHONPATH=. python3 -c 'pd.read_parquet(\"data/candidates/outcomes_v1.parquet\").info()'"
+  - "PYTHONPATH=. python3 -c 'pd.read_parquet(\"data/raw/BTCUSDT/BTCUSDT_1h_full.parquet\")' # gap + duplicate analysis"
+  - "PYTHONPATH=. python3 -c 'pd.read_parquet(\"cache/factor_sprint/panel_d8c8d55e3b8b107e_close.parquet\")' # NaN analysis"
+  - "Dedup analysis: BTC gap=59d, BTC missing=1438h, duplicates=4, NaN totals per panel=43989"
+  - "Cross-symbol comparison: ETH/BNB/SOL clean (29928 rows, no gaps, no dupes)"
+
+evidence:
+  - "BTCUSDT raw: 28,492 rows vs 29,928 expected (1,438 missing)"
+  - "BTCUSDT duplicate timestamps: 1704067200000 (x2), 1704153600000 (x2) — identical OHLCV in each pair"
+  - "BTCUSDT gap after dedup: 2024-01-02 00:00:00 to 2024-03-01 00:00:00 (59 days)"
+  - "Cache NaN per panel: 43,989 total across 7 symbols (MATIC 15062, BTC 6528, BNB 5832, ETH 5832, SOL 5832, SUI 2944, ARB 1959)"
+  - "Candidates dataset (outcomes_v1): 10,000 rows, 0 NaN, 0 Inf, 0 gaps, contiguous 1h intervals"
+  - "ETH/BNB/SOL raw: 29,928 rows, 0 NaN, 0 Inf, 0 duplicates, 0 gaps — full clean"
… omitted 1 diff line(s) across 1 additional file(s)/section(s)
Both reports validated — YAML parses clean, markdown is well-formed.

**Verification status: PASS** (documentation-only change — no source code, no tests, no build artifacts affected.)

ACCP-YAML confirms: 11 datasets audited, verdict NEEDS_REPAIR, 4 decisions locked, 4 remaining holds documented with release conditions.


session_id: 20260706_080002_3dbefd

```
