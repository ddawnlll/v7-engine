"""CLI entry point for outcome cache operations."""

import argparse
import sys
import pandas as pd

from .writer import OutcomeCacheWriter
from .reader import OutcomeCacheReader


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Outcome Cache CLI — persist and query candidate trade outcomes."
    )
    sub = parser.add_subparsers(dest="command")

    # ingest
    ingest = sub.add_parser("ingest", help="Ingest a CSV/Parquet of outcomes into cache")
    ingest.add_argument("--input", required=True, help="Input CSV or Parquet file")
    ingest.add_argument("--alpha-id", default="unknown", help="Alpha identifier")
    ingest.add_argument("--run-id", default="", help="Run identifier")
    ingest.add_argument("--cache-dir", default="data/outcome_cache/v1", help="Cache directory")

    # query
    query = sub.add_parser("query", help="Query cached outcomes")
    query.add_argument("--alpha-id", help="Filter by alpha_id")
    query.add_argument("--symbol", help="Filter by symbol")
    query.add_argument("--filter", help="Pandas query expression (e.g. 'net_R > 0.5')")
    query.add_argument("--cache-dir", default="data/outcome_cache/v1")
    query.add_argument("--output", help="Save results to CSV")

    # summary
    summary = sub.add_parser("summary", help="Show cache summary")
    summary.add_argument("--cache-dir", default="data/outcome_cache/v1")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "ingest":
        writer = OutcomeCacheWriter(base_path=args.cache_dir)
        if args.input.endswith(".parquet"):
            df = pd.read_parquet(args.input)
        else:
            df = pd.read_csv(args.input)

        count = writer.append_dataframe(df, alpha_id=args.alpha_id, run_id=args.run_id)
        writer.close()
        print(f"Ingested {count} records from {args.input} into {args.cache_dir}")
        return 0

    elif args.command == "query":
        reader = OutcomeCacheReader(base_path=args.cache_dir)
        if args.filter:
            result = reader.query(args.filter)
        else:
            result = reader.get_outcomes(alpha_id=args.alpha_id, symbol=args.symbol)
        print(f"Query returned {len(result)} records")
        if not result.empty:
            print(result.head(10).to_string())
        if args.output and not result.empty:
            result.to_csv(args.output, index=False)
            print(f"Saved to {args.output}")
        return 0

    elif args.command == "summary":
        reader = OutcomeCacheReader(base_path=args.cache_dir)
        s = reader.summary()
        print(f"Total records: {s['total_records']}")
        print(f"Alphas: {s.get('alphas', [])}")
        print(f"Symbols: {s.get('symbols', [])}")
        print(f"net_R range: {s.get('net_R_min', 'N/A'):.4f} to {s.get('net_R_max', 'N/A'):.4f}")
        print(f"net_R mean: {s.get('net_R_mean', 'N/A'):.6f}")
        return 0

    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
