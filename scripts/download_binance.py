#!/usr/bin/env python3
"""Parallel Binance Vision downloader with real-time progress bar + ETA.

Downloads 1h klines from data.binance.vision (public S3 mirror, no API key).
4h data is NOT available from Vision — auto-resampled from 1h via pandas.

Usage:
    make download                          # default: 4 symbols, 8 workers
    python3 scripts/download_binance.py --workers 12
"""
import argparse
import concurrent.futures
import os
import shutil
import sys
import tempfile
import time
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from threading import Lock

try:
    from tqdm import tqdm
except ImportError:
    tqdm = None

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "alphaforge" / "src"))
sys.path.insert(0, str(REPO_ROOT))

# Binance Vision base URL for USD-M futures monthly klines
BINANCE_VISION_BASE = "https://data.binance.vision/data/futures/um/monthly/klines"

# Only these intervals are available from the public archive
VALID_VISION_INTERVALS = frozenset({"1m", "5m", "15m", "1h"})
SUPPORTED_INTERVALS = frozenset({"1m", "5m", "15m", "1h"})

# Column names for Binance klines CSV
KLINES_CSV_COLUMNS = [
    "open_time", "open", "high", "low", "close", "volume",
    "close_time", "quote_volume", "trade_count",
    "taker_buy_base_volume", "taker_buy_quote_volume", "ignore",
]

_LOCK = Lock()


# ---------------------------------------------------------------------------
# Atomic download task
# ---------------------------------------------------------------------------

def download_one_month(symbol: str, interval: str, year: int, month: int,
                       output_root: str) -> dict:
    """Download ONE monthly ZIP from Binance Vision and save as Parquet+Zstd.

    Returns dict with keys: symbol, interval, year, month, status, path, error.
    """
    out_path = Path(output_root) / symbol / interval / str(year) / f"{month:02d}.parquet"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Skip if already exists (safe resume)
    if out_path.exists():
        return {"symbol": symbol, "interval": interval, "year": year, "month": month,
                "status": "skipped", "path": str(out_path), "error": None}

    filename = f"{symbol}-{interval}-{year}-{month:02d}.zip"
    zip_url = f"{BINANCE_VISION_BASE}/{symbol}/{interval}/{filename}"
    checksum_url = zip_url + ".CHECKSUM"

    zip_tmp = None
    try:
        # --- Download ---
        try:
            resp = urllib.request.urlopen(zip_url, timeout=300)
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
            shutil.copyfileobj(resp, tmp)
            zip_tmp = tmp.name
            tmp.close()
        except HTTPError as e:
            return {"symbol": symbol, "interval": interval, "year": year, "month": month,
                    "status": "error", "path": None,
                    "error": f"HTTP {e.code}"}
        except Exception as e:
            return {"symbol": symbol, "interval": interval, "year": year, "month": month,
                    "status": "error", "path": None,
                    "error": f"network: {e}"}

        # --- Checksum verification ---
        try:
            expected_hash = _fetch_checksum(checksum_url)
            if expected_hash:
                actual_hash = _file_sha256(zip_tmp)
                if actual_hash != expected_hash:
                    os.unlink(zip_tmp)
                    return {"symbol": symbol, "interval": interval, "year": year, "month": month,
                            "status": "error", "path": None,
                            "error": "SHA-256 mismatch"}
        except Exception:
            pass  # proceed without checksum

        # --- Extract CSV & convert to Parquet ---
        csv_name = f"{symbol}-{interval}-{year}-{month:02d}.csv"
        with zipfile.ZipFile(zip_tmp, "r") as zf:
            with zf.open(csv_name) as f:
                csv_text = f.read().decode("utf-8")

        table = _parse_klines_csv(csv_text, interval)
        import pyarrow.parquet as pq
        pq.write_table(table, str(out_path), compression="zstd")

        if zip_tmp and os.path.exists(zip_tmp):
            os.unlink(zip_tmp)

        return {"symbol": symbol, "interval": interval, "year": year, "month": month,
                "status": "ok", "path": str(out_path), "error": None,
                "records": table.num_rows}

    except Exception as e:
        if zip_tmp and os.path.exists(zip_tmp):
            os.unlink(zip_tmp)
        return {"symbol": symbol, "interval": interval, "year": year, "month": month,
                "status": "error", "path": None, "error": str(e)}


# ---------------------------------------------------------------------------
# Internal helpers (from alphaforge/data/backfill.py)
# ---------------------------------------------------------------------------

def _fetch_checksum(url: str) -> str | None:
    """Fetch SHA-256 checksum from Binance CHECKSUM file."""
    try:
        resp = urllib.request.urlopen(url, timeout=30)
        line = resp.read().decode("utf-8").strip()
        return line.split()[0] if line else None
    except HTTPError:
        return None


def _file_sha256(path: str) -> str:
    """Compute SHA-256 of a file."""
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(64 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _parse_klines_csv(csv_text: str, interval: str):
    """Parse Binance klines CSV into a PyArrow table."""
    import pyarrow as pa
    import numpy as np

    opens, highs, lows, closes = [], [], [], []
    volumes, quote_volumes = [], []
    trades_list = []
    taker_buy_volumes, taker_buy_quote_volumes = [], []
    timestamps = []

    for line in csv_text.strip().splitlines():
        parts = line.split(",")
        if len(parts) < 11:
            continue
        try:
            timestamps.append(int(parts[0]))
            opens.append(float(parts[1]))
            highs.append(float(parts[2]))
            lows.append(float(parts[3]))
            closes.append(float(parts[4]))
            volumes.append(float(parts[5]))
            quote_volumes.append(float(parts[7]))
            trades_list.append(int(parts[8]))
            taker_buy_volumes.append(float(parts[9]))
            taker_buy_quote_volumes.append(float(parts[10]))
        except (ValueError, IndexError):
            continue

    n = len(timestamps)
    if n == 0:
        return pa.table({})

    return pa.table({
        "timestamp": pa.array(timestamps, type=pa.int64()),
        "open": pa.array(opens, type=pa.float64()),
        "high": pa.array(highs, type=pa.float64()),
        "low": pa.array(lows, type=pa.float64()),
        "close": pa.array(closes, type=pa.float64()),
        "volume": pa.array(volumes, type=pa.float64()),
        "quote_volume": pa.array(quote_volumes, type=pa.float64()),
        "trade_count": pa.array(trades_list, type=pa.int64()),
        "taker_buy_base_volume": pa.array(taker_buy_volumes, type=pa.float64()),
        "taker_buy_quote_volume": pa.array(taker_buy_quote_volumes, type=pa.float64()),
        "interval": pa.array([interval] * n, type=pa.string()),
    })


# ---------------------------------------------------------------------------
# Resample 1h → 4h
# ---------------------------------------------------------------------------

def resample_to_4h(data_dir: str, symbols: list[str]) -> None:
    """Resample 1h Parquet files to 4h using pandas."""
    try:
        import pandas as pd
        import pyarrow.parquet as pq
        import pyarrow as pa
    except ImportError:
        print("  [SKIP] pandas/pyarrow not available for 4h resample")
        return

    base = Path(data_dir)
    for symbol in symbols:
        src_dir = base / symbol / "1h"
        if not src_dir.exists():
            continue
        year_dirs = sorted(src_dir.iterdir())
        total = 0
        for year_dir in year_dirs:
            if not year_dir.is_dir():
                continue
            for month_file in sorted(year_dir.iterdir()):
                if month_file.suffix != ".parquet":
                    continue
                out_path = base / symbol / "4h" / year_dir.name / month_file.name
                if out_path.exists():
                    continue
                try:
                    df = pq.read_table(str(month_file)).to_pandas()
                    if len(df) < 4:
                        continue
                    df["ts"] = pd.to_datetime(df["timestamp"], unit="ms")
                    df = df.sort_values("ts").set_index("ts")
                    ohlc = df.resample("4h").agg({
                        "open": "first", "high": "max", "low": "min", "close": "last",
                        "volume": "sum", "quote_volume": "sum", "trade_count": "sum",
                        "taker_buy_base_volume": "sum", "taker_buy_quote_volume": "sum",
                    }).dropna().reset_index()
                    ohlc["timestamp"] = ohlc["ts"].astype("int64") // 10**6
                    ohlc = ohlc.drop(columns=["ts"])
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    pq.write_table(pa.Table.from_pandas(ohlc), str(out_path), compression="zstd")
                    total += 1
                except Exception as e:
                    print(f"    [ERR] {symbol} 4h {year_dir.name}/{month_file.name}: {e}")
        if total:
            print(f"    {symbol}: {total} files resampled to 4h")


# ---------------------------------------------------------------------------
# Register in DataCatalog
# ---------------------------------------------------------------------------

def update_catalog(data_dir: str, symbols: list[str], intervals: list[str]) -> None:
    """Register downloaded files in the DataCatalog."""
    try:
        import pyarrow.parquet as pq
        from lib.data_lake.catalog import DataCatalog
        from lib.data_lake.checksum import compute_sha256

        cat = DataCatalog()
        base = Path(data_dir)
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
                            pf_meta = pq.ParquetFile(str(pf)).metadata
                            row_count = pf_meta.num_rows
                            checksum = compute_sha256(pf)
                            cat.add_entry(
                                symbol=sym,
                                interval=interval,
                                start_ts=0,  # catalog tracks per-file ranges
                                end_ts=0,
                                row_count=row_count,
                                checksum=checksum,
                            )
                            count += 1
                        except Exception:
                            pass
        cat.save()
        print(f"  Catalog: {count} entries registered")
    except Exception as e:
        print(f"  [WARN] Catalog update skipped: {e}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="Parallel Binance Vision download")
    parser.add_argument("--symbols", default="BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT")
    parser.add_argument("--intervals", default="1h")
    parser.add_argument("--start-year", type=int, default=2023)
    parser.add_argument("--start-month", type=int, default=1)
    parser.add_argument("--end-year", type=int, default=None)
    parser.add_argument("--end-month", type=int, default=None)
    parser.add_argument("--output-dir", default="data_lake/raw/binance/um/klines")
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()

    symbols = [s.strip() for s in args.symbols.split(",")]
    intervals = [s.strip() for s in args.intervals.split(",")]

    unsupported = [i for i in intervals if i not in SUPPORTED_INTERVALS]
    intervals = [i for i in intervals if i in SUPPORTED_INTERVALS]

    now = datetime.now(timezone.utc)
    end_year = args.end_year or now.year
    end_month = args.end_month or now.month

    # Generate all atomic tasks: (symbol, interval, year, month)
    tasks = []
    for sym in symbols:
        for interval in intervals:
            for year in range(args.start_year, end_year + 1):
                start_m = args.start_month if year == args.start_year else 1
                end_m = end_month if year == end_year else 12
                for month in range(start_m, end_m + 1):
                    tasks.append((sym, interval, year, month))

    total = len(tasks)
    if total == 0:
        print("Nothing to download.")
        return 0

    print(f"  Symbols:   {symbols}")
    print(f"  Intervals: {intervals}")
    print(f"  Period:    {args.start_year}-{args.start_month:02d} to {end_year}-{end_month:02d}")
    print(f"  Workers:   {args.workers}")
    print(f"  Tasks:     {total} files ({total // len(symbols)} per symbol)")
    print()

    # Progress counters (thread-safe)
    counters = {"ok": 0, "skipped": 0, "error": 0}
    lock = Lock()

    pbar = None
    if tqdm is not None:
        pbar = tqdm(total=total, unit="file", desc="Downloading",
                     bar_format="{l_bar}{bar:30}| {n_fmt}/{total_fmt} "
                                "[{elapsed}<{remaining}, {rate_fmt}]")

    t0 = time.time()
    results = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        fut_to_task = {
            executor.submit(download_one_month, sym, interval, y, m, args.output_dir): (sym, interval, y, m)
            for sym, interval, y, m in tasks
        }

        for fut in concurrent.futures.as_completed(fut_to_task):
            task = fut_to_task[fut]
            try:
                result = fut.result()
                results.append(result)
                with lock:
                    counters[result.get("status", "error")] += 1
                if pbar:
                    pbar.update(1)
                    pbar.set_postfix(ok=counters["ok"], err=counters["error"],
                                     skip=counters["skipped"])
            except Exception as e:
                with lock:
                    counters["error"] += 1
                results.append({"status": "error", "error": str(e)})
                if pbar:
                    pbar.update(1)

    if pbar:
        pbar.close()

    elapsed = time.time() - t0
    ok = counters["ok"]
    skipped = counters["skipped"]
    errors = counters["error"]
    total_records = sum(r.get("records", 0) for r in results if r.get("status") == "ok")

    print(f"\n  Completed in {elapsed:.0f}s ({elapsed / max(1, total):.1f}s/file)")
    print(f"  Downloaded: {ok} files, {total_records:,} records")
    if skipped:
        print(f"  Skipped:    {skipped} (already on disk)")
    if errors:
        print(f"  Errors:     {errors}")
        err_samples = [r.get("error", "?") for r in results
                       if r.get("status") == "error"][:3]
        for e in err_samples:
            print(f"    - {e}")

    # Resample to 4h if needed
    if unsupported:
        print(f"\n  Resampling 1h → {unsupported}...")
        resample_to_4h(args.output_dir, symbols)

    # Register in catalog
    print(f"\n  Updating catalog...")
    update_catalog(args.output_dir, symbols, intervals + unsupported)

    print(f"\n  Next: make data-health")
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
