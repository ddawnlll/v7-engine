#!/usr/bin/env python3
"""MAX-PERFORMANCE Binance Vision downloader.

Squeezes max throughput from Binance Vision public S3 mirror:
  - Async I/O with aiohttp for high-concurrency downloads (60+ parallel)
  - ProcessPoolExecutor offloads CSV parsing (pandas C engine) from network path
  - ZIP stays in memory — no temp-file round trip
  - Retry with exponential backoff for transient failures
  - 1h klines only (direct from data.binance.vision, no API key needed)
  - 4h is auto-resampled from 1h via pandas after download phase
  - Resume support (skips existing files)

Performance:
  Network: 60-concurrent async downloads saturates local bandwidth
  CPU:     All cores parse CSV→parquet in parallel while network continues
  Target:  70+ files/sec (vs ~7/sec with old thread+urllib+pure-Python parser)

Usage:
    make download                                # max perf default
    python3 scripts/download_binance.py --concurrency 80
    python3 scripts/download_binance.py --verify  # with checksums
"""

import argparse
import asyncio
import concurrent.futures
import hashlib
import io
import multiprocessing
import os
import sys
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "alphaforge" / "src"))
sys.path.insert(0, str(REPO_ROOT))

BINANCE_VISION_BASE = "https://data.binance.vision/data/futures/um/monthly/klines"
SUPPORTED_INTERVALS = frozenset({"1m", "5m", "15m", "1h"})
DEFAULT_CONCURRENCY = 60          # async semaphore — not threads, so this is safe

try:
    from tqdm import tqdm
except ImportError:
    tqdm = None

try:
    import aiohttp
except ImportError:
    print("ERROR: requires aiohttp. Install:\n    pip install aiohttp --break-system-packages")
    sys.exit(1)


# ---------------------------------------------------------------------------
# CPU-bound parse step — runs in ProcessPoolExecutor workers
# ---------------------------------------------------------------------------

def _parse_zip_to_parquet(zip_bytes: bytes, symbol: str, interval: str,
                          year: int, month: int, out_path_str: str,
                          expected_sha: str | None = None) -> dict:
    """Extract CSV from in-memory ZIP, parse with pandas C engine, write Parquet.

    Designed for ProcessPoolExecutor — all imports are local so each worker
    has its own import state regardless of multiprocessing context.

    Returns {status, records, error}.
    """
    csv_name = f"{symbol}-{interval}-{year}-{month:02d}.csv"
    out_path = Path(out_path_str)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
            csv_bytes = zf.read(csv_name)

        # Optional SHA-256 check
        if expected_sha:
            actual = hashlib.sha256(csv_bytes).hexdigest()
            if actual != expected_sha:
                return {"status": "error", "records": 0, "error": "SHA-256 mismatch"}

        # Binance Vision CSVs have a header row; detect and skip it
        skiprows = 1 if csv_bytes[:9] == b"open_time" else 0

        COLS = [
            "open_time", "open", "high", "low", "close", "volume",
            "close_time", "quote_volume", "trade_count",
            "taker_buy_base_volume", "taker_buy_quote_volume", "ignore",
        ]
        USE_COLS = [0, 1, 2, 3, 4, 5, 7, 8, 9, 10]  # drop close_time + ignore

        import pandas as pd
        df = pd.read_csv(
            io.BytesIO(csv_bytes),
            header=None, names=COLS, skiprows=skiprows,
            engine="c", usecols=USE_COLS,
            dtype={
                "open_time": "int64",
                "open": "float64",
                "high": "float64",
                "low": "float64",
                "close": "float64",
                "volume": "float64",
                "quote_volume": "float64",
                "trade_count": "int64",
                "taker_buy_base_volume": "float64",
                "taker_buy_quote_volume": "float64",
            },
        )
        df = df.rename(columns={"open_time": "timestamp"})
        df["interval"] = interval

        import pyarrow as pa
        import pyarrow.parquet as pq
        table = pa.Table.from_pandas(df, preserve_index=False)
        pq.write_table(table, out_path_str, compression="zstd")

        return {"status": "ok", "records": len(df), "error": None}

    except Exception as exc:
        return {"status": "error", "records": 0, "error": str(exc)}


# ---------------------------------------------------------------------------
# Async download helpers (I/O bound — asyncio + aiohttp)
# ---------------------------------------------------------------------------

async def download_zip(session: aiohttp.ClientSession, sem: asyncio.Semaphore,
                       url: str) -> bytes | None:
    """Download one ZIP file with retry + exponential backoff.

    Returns raw bytes on success, None on 404, raises on terminal failure.
    The ``sem`` semaphore limits global concurrent downloads.
    """
    max_retries = 3
    for attempt in range(max_retries):
        try:
            async with sem:
                async with session.get(
                    url, timeout=aiohttp.ClientTimeout(total=120)
                ) as resp:
                    if resp.status == 404:
                        return None
                    resp.raise_for_status()
                    return await resp.read()
        except (aiohttp.ClientError, asyncio.TimeoutError, OSError):
            if attempt == max_retries - 1:
                raise
            await asyncio.sleep(1.5 ** attempt)
    return None  # unreachable


async def fetch_checksum(session: aiohttp.ClientSession, url: str) -> str | None:
    """Fetch the SHA-256 checksum file (``url.CHECKSUM``)."""
    try:
        async with session.get(url + ".CHECKSUM",
                               timeout=aiohttp.ClientTimeout(total=30)) as resp:
            if resp.status == 200:
                text = await resp.text()
                return text.strip().split()[0] if text else None
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Per-file pipeline: download → submit to process pool → collect result
# ---------------------------------------------------------------------------

async def process_one(session: aiohttp.ClientSession, sem: asyncio.Semaphore,
                      pool: concurrent.futures.ProcessPoolExecutor,
                      symbol: str, interval: str, year: int, month: int,
                      output_root: str, verify: bool) -> dict:
    """Pipeline for ONE monthly file: exists-check → download → parse → save.

    Returns status dict: {symbol, interval, year, month, status, path, error, records}.
    Skips if parquet already on disk.
    """
    out_path = Path(output_root) / symbol / interval / str(year) / f"{month:02d}.parquet"
    base = {"symbol": symbol, "interval": interval, "year": year, "month": month}

    # --- Resume: skip if already on disk ---
    if out_path.exists():
        try:
            import pyarrow.parquet as pq
            n = pq.ParquetFile(str(out_path)).metadata.num_rows
        except Exception:
            n = 0
        return {**base, "status": "skipped", "path": str(out_path),
                "error": None, "records": n}

    # --- Download ZIP (I/O bound, async) ---
    filename = f"{symbol}-{interval}-{year}-{month:02d}.zip"
    zip_url = f"{BINANCE_VISION_BASE}/{symbol}/{interval}/{filename}"

    try:
        zip_bytes = await download_zip(session, sem, zip_url)
    except Exception as exc:
        return {**base, "status": "error", "path": None,
                "error": f"download failed: {exc}", "records": 0}

    if zip_bytes is None:
        return {**base, "status": "error", "path": None,
                "error": "HTTP 404", "records": 0}

    # --- Optional checksum (another async fetch) ---
    expected_sha: str | None = None
    if verify:
        expected_sha = await fetch_checksum(session, zip_url)

    # --- CPU-bound: parse CSV → write parquet (process pool) ---
    loop = asyncio.get_running_loop()
    result: dict = await loop.run_in_executor(
        pool, _parse_zip_to_parquet,
        zip_bytes, symbol, interval, year, month, str(out_path), expected_sha,
    )

    return {**base, **result,
            "path": str(out_path) if result.get("status") == "ok" else None}


# ---------------------------------------------------------------------------
# Resample 1h → 4h (process-pool, kept from original)
# ---------------------------------------------------------------------------

def _resample_one_month(args: tuple) -> tuple:
    """Resample one 1h parquet file to 4h. Meant for ProcessPoolExecutor."""
    symbol, src_path_str, dst_path_str = args
    src_path = Path(src_path_str)
    dst_path = Path(dst_path_str)
    if dst_path.exists():
        return (symbol, str(src_path), "skipped", 0)
    try:
        import pandas as pd
        import pyarrow.parquet as pq
        import pyarrow as pa
        df = pq.read_table(str(src_path)).to_pandas()
        if len(df) < 4:
            return (symbol, str(src_path), "skip_too_small", 0)
        if "timestamp" not in df.columns and "open_time" in df.columns:
            df = df.rename(columns={"open_time": "timestamp"})
        df["ts"] = pd.to_datetime(df["timestamp"], unit="ms")
        df = df.sort_values("ts").set_index("ts")
        ohlc = df.resample("4h").agg({
            "open": "first", "high": "max", "low": "min", "close": "last",
            "volume": "sum", "quote_volume": "sum", "trade_count": "sum",
            "taker_buy_base_volume": "sum", "taker_buy_quote_volume": "sum",
        }).dropna().reset_index()
        ohlc["timestamp"] = ohlc["ts"].astype("int64") // 10**6
        ohlc = ohlc.drop(columns=["ts"])
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        pq.write_table(pa.Table.from_pandas(ohlc), str(dst_path), compression="zstd")
        return (symbol, str(src_path), "ok", len(ohlc))
    except Exception as e:
        return (symbol, str(src_path), "error", str(e))


def resample_to_4h(data_dir: str, symbols: list[str]) -> None:
    """Parallel 1h→4h resample using processes."""
    base = Path(data_dir)
    tasks = []
    for sym in symbols:
        src_dir = base / sym / "1h"
        if not src_dir.exists():
            continue
        for year_dir in sorted(src_dir.iterdir()):
            if not year_dir.is_dir():
                continue
            for mf in sorted(year_dir.iterdir()):
                if mf.suffix != ".parquet":
                    continue
                dst = base / sym / "4h" / year_dir.name / mf.name
                tasks.append((sym, str(mf), str(dst)))

    if not tasks:
        return

    pbar = tqdm(total=len(tasks), unit="file", desc="Resample 1h→4h",
                bar_format="{l_bar}{bar:20}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]") if tqdm else None

    ok = 0
    with concurrent.futures.ProcessPoolExecutor(max_workers=4) as exc:
        for result in exc.map(_resample_one_month, tasks):
            if result[2] == "ok":
                ok += 1
            if pbar:
                pbar.update(1)

    if pbar:
        pbar.close()
    if ok:
        print(f"    {ok} files resampled to 4h")


# ---------------------------------------------------------------------------
# Catalog registration (kept from original)
# ---------------------------------------------------------------------------

def update_catalog(data_dir: str, symbols: list[str], intervals: list[str]) -> None:
    """Register all parquet files in DataCatalog."""
    import pyarrow.parquet as pq
    from lib.data_lake.catalog import DataCatalog
    from lib.data_lake.checksum import compute_sha256

    base = Path(data_dir)
    lake_root = base
    # If caller points at the canonical klines root, store catalog at the
    # enclosing data-lake root rather than mutating repo-level data/catalog.json.
    if base.parts[-4:] == ("raw", "binance", "um", "klines"):
        lake_root = base.parents[3]
    cat = DataCatalog(catalog_path=str(lake_root / "catalog.json"))
    count = 0
    for sym in symbols:
        for interval in intervals:
            src = base / sym / interval
            if not src.exists():
                continue
            for year_dir in sorted(src.iterdir()):
                if not year_dir.is_dir():
                    continue
                for pf in sorted(year_dir.iterdir()):
                    if pf.suffix != ".parquet":
                        continue
                    try:
                        n = pq.ParquetFile(str(pf)).metadata.num_rows
                        chk = compute_sha256(pf)
                        cat.add_entry(sym, interval, 0, 0, n, chk)
                        count += 1
                    except Exception:
                        pass
    cat.save()
    print(f"  Catalog: {count} entries registered")


# ---------------------------------------------------------------------------
# Async orchestrator
# ---------------------------------------------------------------------------

async def main_async(args: argparse.Namespace) -> list[dict]:
    """Orchestrate async downloads + parallel CPU parsing + tqdm."""
    symbols = [s.strip() for s in args.symbols.split(",")]
    intervals = [s.strip() for s in args.intervals.split(",")]

    now = datetime.now(timezone.utc)
    end_year = args.end_year or now.year
    end_month = args.end_month or now.month

    # Build flat task list
    tasks = []
    for sym in symbols:
        for interval in intervals:
            if interval not in SUPPORTED_INTERVALS:
                continue
            for year in range(args.start_year, end_year + 1):
                sm = args.start_month if year == args.start_year else 1
                em = end_month if year == end_year else 12
                for month in range(sm, em + 1):
                    tasks.append((sym, interval, year, month))

    total = len(tasks)
    if total == 0:
        return []

    verify_str = "ON" if args.verify else "OFF"
    print(f"  Symbols:   {symbols}")
    print(f"  Intervals: {intervals}")
    print(f"  Period:    {args.start_year}-{args.start_month:02d} to {end_year}-{end_month:02d}")
    print(f"  Concurrency: {args.concurrency} (async) | CPU cores: {multiprocessing.cpu_count()}")
    print(f"  Checksums: {verify_str}")
    print(f"  Tasks:     {total} files ({total // len(symbols)} per symbol)")
    print()

    # Shared resources
    conn = aiohttp.TCPConnector(limit=100, limit_per_host=100)
    sem = asyncio.Semaphore(args.concurrency)

    results: list[dict] = []

    with concurrent.futures.ProcessPoolExecutor(
        max_workers=multiprocessing.cpu_count()
    ) as pool:
        async with aiohttp.ClientSession(connector=conn) as session:
            coros = [
                process_one(session, sem, pool, sym, intv, y, m,
                            args.output_dir, args.verify)
                for sym, intv, y, m in tasks
            ]

            pbar = tqdm(
                total=total, unit="file",
                bar_format="{l_bar}{bar:30}| {n_fmt}/{total_fmt} "
                           "[{elapsed}<{remaining}, {rate_fmt}]",
            ) if tqdm else None

            # Await in completion order (fast downloads surface first)
            for coro in asyncio.as_completed(coros):
                try:
                    r = await coro
                    results.append(r)
                except Exception as exc:
                    results.append({"status": "error", "error": str(exc),
                                    "records": 0})
                if pbar:
                    pbar.update(1)

            if pbar:
                pbar.close()

    return results


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="MAX-PERF Binance Vision download")
    parser.add_argument("--symbols", default="BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT,XRPUSDT,DOGEUSDT,ADAUSDT,AVAXUSDT,LINKUSDT,DOTUSDT")
    parser.add_argument("--intervals", default="1h")
    parser.add_argument("--start-year", type=int, default=2023)
    parser.add_argument("--start-month", type=int, default=1)
    parser.add_argument("--end-year", type=int, default=None)
    parser.add_argument("--end-month", type=int, default=None)
    parser.add_argument("--output-dir", default="data_lake/raw/binance/um/klines")
    parser.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY,
                        help=f"Async download concurrency (default {DEFAULT_CONCURRENCY})")
    parser.add_argument("--workers", type=int, default=None,  # alias kept for compat
                        help="Deprecated alias for --concurrency")
    parser.add_argument("--verify", action="store_true",
                        help="Enable SHA-256 checksum verification (slower)")
    args = parser.parse_args()

    # Accept --workers as alias for --concurrency (back-compat)
    if args.workers is not None:
        args.concurrency = args.workers

    symbols = [s.strip() for s in args.symbols.split(",")]
    intervals = [s.strip() for s in args.intervals.split(",")]
    unsupported = [i for i in intervals if i not in SUPPORTED_INTERVALS]
    intervals = [i for i in intervals if i in SUPPORTED_INTERVALS]

    t0 = time.time()
    results = asyncio.run(main_async(args))
    elapsed = time.time() - t0

    # Tally
    ok = sum(1 for r in results if r.get("status") == "ok")
    skipped = sum(1 for r in results if r.get("status") == "skipped")
    errors = sum(1 for r in results if r.get("status") == "error")
    total_records = sum(r.get("records", 0) for r in results
                        if r.get("status") == "ok")

    total = len(results)
    rate = total / max(1, elapsed)
    print(f"\n  Done in {elapsed:.0f}s ({rate:.0f} files/min, {elapsed/max(1,total):.2f}s/file)")
    print(f"  Downloaded: {ok} files, {total_records:,} records")
    if skipped:
        print(f"  Skipped:    {skipped} (already on disk)")
    if errors:
        print(f"  Errors:     {errors}")
        for e in [r.get("error", "?") for r in results
                  if r.get("status") == "error"][:5]:
            print(f"    - {e}")

    # 4h resample (processes, self-contained)
    if unsupported:
        print(f"\n  Resampling 1h → {unsupported}...")
        resample_to_4h(args.output_dir, symbols)

    # Catalog registration
    print(f"\n  Updating catalog...")
    update_catalog(args.output_dir, symbols, intervals + unsupported)

    print(f"\n  Next: make data-health")
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
