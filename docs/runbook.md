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
