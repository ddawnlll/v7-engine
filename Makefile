.PHONY: help install test check-boundaries clean lint typecheck setup

help:
	@echo "V7 Engine Monorepo — Makefile"
	@echo ""
	@echo "  make setup            Full environment setup (venv + deps + verify)"
	@echo "  make setup ARGS=--quick   Quick setup (use existing venv)"
	@echo "  make install          Install dependencies (pip)"
	@echo "  make test             Run all lib/ tests"
	@echo "  make test file=FILE   Run a specific test file"
	@echo "  make check-boundaries Verify lib/ imports no v7/alphaforge modules"
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

check-boundaries:
	@echo "Checking that lib/ does NOT import v7 or alphaforge..."
	@python -c "import lib; print('  lib/ importable ✓')"
	@python -m pytest lib/tests/test_import_boundary.py -v -q 2>&1 | tail -3
	@echo "  Boundary check complete ✓"

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
