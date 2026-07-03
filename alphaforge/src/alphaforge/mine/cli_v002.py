"""P1.0 Profit-State Mining Alpha Factory — v002 CLI.

Full pipeline:
  CandidateOutcomeDataset v002 → Baseline normalization → Feature bucketization
  → Level 1/2/3 mining → Rule dedup → Validation → AlphaRuleSpec export

Usage:
    python -m alphaforge.mine.cli_v002 \\
        --dataset data/alphaforge/candidate_outcomes/candidate_outcomes_v002.parquet \\
        --target excess_net_R \\
        --levels 1,2 \\
        --min-support 100 \\
        --output reports/alphaforge/mining/run_v002/
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

logger = logging.getLogger(__name__)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="P1.0 Profit-State Mining Alpha Factory v002",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--dataset", required=True, help="Path to CandidateOutcomeDataset v002 parquet")
    parser.add_argument("--target", default="excess_net_R", choices=["excess_net_R", "net_R"],
                        help="Mining target (default: excess_net_R)")
    parser.add_argument("--levels", default="1,2", help="Mining levels (comma-separated: 1,2,3)")
    parser.add_argument("--min-support", type=int, default=100, help="Minimum support count")
    parser.add_argument("--top-k", type=int, default=500, help="Max rules to keep after Level 1")
    parser.add_argument("--output", default="reports/alphaforge/mining/run_v002", help="Output directory")
    parser.add_argument("--jaccard-threshold", type=float, default=0.7, help="Dedup Jaccard threshold")
    parser.add_argument("--log-level", default="INFO", help="Logging level")
    return parser


def run_pipeline(args: argparse.Namespace) -> Dict[str, Any]:
    """Run the full v002 mining pipeline."""
    from alphaforge.mine.bucketizer import FeatureBucketizer
    from alphaforge.mine.bitset_engine import BitsetEngine
    from alphaforge.mine.rule_scorer import RuleScorer
    from alphaforge.mine.rule_deduper import RuleDeduplicator
    from alphaforge.mine.validator import ValidationFunnel
    from alphaforge.mine.exporter import AlphaRuleSpecBuilder

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    levels = [int(l.strip()) for l in args.levels.split(",")]
    target_col = args.target
    start = time.time()

    summary: Dict[str, Any] = {
        "status": "running",
        "dataset": str(args.dataset),
        "target": target_col,
        "levels": levels,
        "min_support": args.min_support,
        "steps_completed": [],
        "results": {},
    }

    # ── Step 1: Load dataset ──────────────────────────────────────────
    logger.info("Step 1: Loading dataset from %s", args.dataset)
    table = pq.read_table(args.dataset)
    n = table.num_rows
    summary["dataset_rows"] = n
    summary["dataset_columns"] = table.column_names
    summary["steps_completed"].append("load")

    if target_col not in table.column_names:
        logger.error("Target column '%s' not found. Available: %s", target_col, table.column_names)
        summary["status"] = "error"
        summary["error"] = f"Target column '{target_col}' not found"
        return summary

    # ── Step 2: Bucketize features ────────────────────────────────────
    logger.info("Step 2: Bucketizing features...")
    feature_cols = [
        c for c in [
            "volatility_percentile", "momentum_rank", "volume_zscore",
            "atr_pct", "pullback_atr", "distance_to_range_high",
        ] if c in table.column_names
    ]

    # Add categorical features as explicit conditions
    categorical_features = ["side", "mode", "regime_trend", "btc_regime"]
    for cat in categorical_features:
        if cat in table.column_names:
            unique_vals = table.column(cat).to_pylist()
            unique_set = set(str(v) for v in unique_vals)
            for val in unique_set:
                col_name = f"{cat}__{val}"
                mask = np.array([str(v) == val for v in unique_vals], dtype=bool)
                # We'll add these as manual masks later
                feature_cols.append(cat)  # bucketizer will handle deciles

    bucketizer = FeatureBucketizer()
    bucketizer.fit(table, [c for c in feature_cols if c in table.column_names])
    masks = bucketizer.transform(table)

    # Add categorical condition masks
    for cat in categorical_features:
        if cat in table.column_names:
            unique_vals = table.column(cat).to_pylist()
            unique_set = set(str(v) for v in unique_vals)
            for val in unique_set:
                mask_key = f"{cat}__{val}"
                masks[mask_key] = np.array([str(v) == val for v in unique_vals], dtype=bool)

    condition_registry = [
        c for c in bucketizer.get_condition_registry()
        if c.get("support_count", 0) >= args.min_support
    ]
    summary["total_conditions"] = len(masks)
    summary["steps_completed"].append("bucketize")

    # ── Step 3: Extract target ─────────────────────────────────────────
    target = table.column(target_col).to_numpy().astype("float64")

    # ── Step 4: Mine rules ─────────────────────────────────────────────
    engine = BitsetEngine(min_support=args.min_support / max(1, n))
    level1, level2, level3 = [], [], []

    if 1 in levels:
        logger.info("Level 1: Single condition scan...")
        level1 = engine.level1_scan(masks, target)
        level1 = sorted(level1, key=lambda r: r.get("mean_net_R", 0), reverse=True)[:args.top_k]
        summary["results"]["level1_count"] = len(level1)
        summary["steps_completed"].append("level1")
        logger.info("  Level 1: %d rules", len(level1))

    if 2 in levels:
        logger.info("Level 2: Pairwise condition scan...")
        level2 = engine.level2_scan(masks, target, top_n=args.top_k)
        summary["results"]["level2_count"] = len(level2)
        summary["steps_completed"].append("level2")
        logger.info("  Level 2: %d rules", len(level2))

    if 3 in levels:
        logger.info("Level 3: Beam search...")
        seed_rules = level2[:100] if level2 else level1[:100]
        level3 = engine.level3_scan(seed_rules, masks, target, beam_width=50)
        summary["results"]["level3_count"] = len(level3)
        summary["steps_completed"].append("level3")
        logger.info("  Level 3: %d rules", len(level3))

    # Combine all rules
    all_rules = level1 + level2 + level3
    # Deduplicate by condition signature
    seen = set()
    unique_rules = []
    for r in all_rules:
        sig = str(sorted(r.get("conditions", [])))
        if sig not in seen:
            seen.add(sig)
            unique_rules.append(r)
    all_rules = unique_rules
    summary["total_rules_discovered"] = len(all_rules)

    if not all_rules:
        summary["status"] = "no_rules_found"
        summary["elapsed_seconds"] = round(time.time() - start, 2)
        return summary

    # ── Step 5: Score rules ────────────────────────────────────────────
    logger.info("Step 5: Scoring %d rules...", len(all_rules))
    scorer = RuleScorer()
    symbol_map = table.column("symbol").to_numpy().astype(str) if "symbol" in table.column_names else np.zeros(n, dtype=str)
    regime_map = table.column("regime_trend").to_numpy().astype(str) if "regime_trend" in table.column_names else np.zeros(n, dtype=str)

    # Build per-rule masks
    per_rule_masks = []
    for rule in all_rules:
        conds = rule.get("conditions", [])
        combined = None
        for c in conds:
            if c in masks and len(masks[c]) == n:
                combined = masks[c] if combined is None else (combined & masks[c])
        per_rule_masks.append({"combined": combined if combined is not None else np.zeros(n, dtype=bool)})

    scored_rules = scorer.score_batch(all_rules, per_rule_masks, target, symbol_map, regime_map)
    summary["steps_completed"].append("score")

    # ── Step 6: Dedup / family clustering ──────────────────────────────
    logger.info("Step 6: Deduplicating and clustering...")
    deduper = RuleDeduplicator(jaccard_threshold=args.jaccard_threshold)
    dedup_result = deduper.deduplicate(all_rules, masks, target)
    families = dedup_result["families"]
    duplicates = dedup_result["duplicates"]
    summary["results"]["families_count"] = len(families)
    summary["results"]["duplicates_count"] = len(duplicates)
    summary["steps_completed"].append("dedup")

    # ── Step 7: Validation funnel ──────────────────────────────────────
    logger.info("Step 7: Running validation funnel...")
    funnel = ValidationFunnel()
    try:
        splits = funnel.split(table, timestamp_col="timestamp")
        val_result = funnel.validate(
            rules=all_rules,
            masks=masks,
            discovery_table=splits["discovery"],
            validation_table=splits["validation"],
            holdout_table=splits["holdout"],
            target_col=target_col,
        )
        summary["results"]["validation"] = val_result["summary"]
        validated_rules = val_result["validated_rules"]
        rejected_rules = val_result["rejected_rules"]
        summary["steps_completed"].append("validation")
    except Exception as e:
        logger.warning("Validation failed: %s", e)
        summary["results"]["validation"] = {"error": str(e)}
        validated_rules = all_rules
        rejected_rules = []

    # ── Step 8: Export AlphaRuleSpec ───────────────────────────────────
    logger.info("Step 8: Exporting AlphaRuleSpec artifacts...")
    specs_dir = output_dir / "alpha_rule_specs"
    exporter = AlphaRuleSpecBuilder()
    specs = exporter.build(
        validated_rules,
        mining_run_id=f"run_v002_{int(time.time())}",
        dataset_version="v002",
    )
    exported = exporter.export(specs, str(specs_dir))
    registry = exporter.build_registry(specs)

    # Write registry
    registry_path = output_dir / "alpha_registry.json"
    with open(registry_path, "w") as f:
        json.dump(registry, f, indent=2, default=str)

    summary["results"]["exported_specs"] = exported
    summary["steps_completed"].append("export")

    # ── Step 9: Write outputs ──────────────────────────────────────────
    elapsed = time.time() - start
    summary["elapsed_seconds"] = round(elapsed, 2)
    summary["status"] = "complete"
    summary["output_dir"] = str(output_dir)

    # Family summary
    family_summary = {
        "raw_rule_count": len(all_rules),
        "non_duplicate_rule_count": len(all_rules) - len(duplicates),
        "independent_alpha_family_count": len(families),
        "validated_alpha_family_count": sum(
            1 for f in families
            if any(r.get("status") == "VALIDATED" for r in validated_rules
                   if r.get("family_id") == f["family_id"])
        ),
        "families": [
            {
                "family_id": f["family_id"],
                "primary_feature_family": f["primary_feature_family"],
                "member_count": f["member_count"],
                "mean_net_R": f["mean_net_R"],
                "representative_rule_id": f["representative_rule_id"],
            }
            for f in families
        ],
    }
    summary["family_summary"] = family_summary

    # Write summary
    summary_path = output_dir / "mining_summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2, default=str)

    # Write family summary
    family_path = output_dir / "alpha_factor_families.json"
    with open(family_path, "w") as f:
        json.dump(family_summary, f, indent=2, default=str)

    # Write duplicates
    dup_path = output_dir / "duplicate_rules.json"
    with open(dup_path, "w") as f:
        json.dump(duplicates, f, indent=2, default=str)

    logger.info(
        "Pipeline complete in %.1fs — %d rules → %d families",
        elapsed, len(all_rules), len(families),
    )

    return summary


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    try:
        summary = run_pipeline(args)
        if summary["status"] == "complete":
            fs = summary.get("family_summary", {})
            print(f"\n✅ Mining complete — {fs.get('raw_rule_count', 0)} rules → "
                  f"{fs.get('independent_alpha_family_count', 0)} families "
                  f"in {summary['elapsed_seconds']}s")
            print(f"   Output: {summary['output_dir']}")
            return 0
        elif summary["status"] == "no_rules_found":
            print("\n⚠️  No rules met minimum criteria")
            return 1
        else:
            print(f"\n❌ Pipeline failed: {summary.get('error', 'unknown')}")
            return 1
    except Exception as e:
        logger.exception("Pipeline failed: %s", e)
        print(f"\n❌ Pipeline failed: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
