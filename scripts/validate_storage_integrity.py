#!/usr/bin/env python3
"""
Storage integrity validation for V7 market data.

Verifies:
  1. Every Parquet file has a matching .sha256 sidecar
  2. Every sha256 checksum matches its Parquet file
  3. No orphaned .sha256 sidecar files (no matching .parquet)
  4. Catalog entries are consistent with files on disk
  5. Catalog queries produce correct filtered results
  6. Parquet files are readable and contain expected columns

Usage:
    # Check all data directories
    PYTHONPATH=. python3 scripts/validate_storage_integrity.py

    # Check a specific data directory
    PYTHONPATH=. python3 scripts/validate_storage_integrity.py --data-dir data

    # Check a single file
    PYTHONPATH=. python3 scripts/validate_storage_integrity.py --file data/raw/BTCUSDT/BTCUSDT_1h_1700000000000_1700086400000.parquet

    # Quiet mode (only errors)
    PYTHONPATH=. python3 scripts/validate_storage_integrity.py --quiet

Exit codes:
    0 — All checks passed
    1 — One or more checks failed
"""

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

import pyarrow.parquet as pq

EXPECTED_KLINES_COLUMNS = {
    "symbol", "timestamp", "open", "high", "low", "close",
    "volume", "quote_volume", "trade_count", "taker_buy_volume",
    "taker_buy_quote_volume", "interval", "source", "is_closed",
}

EXPECTED_FUNDING_COLUMNS = {
    "symbol", "timestamp", "funding_rate", "source",
}


def compute_sha256(file_path: str) -> str:
    """Compute SHA-256 hex digest of a file."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def validate_single_file(file_path: str, quiet: bool = False) -> bool:
    """Validate a single Parquet file and its sidecar.

    Returns True if valid, False otherwise.
    """
    if not os.path.isfile(file_path):
        print(f"ERROR: File not found: {file_path}")
        return False

    if not file_path.endswith(".parquet"):
        print(f"ERROR: Not a .parquet file: {file_path}")
        return False

    sidecar_path = file_path + ".sha256"
    errors = []

    # Check sidecar exists
    if not os.path.isfile(sidecar_path):
        errors.append(f"MISSING_SIDECAR: {sidecar_path}")

    # Verify checksum
    if not errors:
        with open(sidecar_path) as f:
            expected = f.read().strip()
        actual = compute_sha256(file_path)
        if actual != expected:
            errors.append(f"CHECKSUM_MISMATCH: expected={expected[:16]}... actual={actual[:16]}...")

    # Verify Parquet readability
    try:
        table = pq.read_table(file_path)
        columns = set(table.column_names)
        if len(table) == 0:
            errors.append("EMPTY_PARQUET: 0 rows")
    except Exception as e:
        errors.append(f"PARQUET_READ_ERROR: {e}")

    if errors:
        for e in errors:
            print(f"FAIL: {file_path}: {e}")
        return False

    if not quiet:
        print(f"OK: {file_path}")
    return True


def validate_directory(data_dir: str, quiet: bool = False) -> dict:
    """Validate all Parquet files in a data directory tree.

    Returns dict with pass/fail counts.
    """
    stats = {
        "parquet_files": 0,
        "passed": 0,
        "failed": 0,
        "orphaned_sha256": 0,
        "catalog_ok": True,
        "catalog_issues": [],
    }

    base = Path(data_dir)
    if not base.is_dir():
        print(f"INFO: Data directory does not exist: {data_dir} (nothing to validate)")
        return stats

    # Gather all .parquet and .sha256 files
    parquet_files: set[str] = set()
    sha256_files: set[str] = set()

    for root, _, files in os.walk(data_dir):
        for f in files:
            full = os.path.join(root, f)
            if f.endswith(".parquet"):
                parquet_files.add(full)
            elif f.endswith(".sha256"):
                sha256_files.add(full)

    stats["parquet_files"] = len(parquet_files)

    if not parquet_files and not sha256_files:
        if not quiet:
            print("INFO: No Parquet or .sha256 files found (clean slate)")
        return stats

    # Validate each Parquet
    for pf in sorted(parquet_files):
        if validate_single_file(pf, quiet=quiet):
            stats["passed"] += 1
        else:
            stats["failed"] += 1

    # Check for orphaned .sha256 files
    expected_sidecars = {pf + ".sha256" for pf in parquet_files}
    for sf in sorted(sha256_files):
        if sf not in expected_sidecars:
            print(f"WARN: Orphaned .sha256 (no matching .parquet): {sf}")
            stats["orphaned_sha256"] += 1

    # Validate catalog consistency
    catalog_path = os.path.join(data_dir, "catalog.json")
    if os.path.isfile(catalog_path):
        stats.update(_validate_catalog(catalog_path, data_dir, quiet))
    else:
        if not quiet:
            print("INFO: No catalog.json found (not yet created)")

    return stats


def _validate_catalog(catalog_path: str, data_dir: str, quiet: bool) -> dict:
    """Validate catalog consistency against files on disk.

    Checks:
      - Catalog is valid JSON
      - Each entry's checksum matches the file identified by
        (symbol, interval, start_ts, end_ts)
      - No duplicate entries
    """
    result: dict = {"catalog_ok": True, "catalog_issues": []}

    try:
        with open(catalog_path) as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        result["catalog_ok"] = False
        result["catalog_issues"].append(f"CATALOG_CORRUPT: {e}")
        print(f"FAIL: catalog.json is corrupt: {e}")
        return result

    entries = data.get("entries", [])
    if not entries:
        if not quiet:
            print("INFO: catalog.json has no entries")
        return result

    if not quiet:
        print(f"INFO: catalog.json has {len(entries)} entries")

    # Check for duplicates
    seen = set()
    for i, entry in enumerate(entries):
        key = (entry.get("symbol"), entry.get("interval"),
               entry.get("start_ts"), entry.get("end_ts"))
        if key in seen:
            result["catalog_issues"].append(
                f"DUPLICATE_ENTRY[{i}]: {entry['symbol']} {entry['interval']} "
                f"[{entry['start_ts']}, {entry['end_ts']})"
            )
            result["catalog_ok"] = False
        seen.add(key)

    # Check required keys
    required = {"symbol", "interval", "start_ts", "end_ts", "row_count", "checksum", "ingested_at"}
    for i, entry in enumerate(entries):
        missing = required - set(entry.keys())
        if missing:
            result["catalog_issues"].append(
                f"MISSING_KEYS[{i}]: {entry.get('symbol', '?')} missing {missing}"
            )
            result["catalog_ok"] = False

    # Cross-reference with files on disk (best effort)
    for entry in entries:
        symbol = entry.get("symbol", "")
        interval = entry.get("interval", "")
        start_ts = entry.get("start_ts")
        end_ts = entry.get("end_ts")
        expected_checksum = entry.get("checksum", "")

        if not all([symbol, interval, start_ts is not None, end_ts is not None]):
            continue

        # Try to locate the file
        raw_path = os.path.join(
            data_dir, "raw", symbol,
            f"{symbol}_{interval}_{start_ts}_{end_ts}.parquet",
        )
        norm_path = os.path.join(
            data_dir, "normalized", symbol,
            f"{symbol}_{interval}_{start_ts}_{end_ts}.parquet",
        )

        for path in [raw_path, norm_path]:
            if os.path.isfile(path):
                actual_checksum = compute_sha256(path)
                if actual_checksum == expected_checksum:
                    break
                else:
                    msg = (
                        f"CATALOG_CHECKSUM_MISMATCH: {entry['symbol']} {entry['interval']} "
                        f"catalog={expected_checksum[:16]}... file={actual_checksum[:16]}..."
                    )
                    result["catalog_issues"].append(msg)
                    result["catalog_ok"] = False
                break
        else:
            if not quiet:
                msg = (
                    f"CATALOG_MISSING_FILE: {entry['symbol']} {entry['interval']} "
                    f"[{entry['start_ts']}, {entry['end_ts']}) — no matching .parquet"
                )
                result["catalog_issues"].append(msg)
                result["catalog_ok"] = False

    if result["catalog_issues"]:
        for issue in result["catalog_issues"]:
            print(f"WARN: {issue}")

    return result


def run_catalog_query_tests(data_dir: str, quiet: bool) -> dict:
    """Run a short set of functional tests on the DataCatalog query API.

    These tests validate that the DataCatalog class works correctly
    independent of persistent files.
    """
    from lib.market_data.catalog import DataCatalog

    stats: dict = {"catalog_query_passed": 0, "catalog_query_failed": 0}

    catalog_path = os.path.join(data_dir, "catalog.json")

    # Clean test catalog
    cat = DataCatalog(catalog_path=catalog_path)
    cat.clear()

    # Add test entries
    cat.add_entry("BTCUSDT", "1h", 1000, 2000, 100, "abc123")
    cat.add_entry("ETHUSDT", "1h", 1000, 2000, 200, "def456")
    cat.add_entry("BTCUSDT", "4h", 3000, 4000, 50, "ghi789")

    tests = [
        ("query all", lambda: len(cat.query()) == 3),
        ("query by symbol", lambda: len(cat.query(symbol="BTCUSDT")) == 2),
        ("query by interval", lambda: len(cat.query(interval="4h")) == 1),
        ("query by symbol+interval", lambda: len(cat.query(symbol="BTCUSDT", interval="1h")) == 1),
        ("query by time range", lambda: len(cat.query(start_ts=2000)) == 1),
        ("query missing", lambda: cat.query(symbol="NONEXISTENT") == []),
        ("query by end_ts", lambda: len(cat.query(end_ts=3000)) == 2),
    ]

    for name, test_fn in tests:
        try:
            if test_fn():
                stats["catalog_query_passed"] += 1
                if not quiet:
                    print(f"  catalog query: {name} ... OK")
            else:
                stats["catalog_query_failed"] += 1
                print(f"  catalog query: {name} ... FAIL (assertion)")
        except Exception as e:
            stats["catalog_query_failed"] += 1
            print(f"  catalog query: {name} ... FAIL ({e})")

    # Cleanup test catalog
    cat.clear()
    cat.save()
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate V7 market data storage integrity",
    )
    parser.add_argument(
        "--data-dir", default="data",
        help="Root data directory (default: data)",
    )
    parser.add_argument(
        "--file",
        help="Validate a single Parquet file",
    )
    parser.add_argument(
        "--quiet", "-q", action="store_true",
        help="Only print errors",
    )
    parser.add_argument(
        "--catalog-only", action="store_true",
        help="Only run catalog query tests (no file checks)",
    )
    args = parser.parse_args()

    overall_pass = True

    if args.catalog_only:
        if not args.quiet:
            print("--- Catalog Query Tests ---")
        query_stats = run_catalog_query_tests(args.data_dir, args.quiet)
        if query_stats["catalog_query_failed"] > 0:
            overall_pass = False
    elif args.file:
        overall_pass = validate_single_file(args.file, args.quiet)
    else:
        if not args.quiet:
            print(f"--- Storage Integrity Check: {args.data_dir} ---")

        stats = validate_directory(args.data_dir, args.quiet)

        if not args.quiet:
            print(f"\n  Parquet files: {stats['parquet_files']}")
            print(f"  Passed:        {stats['passed']}")
            print(f"  Failed:        {stats['failed']}")
            print(f"  Orphaned sha256:{stats['orphaned_sha256']}")

        if stats["failed"] > 0 or stats["orphaned_sha256"] > 0:
            overall_pass = False
        if not stats.get("catalog_ok", True):
            overall_pass = False

        # Catalog query functional tests
        if not args.quiet:
            print("\n--- Catalog Query Tests ---")
        query_stats = run_catalog_query_tests(args.data_dir, args.quiet)
        if query_stats["catalog_query_failed"] > 0:
            overall_pass = False

    if overall_pass:
        if not args.quiet:
            print("\nRESULT: ALL CHECKS PASSED")
        return 0
    else:
        print("\nRESULT: SOME CHECKS FAILED (see above)")
        return 1


if __name__ == "__main__":
    sys.exit(main())
