.PHONY: help install test check-lib-boundaries check-boundaries check-contracts test-system test-all clean lint typecheck setup

help:
	@echo "V7 Engine Monorepo — Makefile"
	@echo ""
	@echo "  make setup ARGS=--quick   Full environment setup (venv + deps + verify)"
	@echo "  make install          Install dependencies (pip)"
	@echo "  make test file=FILE   Run all lib/ tests"
	@echo "  make check-lib-boundaries  Verify lib/ imports no v7/alphaforge modules"
	@echo "  make check-boundaries Verify ALL domain import boundaries (lib + cross-domain)"
	@echo "  make check-contracts  Validate contract registry and schema parity"
	@echo "  make test-system      Run all system-level tests (contracts + boundaries + smoke)"
	@echo "  make test-all         Run all tests (lib + system)"
	@echo "  make clean            Remove caches, artifacts, build artifacts"
	@echo "  make lint             Run ruff linting"
	@echo "  make typecheck        Run mypy type checking"
	@echo ""
	@echo "--- Pipeline targets (TR-03-PIPELINE-CLI-MAKEFILE-RUNBOOK) ---"
	@echo "  make validate         Run contract + boundary checks + test suite"
	@echo "  make backfill         Download and backfill market data"
	@echo "  make simulate         Run simulation with cost model"
	@echo "  make build-dataset    Build training dataset"
	@echo "  make train            Train model (gated)"
	@echo "  make wfv              Walk-forward validation (gated)"
	@echo "  make report           Generate pipeline report"
	@echo "  make pipeline         End-to-end: validate > backfill > simulate > build-dataset > train > wfv > report"
	@echo "  make pipeline-v0.2    v0.2 profitability evidence pipeline (ISSUE #35)"
	@echo ""
	@echo "--- v0.30E — Real Data Baseline ---"
	@echo "  make data-health      	Verify + auto-repair downloaded Binance data"
	@echo "  make download         	Download Binance Vision data (BTC/ETH/SOL/BNB, 1h/4h, 2023-2026)"
	@echo "  make diagnostic      	Run v0.31A failure diagnostic report (read-only)"
	@echo "  make candidate       	Run candidate v0.2 (2-class + no confidence threshold)"
	@echo "  make test-training    	Health check > train > verify (SCALP, BTC/ETH/SOL/BNB)"
	@echo "  make test-training-full   Same + Optuna hyperparameter search"
	@echo "  make MODE=SWING ...   	Override trading mode"
	@echo "  make SYMBOLS=BTCUSDT  	Override symbol list"
	@echo "  make DRY_RUN=1 <tgt>  	Dry-run mode (echo what would run)"
	@echo ""

setup:
	@bash scripts/setup.sh $(ARGS)

install:
	pip install -q -U pip pytest requests mypy ruff

test:
ifdef file
	python -m pytest $(file) -v
else
	python -m pytest lib/tests/ -v
endif

check-lib-boundaries:
	@echo "Checking that lib/ does NOT import v7 or alphaforge..."
	@python -c "import lib; print('  lib/ importable ok')"
	@python -m pytest lib/tests/test_import_boundary.py -v -q 2>&1 | tail -3
	@echo "  Lib boundary check complete ok"

check-boundaries:
	@echo "=== Checking lib/ boundaries ==="
	@python -m pytest lib/tests/test_import_boundary.py -q 2>&1 | tail -3
	@echo ""
	@echo "=== Checking cross-domain boundaries ==="
	@python -m pytest integration/tests/test_cross_domain_boundaries.py -v -q 2>&1 | tail -10
	@echo ""
	@echo "  Boundary check complete ok"

check-contracts:
	@echo "=== Validating contract registry ==="
	@python -m pytest integration/tests/test_contract_registry.py -v -q 2>&1 | tail -10
	@echo ""
	@echo "=== Validating schema parity ==="
	@python -m pytest integration/tests/test_schema_parity.py -v -q 2>&1 | tail -10
	@echo ""
	@echo "  Contract check complete ok"

test-system:
	@echo "=== System tests (contracts + boundaries + smoke) ==="
	@python -m pytest integration/tests/ -v -q 2>&1
	@echo ""
	@echo "  System tests complete ok"

test-all:
	@echo "=== Running all lib/ tests ==="
	@python -m pytest lib/tests/ -v -q 2>&1
	@echo ""
	@echo "=== Running all system tests ==="
	@python -m pytest integration/tests/ -v -q 2>&1
	@echo ""
	@echo "  All tests complete ok"

clean:
	-rm -rf .pytest_cache
	-rm -rf __pycache__
	-find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	-find . -type f -name '*.pyc' -delete
	-rm -rf .mypy_cache
	-rm -rf .ruff_cache
	-rm -rf build/
	-rm -rf dist/
	-rm -rf *.egg-info
	@echo "  Cleanup complete ok"

lint:
	@echo "Running ruff..."
	@ruff check lib/ --ignore=E501,F401 2>/dev/null || ruff --help >/dev/null 2>&1 && ruff check lib/ --ignore=E501 || echo "  ruff not installed, skipping"
	@echo ""

typecheck:
	@echo "Running mypy..."
	@mypy lib/ --ignore-missing-imports --no-strict-optional 2>/dev/null || echo "  mypy not installed, skipping"
	@echo ""

# ====================================================================
# Pipeline targets — Plan TR-03-PIPELINE-CLI-MAKEFILE-RUNBOOK
# ====================================================================
# Each target logs its step, supports DRY_RUN=1, and runs the matching
# CLI subcommand with PYTHONPATH=alphaforge/src:.

PIPELINE_PYTHONPATH := alphaforge/src:.

.PHONY: backfill simulate build-dataset train wfv report pipeline validate pipeline-v0.2

backfill:
	@echo "=== TR-03-PIPELINE-CLI-MAKEFILE-RUNBOOK | backfill ==="; \
	if [ "$(DRY_RUN)" = "1" ]; then \
		echo "[DRY RUN] PYTHONPATH=$(PIPELINE_PYTHONPATH) python3 -m cli backfill"; \
	else \
		PYTHONPATH=$(PIPELINE_PYTHONPATH) python3 -m cli backfill; \
	fi

simulate:
	@echo "=== TR-03-PIPELINE-CLI-MAKEFILE-RUNBOOK | simulate ==="; \
	if [ "$(DRY_RUN)" = "1" ]; then \
		echo "[DRY RUN] PYTHONPATH=$(PIPELINE_PYTHONPATH) python3 -m cli simulate"; \
	else \
		PYTHONPATH=$(PIPELINE_PYTHONPATH) python3 -m cli simulate; \
	fi

build-dataset:
	@echo "=== TR-03-PIPELINE-CLI-MAKEFILE-RUNBOOK | build-dataset ==="; \
	if [ "$(DRY_RUN)" = "1" ]; then \
		echo "[DRY RUN] PYTHONPATH=$(PIPELINE_PYTHONPATH) python3 -m cli build-dataset"; \
	else \
		PYTHONPATH=$(PIPELINE_PYTHONPATH) python3 -m cli build-dataset; \
	fi

train:
	@echo "=== TR-03-PIPELINE-CLI-MAKEFILE-RUNBOOK | train ==="; \
	if [ "$(DRY_RUN)" = "1" ]; then \
		echo "[DRY RUN] PYTHONPATH=$(PIPELINE_PYTHONPATH) python3 -m cli train"; \
	else \
		PYTHONPATH=$(PIPELINE_PYTHONPATH) python3 -m cli train; \
	fi

wfv:
	@echo "=== TR-03-PIPELINE-CLI-MAKEFILE-RUNBOOK | wfv ==="; \
	if [ "$(DRY_RUN)" = "1" ]; then \
		echo "[DRY RUN] PYTHONPATH=$(PIPELINE_PYTHONPATH) python3 -m cli wfv"; \
	else \
		PYTHONPATH=$(PIPELINE_PYTHONPATH) python3 -m cli wfv; \
	fi

report:
	@echo "=== TR-03-PIPELINE-CLI-MAKEFILE-RUNBOOK | report ==="; \
	if [ "$(DRY_RUN)" = "1" ]; then \
		echo "[DRY RUN] PYTHONPATH=$(PIPELINE_PYTHONPATH) python3 -m cli report"; \
	else \
		PYTHONPATH=$(PIPELINE_PYTHONPATH) python3 -m cli report; \
	fi

validate:
	@echo "=== TR-03-PIPELINE-CLI-MAKEFILE-RUNBOOK | validate ==="; \
	if [ "$(DRY_RUN)" = "1" ]; then \
		echo "[DRY RUN] Would run: check-contracts + check-boundaries + test-system"; \
	else \
		$(MAKE) check-contracts && $(MAKE) check-boundaries && $(MAKE) test-system; \
	fi

pipeline:
	@echo "=== TR-03-PIPELINE-CLI-MAKEFILE-RUNBOOK | pipeline (end-to-end) ==="; \
	if [ "$(DRY_RUN)" = "1" ]; then \
		echo "[DRY RUN] PYTHONPATH=$(PIPELINE_PYTHONPATH) python3 -m cli pipeline"; \
		echo "[DRY RUN] Steps: validate -> backfill -> simulate -> build-dataset -> train -> wfv -> report"; \
	else \
		PYTHONPATH=$(PIPELINE_PYTHONPATH) python3 -m cli pipeline; \
	fi

pipeline-v0.2:
	@echo "=== ISSUE-35 | pipeline-v0.2 (profitability evidence pipeline) ==="; \
	if [ "$(DRY_RUN)" = "1" ]; then \
		PYTHONPATH=$(PIPELINE_PYTHONPATH) python3 -m cli v02 --dry-run $(ARGS); \
	else \
		PYTHONPATH=$(PIPELINE_PYTHONPATH) python3 -m cli v02 $(ARGS); \
	fi

# ====================================================================
# v0.30E — Real Data Baseline Pipeline (test-training profile)
# ====================================================================
# Targets:
#   make data-health          Verify + auto-repair downloaded data
#   make test-training        Full pipeline: health > train > verify
#   make test-training-full   Same + Optuna hyperparameter search
#
# Profile: configs/profiles/test-training.yaml
# Overrides: MODE=SCALP, SYMBOLS=BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT
# ====================================================================

.PHONY: data-health download test-training test-training-full
	candidate \
	diagnostic \

MODE ?= SCALP
SYMBOLS ?= BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT
TRAIN_PYTHONPATH := alphaforge/src:.
SCRIPTS_PYTHONPATH := .
DATA_DIR ?= data_lake

data-health:
	@echo "=== v0.30E | Data Health Check ==="
	@echo "  Mode:    $(MODE)"
	@echo "  Symbols: $(SYMBOLS)"
	@echo "  Data:    $(DATA_DIR)"
	@echo ""
	@if [ "$(DRY_RUN)" = "1" ]; then \
		echo "[DRY RUN] python3 scripts/health_check.py --symbols $(SYMBOLS) --data-dir $(DATA_DIR)"; \
	else \
		PYTHONPATH=$(SCRIPTS_PYTHONPATH) python3 scripts/health_check.py --symbols $(SYMBOLS) --data-dir $(DATA_DIR) && \
		echo "  OK: Data healthy"; \
	fi

candidate:
	@echo "=== v0.31E — Directional Candidate v0.2 ==="

	@PYTHONPATH=alphaforge/src:. python3 -m alphaforge.train \

		--mode SCALP \

		--symbols BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT \

		--folds 6 \

		--target 2-class \

		--output data/reports/train-results-CANDIDATE-V02.json



diagnostic:

	@echo "=== v0.31A | Real-Data Failure Diagnostic Report ==="

	@PYTHONPATH=alphaforge/src:. python3 scripts/diagnostic_v031.py



test-training: data-health
	@echo "=== v0.30E | Test Training ==="
	@echo "  Mode:    $(MODE)"
	@echo "  Symbols: $(SYMBOLS)"
	@echo ""
	@if [ "$(DRY_RUN)" = "1" ]; then \
		echo "[DRY RUN] PYTHONPATH=$(TRAIN_PYTHONPATH) python3 -m alphaforge.train --mode $(MODE) --symbols $(SYMBOLS) --folds 6"; \
	else \
		echo "[1/3] Running train..."; \
		PYTHONPATH=$(TRAIN_PYTHONPATH) python3 -m alphaforge.train \
			--mode $(MODE) \
			--symbols $(SYMBOLS) \
			--folds 6 \
			--output data/reports/train-results-$(MODE).json; \
		echo ""; \
		echo "[2/3] Verifying results..."; \
		PYTHONPATH=$(SCRIPTS_PYTHONPATH) python3 scripts/verify_training.py \
			data/reports/train-results-$(MODE).json; \
		echo ""; \
		echo "[3/3] DataPassport check..."; \
		PYTHONPATH=$(SCRIPTS_PYTHONPATH) python3 scripts/check_passport.py \
			--symbols $(SYMBOLS); \
		echo ""; \
		echo "=== Test-training complete ==="; \
	fi

download:
	@echo "=== v0.30E | Download Binance Vision Data ==="
	@echo "  Symbols:   $(SYMBOLS)"
	@echo "  Intervals: 1h, 4h"
	@echo "  Period:    2023-01 to 2026-12"
	@echo ""
	@if [ "$(DRY_RUN)" = "1" ]; then \
		echo "[DRY RUN] python3 scripts/download_binance.py --symbols $(SYMBOLS)"; \
	else \
		PYTHONPATH=alphaforge/src:. python3 scripts/download_binance.py --symbols $(SYMBOLS); \
	fi

test-training-full: data-health
	@echo "=== v0.30E | Test Training + Optuna ==="
	@echo "  Mode:    $(MODE)"
	@echo "  Symbols: $(SYMBOLS)"
	@echo ""
	@if [ "$(DRY_RUN)" = "1" ]; then \
		echo "[DRY RUN] Would run: Optuna + verify + baseline"; \
	else \
		echo "[1/3] Running Optuna study..."; \
		PYTHONPATH=$(TRAIN_PYTHONPATH) python3 -m alphaforge.train \
			--mode $(MODE) \
			--symbols $(SYMBOLS) \
			--folds 6 \
			--optuna \
			--output data/reports/train-results-optuna-$(MODE).json; \
		echo ""; \
		echo "[2/3] Verifying results..."; \
		PYTHONPATH=$(SCRIPTS_PYTHONPATH) python3 scripts/verify_training.py \
			data/reports/train-results-optuna-$(MODE).json; \
		echo ""; \
		echo "[3/3] Saving baseline snapshot..."; \
		cp data/reports/train-results-optuna-$(MODE).json \
		   data/reports/baseline-$(MODE)-$$(date +%Y%m%d).json; \
		echo "  Baseline saved: data/reports/baseline-$(MODE)-$$(date +%Y%m%d).json"; \
		echo ""; \
		echo "=== Test-training-full complete ==="; \
	fi

candidate:
	@echo "=== v0.31E — Directional Candidate v0.2 ==="
	PYTHONPATH=alphaforge/src:. python3 -m alphaforge.train --mode SCALP --symbols BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT --folds 6 --target 2-class --output data/reports/candidate-v02.json
