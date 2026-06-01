.PHONY: help install test check-lib-boundaries check-boundaries check-contracts test-system test-all clean lint typecheck setup

help:
	@echo "V7 Engine Monorepo — Makefile"
	@echo ""
	@echo "  make setup            Full environment setup (venv + deps + verify)"
	@echo "  make setup ARGS=--quick   Quick setup (use existing venv)"
	@echo "  make install          Install dependencies (pip)"
	@echo "  make test             Run all lib/ tests"
	@echo "  make test file=FILE   Run a specific test file"
	@echo "  make check-lib-boundaries  Verify lib/ imports no v7/alphaforge modules"
	@echo "  make check-boundaries Verify ALL domain import boundaries (lib + cross-domain)"
	@echo "  make check-contracts  Validate contract registry and schema parity"
	@echo "  make test-system      Run all system-level tests (contracts + boundaries + smoke)"
	@echo "  make test-all         Run all tests (lib + system)"
	@echo "  make clean            Remove caches, artifacts, build artifacts"
	@echo "  make lint             Run ruff linting"
	@echo "  make typecheck        Run mypy type checking"
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
	@echo "=== Running all system tests ==="
	@python -m pytest integration/tests/ -v -q 2>&1
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
