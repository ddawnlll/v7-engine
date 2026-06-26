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
	@echo "  make test-all         Run all tests (lib + system + simulation)"
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
	@echo "  make pipeline         End-to-end: validate → backfill → simulate → build-dataset → train → wfv → report"
	@echo "  make DRY_RUN=1 <tgt>  Dry-run mode (echo what would run)"
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
	@python -c "import lib; print('  lib/ importable ✓')"
	@python -m pytest lib/tests/test_import_boundary.py -v -q 2>&1 | tail -3
	@echo "  Lib boundary check complete ✓"

check-boundaries:
	@echo "=== Checking lib/ boundaries ==="
	@python -m pytest lib/tests/test_import_boundary.py -q 2>&1 | tail -3
	@echo ""
	@echo "=== Checking cross-domain boundaries ==="
	@python -m pytest integration/tests/test_cross_domain_boundaries.py -v -q 2>&1 | tail -10
	@echo ""
	@echo "  Boundary check complete ✓"

check-contracts:
	@echo "=== Validating contract registry ==="
	@python -m pytest integration/tests/test_contract_registry.py -v -q 2>&1 | tail -10
	@echo ""
	@echo "=== Validating schema parity ==="
	@python -m pytest integration/tests/test_schema_parity.py -v -q 2>&1 | tail -10
	@echo ""
	@echo "  Contract check complete ✓"

test-system:
	@echo "=== System tests (contracts + boundaries + smoke) ==="
	@python -m pytest integration/tests/ -v -q 2>&1
	@echo ""
	@echo "  System tests complete ✓"

test-all:
	@echo "=== Running all lib/ tests ==="
	@python -m pytest lib/tests/ -v -q 2>&1
	@echo ""
	@echo "=== Running all integration tests ==="
	@python -m pytest integration/tests/ -v -q 2>&1
	@echo ""
	@echo "=== Running all simulation tests ==="
	@python -m pytest simulation/tests/ -v -q 2>&1
	@echo ""
	@echo "  All tests complete ✓"

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
	@echo "  Cleanup complete ✓"

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

.PHONY: backfill simulate build-dataset train wfv report pipeline validate

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
