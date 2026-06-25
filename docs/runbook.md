# V7 Engine — Runbook

Getting-started guide for the V7 Engine trading pipeline.

---

## Prerequisites

- Python 3.14+ (see `.python-version` or `pyproject.toml`)
- `pip` (bundled with Python)
- `make` (build tool, used for all common tasks)
- A Binance API key (for online/real-data mode — optional for offline)

---

## Setup

```bash
# One-shot: create venv, install deps, verify
make setup

# Quick re-setup (skip venv creation)
make setup ARGS=--quick

# Clean rebuild
make setup ARGS=--clean
```

The `setup` target creates a Python virtual environment, installs project
dependencies, and runs a brief verification.

---

## Configuration

### 1. Environment variables

```bash
cp .env.example .env
```

Edit `.env` and fill in your Binance API credentials if you plan to use
online/real-data mode.  **Never commit `.env`** — it contains secrets.

| Variable         | Required for     | Purpose                         |
|------------------|------------------|---------------------------------|
| `BINANCE_API_KEY`| Online mode      | Binance API authentication      |
| `BINANCE_SECRET` | Online mode      | Binance API authentication      |
| `DATA_DIR`       | Optional         | Override default data directory |

### 2. Pipeline config

```bash
cp configs/data.example.yaml      configs/data.yaml
cp configs/training.example.yaml  configs/training.yaml
```

Edit the YAML files to set default symbols, intervals, lookback parameters,
and model hyperparameters.  The pipeline reads `configs/data.yaml` and
`configs/training.yaml` at runtime.

---

## Offline / Fixture Mode

All CLI commands default to offline behaviour.  Run with `--dry-run` to
verify what would happen:

```bash
# See the full pipeline plan without executing anything
PYTHONPATH=alphaforge/src:. python3 -m cli pipeline --dry-run

# Or step-by-step:
PYTHONPATH=alphaforge/src:. python3 -m cli backfill --dry-run --symbols BTCUSDT --intervals 4h --start 2024-01-01 --end 2024-01-02
PYTHONPATH=alphaforge/src:. python3 -m cli simulate --dry-run --mode SWING --symbols BTCUSDT
PYTHONPATH=alphaforge/src:. python3 -m cli build-dataset --dry-run
PYTHONPATH=alphaforge/src:. python3 -m cli train --dry-run
PYTHONPATH=alphaforge/src:. python3 -m cli wfv --dry-run
PYTHONPATH=alphaforge/src:. python3 -m cli report --dry-run
```

Training and WFV are **gated** — they print a warning in dry-run mode and
refuse to run in real mode unless `--force` is supplied.

---

## Online / Real-Data Mode

1. Ensure `.env` contains valid Binance API keys.
2. Run without `--dry-run`:

```bash
PYTHONPATH=alphaforge/src:. python3 -m cli backfill --symbols BTCUSDT --intervals 4h
PYTHONPATH=alphaforge/src:. python3 -m cli simulate --mode SWING
```

**Limitation**: Real mode emits "Not yet implemented — use --dry-run for now"
for most commands.  The CLI skeleton is wired for future implementation.

---

## Pipeline Steps

| Step            | Description                                                  | Plan ID                         |
|-----------------|--------------------------------------------------------------|---------------------------------|
| `validate`      | Contract checks + boundary checks + smoke tests             | TR-03-PIPELINE-CLI-MAKEFILE-RUNBOOK |
| `backfill`      | Download raw market data from exchange                       | TR-03-PIPELINE-CLI-MAKEFILE-RUNBOOK |
| `simulate`      | Run simulation with cost model (fee, slippage)               | TR-03-PIPELINE-CLI-MAKEFILE-RUNBOOK |
| `build-dataset` | Assemble feature matrix + label vector from raw data         | TR-03-PIPELINE-CLI-MAKEFILE-RUNBOOK |
| `train`         | Train XGBoost / model (gated)                                | TR-03-PIPELINE-CLI-MAKEFILE-RUNBOOK |
| `wfv`           | Walk-forward validation (gated)                              | TR-03-PIPELINE-CLI-MAKEFILE-RUNBOOK |
| `report`        | Generate pipeline report                                     | TR-03-PIPELINE-CLI-MAKEFILE-RUNBOOK |

---

## Make Targets Reference

| Target            | Equivalent CLI command               | Plan ID                         |
|-------------------|--------------------------------------|---------------------------------|
| `make validate`   | `python3 -m cli validate`           | TR-03-PIPELINE-CLI-MAKEFILE-RUNBOOK |
| `make backfill`   | `python3 -m cli backfill`           | TR-03-PIPELINE-CLI-MAKEFILE-RUNBOOK |
| `make simulate`   | `python3 -m cli simulate`           | TR-03-PIPELINE-CLI-MAKEFILE-RUNBOOK |
| `make build-dataset`| `python3 -m cli build-dataset`    | TR-03-PIPELINE-CLI-MAKEFILE-RUNBOOK |
| `make train`      | `python3 -m cli train`              | TR-03-PIPELINE-CLI-MAKEFILE-RUNBOOK |
| `make wfv`        | `python3 -m cli wfv`                | TR-03-PIPELINE-CLI-MAKEFILE-RUNBOOK |
| `make report`     | `python3 -m cli report`             | TR-03-PIPELINE-CLI-MAKEFILE-RUNBOOK |
| `make pipeline`   | `python3 -m cli pipeline`           | TR-03-PIPELINE-CLI-MAKEFILE-RUNBOOK |
| `make DRY_RUN=1 validate` | Show what validate would run | TR-03-PIPELINE-CLI-MAKEFILE-RUNBOOK |

---

## Troubleshooting

| Symptom                              | Likely cause                             | Fix                                      |
|--------------------------------------|------------------------------------------|------------------------------------------|
| `python3 -m cli` not found           | `cli/` package not in `PYTHONPATH`       | Set `PYTHONPATH=alphaforge/src:.`        |
| `make backfill` does nothing         | Command not yet implemented              | Run with `--dry-run` to see the plan     |
| `GATE: Training not yet authorized`  | Training gate active                     | Add `--force` or wait for authorization  |
| `ModuleNotFoundError: binance`       | Binance library not installed            | `pip install python-binance`             |
| `make setup` fails                   | Missing system dependency                | Check Python version, install `make`     |
| `BINANCE_API_KEY` not set            | `.env` missing or incomplete             | Copy `.env.example` to `.env` and fill   |

---

## Backfill Procedure

### Overview

The backfill pipeline downloads historical market data from Binance and stores
it in Parquet format with SHA-256 integrity checksums. The orchestrator
(`BackfillOrchestrator`) coordinates four subsystems:

| Component            | Responsibility                              | Key file                                   |
|----------------------|---------------------------------------------|--------------------------------------------|
| `KlinesService`      | Fetch klines, paginate, normalize           | `lib/market_data/binance/klines_service.py`|
| `FundingService`     | Fetch funding rate history                  | `lib/market_data/binance/funding_service.py`|
| `StorageWriter`      | Write Parquet + SHA-256 sidecar             | `lib/market_data/storage.py`               |
| `DataCatalog`        | Track ingested symbols/intervals/ranges     | `lib/market_data/catalog.py`               |
| `BinanceRateLimiter` | Token-bucket rate limiter with 429 backoff  | `lib/market_data/binance/rate_limiter.py`  |
| `BackfillCheckpoint` | Resume interrupted backfills                | `lib/market_data/binance/checkpoint.py`    |

### Storage Layout

```
data/
├── catalog.json                          # Ingest catalog (JSON)
├── raw/
│   └── BTCUSDT/
│       ├── BTCUSDT_1h_1700000000000_1700086400000.parquet
│       └── BTCUSDT_1h_1700000000000_1700086400000.parquet.sha256
└── normalized/
    └── BTCUSDT/
        ├── BTCUSDT_1h_1700000000000_1700086400000.parquet
        ├── BTCUSDT_1h_1700000000000_1700086400000.parquet.sha256
        └── funding_BTCUSDT_1700000000000_1700086400000.parquet
```

### Prerequisites

1. **Binance API keys** (required for live backfill):
   ```bash
   export BINANCE_API_KEY="your-api-key"
   export BINANCE_SECRET="your-secret"
   ```

2. **Python dependencies** (installed via `make setup`):
   - `pyarrow` / `pandas` (Parquet)
   - `requests` (HTTP client)

### Running a Backfill

#### Dry-run (offline, no API calls)

```bash
PYTHONPATH=alphaforge/src:. python3 -m cli backfill --dry-run \
  --symbols BTCUSDT,ETHUSDT \
  --intervals 1h,4h \
  --start 2024-01-01 \
  --end 2024-01-02
```

#### Live backfill (requires Binance API keys)

```bash
PYTHONPATH=alphaforge/src:. python3 -m cli backfill \
  --symbols BTCUSDT \
  --intervals 1h \
  --start 2024-01-01 \
  --end 2024-01-31
```

For a short test backfill (1 week, single symbol):

```bash
PYTHONPATH=alphaforge/src:. python3 -m cli backfill \
  --symbols BTCUSDT \
  --intervals 1h \
  --start 2025-01-01 \
  --end 2025-01-08
```

#### Programmatic backfill (Python)

```python
from lib.market_data.binance.client import BinanceClient
from lib.market_data.binance.klines_service import KlinesService
from lib.market_data.binance.funding_service import FundingService
from lib.market_data.binance.rate_limiter import BinanceRateLimiter
from lib.market_data.binance.checkpoint import BackfillCheckpoint
from lib.market_data.binance.backfill import BackfillOrchestrator
from lib.market_data.storage import StorageWriter
from lib.market_data.catalog import DataCatalog

client = BinanceClient()
klines = KlinesService(client)
funding = FundingService(client)
writer = StorageWriter(base_dir="data")
catalog = DataCatalog(catalog_path="data/catalog.json")
limiter = BinanceRateLimiter(max_weight_per_minute=1200)
checkpoint = BackfillCheckpoint(file_path="checkpoints/backfill_checkpoint.json")

orchestrator = BackfillOrchestrator(
    klines_service=klines,
    funding_service=funding,
    storage_writer=writer,
    catalog=catalog,
    rate_limiter=limiter,
    checkpoint=checkpoint,
)

stats = orchestrator.backfill(
    symbols=["BTCUSDT", "ETHUSDT"],
    intervals=["1h", "4h"],
    start_time=1700000000000,   # ms timestamp
    end_time=1700086400000,
)
print(f"Records: {stats['total_records']}, Errors: {len(stats['errors'])}")
```

### Rate Limiting

The `BinanceRateLimiter` uses a token-bucket with a 1200 weight/minute limit
(rolling 60s window). Different endpoints consume different weights:

| Endpoint      | Weight |
|---------------|--------|
| Klines        | 1-10   |
| Funding rate  | 1      |

On HTTP 429 responses, exponential backoff is applied:
`delay = min(base * 2^retry_count, 60s) + jitter[0, 0.5*delay]`

### Checkpoint / Resume

Backfill checkpoints are stored in `checkpoints/backfill_checkpoint.json`.
Each (symbol, interval, time_range) is recorded after successful completion.
If a backfill is interrupted, re-running the same range skips already-completed
work.

To reset a checkpoint (force re-backfill):

```python
checkpoint = BackfillCheckpoint(file_path="checkpoints/backfill_checkpoint.json")
checkpoint.remove("BTCUSDT", "1h")
```

### Storage Integrity

After any backfill, verify storage integrity:

```bash
# Full integrity scan (Parquet + SHA-256 + catalog)
PYTHONPATH=. python3 scripts/validate_storage_integrity.py

# Single file check
PYTHONPATH=. python3 scripts/validate_storage_integrity.py \
  --file data/raw/BTCUSDT/BTCUSDT_1h_1700000000000_1700086400000.parquet

# Catalog query tests only
PYTHONPATH=. python3 scripts/validate_storage_integrity.py --catalog-only

# Quiet mode (only errors)
PYTHONPATH=. python3 scripts/validate_storage_integrity.py --quiet
```

The validation script checks:
1. Every `.parquet` has a matching `.sha256` sidecar
2. Every SHA-256 checksum matches its Parquet file bytes
3. No orphaned `.sha256` sidecars exist
4. Parquet files are readable with expected columns
5. `catalog.json` entries are consistent with files on disk
6. DataCatalog query API returns correct filtered results

### Backfill Troubleshooting

| Symptom                              | Likely cause                       | Fix                                      |
|--------------------------------------|------------------------------------|------------------------------------------|
| `BinanceClientError 429`             | Rate limit hit                     | Limiter handles with backoff; reduce concurrency |
| Empty records returned               | Time range has no candles          | Check symbol and interval; verify Binance has data for the range |
| `ModuleNotFoundError: pyarrow`       | Missing dependency                 | `pip install pyarrow`                    |
| Checksum mismatch in validation      | File corrupted or incomplete write | Delete the file and re-backfill the range |
| `BINANCE_API_KEY` not set            | `.env` missing                     | Copy `.env.example` to `.env` and fill   |
| Backfill interrupted mid-run         | Network or process failure         | Re-run same command; checkpoint skips completed ranges |
| `make backfill` does nothing         | Command not yet implemented        | Run with `--dry-run` to see the plan     |
