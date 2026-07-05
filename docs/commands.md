# V7 Engine — Commands Reference

Every Make target and CLI command documented, with options and examples.

---

## Make Targets

### `make help`
Print all available Make targets.

```bash
make help
```

### `make setup`
Full environment setup — creates virtual environment, installs dependencies,
and runs verification.

**Options:**
- `ARGS=--quick` — Skip venv creation (use existing venv)
- `ARGS=--clean` — Remove venv and rebuild
- `ARGS=--check` — Only run checks (no install)

**Examples:**
```bash
make setup
make setup ARGS=--quick
make setup ARGS=--clean
```

### `make install`
Install Python dependencies via pip.

### `make test`
Run test suite.

**Options:**
- `file=FILE` — Run a specific test file (relative path)

**Examples:**
```bash
make test
make test file=tests/test_cli_commands.py
```

### `make check-lib-boundaries`
Verify that `lib/` does not import from `v7/` or `alphaforge/` domains.

### `make check-boundaries`
Verify all domain import boundaries (lib + cross-domain).

### `make check-contracts`
Validate contract registry and schema parity.

### `make test-system`
Run all system-level tests (contracts + boundaries + smoke).

### `make test-all`
Run all tests (lib + system).

### `make clean`
Remove Python cache files, build artifacts, and temporary files.

### `make lint`
Run ruff linting.

### `make typecheck`
Run mypy type checking.

---

## Pipeline Make Targets (TR-03)

Each target runs with `PYTHONPATH=alphaforge/src:.` by default.  Set
`DRY_RUN=1` to print what would happen without executing.

### `make validate`
Run contract checks + boundary checks + test suite.

```bash
make validate
make DRY_RUN=1 validate
```

### `make backfill`
Download and backfill market data.

```bash
make backfill
make DRY_RUN=1 backfill
```

### `make simulate`
Run simulation with the cost model.

```bash
make simulate
make DRY_RUN=1 simulate
```

### `make build-dataset`
Build training dataset from features and labels.

```bash
make build-dataset
make DRY_RUN=1 build-dataset
```

### `make train`
Train model (gated — requires `--force` to bypass).

```bash
make train
make DRY_RUN=1 train
```

### `make wfv`
Run walk-forward validation (gated — requires a trained model).

```bash
make wfv
make DRY_RUN=1 wfv
```

### `make report`
Generate pipeline report.

```bash
make report
make DRY_RUN=1 report
```

### `make pipeline`
Run end-to-end pipeline: validate → backfill → simulate → build-dataset →
train → wfv → report.  Steps run sequentially; the pipeline stops at the
first failure.

```bash
make pipeline
make DRY_RUN=1 pipeline
```

---

## CLI Commands

Usage: `PYTHONPATH=alphaforge/src:. python3 -m cli <command> [options]`

### `--dry-run`
Global option available on every command.  Prints what would happen without
executing anything.

### `help`
Print usage information for all commands.

```bash
python3 -m cli help
python3 -m cli --help
```

### `validate`
Run contract + boundary validation.  Offline-safe.

```bash
# Offline (plan)
python3 -m cli validate --dry-run

# Online (real)
python3 -m cli validate
```

### `backfill`
Download and backfill historical market data from the exchange.

**Options:**

| Option        | Description                    | Example                |
|---------------|--------------------------------|------------------------|
| `--symbols`   | Symbols (comma-separated)      | `BTCUSDT,ETHUSDT`      |
| `--intervals` | Timeframe intervals            | `4h`, `1h`, `1d`       |
| `--start`     | Start date (YYYY-MM-DD)        | `2024-01-01`           |
| `--end`       | End date (YYYY-MM-DD)          | `2024-01-31`           |

**Examples:**
```bash
# Offline (plan)
python3 -m cli backfill --dry-run --symbols BTCUSDT --intervals 4h --start 2024-01-01

# Online (real)
python3 -m cli backfill --symbols BTCUSDT --intervals 4h --start 2024-01-01 --end 2024-01-31
```

### `simulate`
Run simulation with the engine's cost model (fee, slippage, horizon).

**Options:**

| Option      | Description              | Example          |
|-------------|--------------------------|------------------|
| `--mode`    | Trading mode             | `SWING`, `SCALP` |
| `--symbols` | Symbols (comma-separated)| `BTCUSDT`        |

**Examples:**
```bash
# Offline (plan)
python3 -m cli simulate --dry-run --mode SWING --symbols BTCUSDT

# Online (real)
python3 -m cli simulate --mode SWING --symbols BTCUSDT
```

### `build-dataset`
Assemble the feature matrix and label vector from backfilled data.

**Examples:**
```bash
python3 -m cli build-dataset --dry-run
python3 -m cli build-dataset
```

### `train`
Train the model.  **Gated** — refuses to run without `--force`.

**Options:**

| Option    | Description                   |
|-----------|-------------------------------|
| `--force` | Override the training gate    |

**Examples:**
```bash
python3 -m cli train --dry-run          # plan with gate message
python3 -m cli train --dry-run --force  # plan without gate message
python3 -m cli train                    # real mode → refused (gate)
python3 -m cli train --force            # real mode with gate bypass
```

### `wfv`
Run walk-forward validation.  **Gated** — requires a trained model.

**Examples:**
```bash
python3 -m cli wfv --dry-run    # plan with gate message
python3 -m cli wfv              # real mode → refused (gate)
```

### `report`
Generate a pipeline report aggregating results.

**Examples:**
```bash
python3 -m cli report --dry-run
python3 -m cli report
```

### `pipeline`
Run the complete end-to-end pipeline.  Each step runs sequentially; the
pipeline halts at the first failure.

```bash
python3 -m cli pipeline --dry-run  # plan every step
python3 -m cli pipeline            # execute full pipeline
```

---

### `validate-storage`
Validate market data storage integrity (Parquet + SHA-256 + catalog).

**Options:**

| Option        | Description                | Example                  |
|---------------|----------------------------|--------------------------|
| `--data-dir`  | Root data directory        | `--data-dir data`        |
| `--file`      | Validate a single file     | `--file data/raw/...`    |
| `--catalog-only` | Run only catalog query tests | `--catalog-only`      |
| `--quiet`     | Only print errors          | `--quiet` or `-q`        |

**Examples:**
```bash
# Full integrity scan
PYTHONPATH=. python3 scripts/validate_storage_integrity.py

# Single file
PYTHONPATH=. python3 scripts/validate_storage_integrity.py --file data/raw/BTCUSDT/BTCUSDT_1h_1700000000000_1700086400000.parquet

# Catalog queries only
PYTHONPATH=. python3 scripts/validate_storage_integrity.py --catalog-only
```

Exit code 0 = all checks passed; exit code 1 = one or more checks failed.

---

## Distinguishing Offline vs Online

| Mode   | `--dry-run` | `.env` required | Network access | What happens                 |
|--------|-------------|-----------------|----------------|------------------------------|
| Offline| Yes         | No              | No             | Prints plan, exits 0        |
| Online | No          | Yes             | Yes            | Executes the real operation  |

Most commands are **not yet implemented** in real mode.  They emit a message
telling you to use `--dry-run` for now.
