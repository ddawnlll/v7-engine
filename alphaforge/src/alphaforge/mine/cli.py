"""Mining Pipeline CLI — tek komutta tüm P1.0 pipeline'ı.

Usage:
    python -m alphaforge.mine.cli \\
        --candidates data/candidates/outcomes_v1.parquet \\
        --levels 1,2,3 \\
        --min-support 100 \\
        --top-k 500 \\
        --output reports/alphaforge/mining/run_001/

Pipeline: CandidateOutcomeDataset → Bucketizer → BitsetEngine → Scorer → MTC → OOS → AlphaRuleSpec
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="P1.0 Profit-State Mining Alpha Factory",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m alphaforge.mine.cli --candidates data/candidates/v001.parquet --levels 1,2
  python -m alphaforge.mine.cli --candidates data/candidates/v001.parquet --levels 1,2,3 --min-support 200 --top-k 1000
        """,
    )
    parser.add_argument("--candidates", required=True, help="Path to CandidateOutcomeDataset parquet")
    parser.add_argument("--levels", default="1,2,3", help="Mining levels (comma-separated: 1,2,3)")
    parser.add_argument("--min-support", type=int, default=100, help="Minimum support count")
    parser.add_argument("--top-k", type=int, default=500, help="Max rules to keep after Level 1")
    parser.add_argument("--output", default="reports/alphaforge/mining", help="Output directory")
    parser.add_argument("--discovery-end", help="Discovery period end date (ISO format)")
    parser.add_argument("--validation-end", help="Validation period end date (ISO format)")
    parser.add_argument("--log-level", default="INFO", help="Logging level")
    return parser


def run_pipeline(args: argparse.Namespace) -> dict:
    """Run the full mining pipeline."""
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    levels = [int(l.strip()) for l in args.levels.split(",")]
    min_support = args.min_support
    top_k = args.top_k

    # Import mining modules
    from alphaforge.mine.candidate_dataset import CandidateOutcomeBuilder
    from alphaforge.mine.bucketizer import FeatureBucketizer
    from alphaforge.mine.bitset_engine import BitsetEngine
    from alphaforge.mine.rule_scorer import RuleScorer
    from alphaforge.mine.multi_testing import MultiTestingCorrector
    from alphaforge.mine.oos_validator import OOSValidator

    import pyarrow.parquet as pq

    start = time.time()
    summary = {
        "status": "running",
        "candidates_file": str(args.candidates),
        "levels": levels,
        "min_support": min_support,
        "steps_completed": [],
        "results": {},
    }

    # Step 1: Load CandidateOutcomeDataset
    logger.info("Loading candidates from %s", args.candidates)
    table = pq.read_table(args.candidates)
    summary["total_candidates"] = table.num_rows
    summary["steps_completed"].append("load")

    # Step 2: Bucketize features
    logger.info("Bucketizing features...")
    feature_cols = [
        "volatility_percentile", "momentum_rank", "volume_zscore",
        "atr_pct", "pullback_atr", "distance_to_range_high",
    ]
    bucketizer = FeatureBucketizer()
    bucketizer.fit(table, feature_cols)
    masks = bucketizer.transform(table)
    condition_registry = [
        c for c in bucketizer.get_condition_registry()
        if c.get("support_count", 0) >= min_support
    ]
    summary["total_conditions"] = len(condition_registry)
    summary["steps_completed"].append("bucketize")

    # Step 3: Extract target
    target = table.column("net_R").to_numpy().astype("float64")

    # Step 4: Mine rules
    engine = BitsetEngine()

    if 1 in levels:
        logger.info("Level 1: Single condition scan...")
        level1 = engine.level1_scan(masks, target, min_support=min_support)
        level1 = sorted(level1, key=lambda r: r["mean_net_R"], reverse=True)[:top_k]
        summary["results"]["level1_count"] = len(level1)
        summary["steps_completed"].append("level1")

    if 2 in levels:
        logger.info("Level 2: Pair condition scan...")
        level2 = engine.level2_scan(masks, target, top_n=top_k)
        summary["results"]["level2_count"] = len(level2)
        summary["steps_completed"].append("level2")

    if 3 in levels:
        logger.info("Level 3: Beam search...")
        from alphaforge.mine.beam_search import BeamSearchMiner
        miner = BeamSearchMiner()
        seed_rules = level2[:100] if "level2" in summary["steps_completed"] else level1[:100]
        level3 = miner.search(seed_rules, masks, target, beam_width=50, max_depth=3)
        summary["results"]["level3_count"] = len(level3)
        summary["steps_completed"].append("level3")

    # Combine all discovered rules
    all_rules = []
    if "level1" in summary["steps_completed"]:
        all_rules.extend(level1)
    if "level2" in summary["steps_completed"]:
        all_rules.extend(level2)
    if "level3" in summary["steps_completed"]:
        all_rules.extend(level3)

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

    # Step 5: Score rules
    logger.info("Scoring %d rules...", len(all_rules))
    scorer = RuleScorer()
    symbol_map = table.column("symbol").to_numpy() if "symbol" in table.column_names else None
    regime_map = table.column("regime_trend").to_numpy() if "regime_trend" in table.column_names else None
    if symbol_map is not None:
        symbol_map = symbol_map.astype(str)
    if regime_map is not None:
        regime_map = regime_map.astype(str)
    scored_rules = scorer.score_batch(all_rules, masks, target, symbol_map, regime_map)
    summary["steps_completed"].append("score")

    # Step 6: Multi-testing correction
    logger.info("Applying multi-testing correction...")
    corrector = MultiTestingCorrector()
    corrected_rules = corrector.correct(scored_rules, method="fdr")
    passes = [r for r in corrected_rules if r.get("passes_correction", True)]
    summary["results"]["passes_correction"] = len(passes)
    summary["results"]["fails_correction"] = len(corrected_rules) - len(passes)
    summary["steps_completed"].append("mtc")

    # Step 7: OOS Validation
    logger.info("Running OOS validation...")
    validator = OOSValidator()
    oos_result = validator.validate(
        passes,
        {"net_R": target, "symbol": symbol_map, "regime": regime_map, "table": table},
        discovery_end=args.discovery_end,
        validation_end=args.validation_end,
    )
    summary["results"]["oos"] = oos_result.get("summary", {})
    summary["steps_completed"].append("oos")

    # Step 8: Export AlphaRuleSpecs
    logger.info("Exporting AlphaRuleSpec artifacts...")
    specs_dir = output_dir / "alpha_rule_specs"
    specs_dir.mkdir(parents=True, exist_ok=True)
    from alphaforge.mine.candidate_dataset import AlphaRuleSpecExporter
    exporter = AlphaRuleSpecExporter()
    exported = exporter.export(passes[: min(50, len(passes))], str(specs_dir))
    summary["results"]["exported_specs"] = exported
    summary["steps_completed"].append("export")

    # Summary
    elapsed = time.time() - start
    summary["elapsed_seconds"] = round(elapsed, 2)
    summary["status"] = "complete"
    summary["output_dir"] = str(output_dir)

    # Write summary
    summary_path = output_dir / "mining_summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2, default=str)
    logger.info("Summary written to %s", summary_path)
    logger.info("Pipeline complete in %.1f seconds — %d rules discovered",
                elapsed, len(all_rules))

    return summary


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO),
                        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    try:
        summary = run_pipeline(args)
        if summary["status"] == "complete":
            print(f"\n✅ Pipeline complete — {summary['total_rules_discovered']} rules discovered "
                  f"in {summary['elapsed_seconds']}s")
            print(f"   Output: {summary['output_dir']}")
            return 0
        elif summary["status"] == "no_rules_found":
            print("\n⚠️  Pipeline finished — no rules met minimum criteria")
            return 1
        else:
            print(f"\n❌ Pipeline failed — status: {summary['status']}")
            return 1
    except Exception as e:
        logger.exception("Pipeline failed: %s", e)
        print(f"\n❌ Pipeline failed: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
