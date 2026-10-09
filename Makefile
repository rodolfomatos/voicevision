# voicevision — Makefile
# Runs quality gates per AES protocol: make check
# Usage: make <target> [AES_LANGUAGE=python]

.PHONY: setup run test lint format build check doctor help clean \
        test-unit test-integration test-coverage \
        lint-ruff lint-mypy lint-bandit \
        format-ruff \
        docs-check code-check test-check lint-check \
        verify-implementation \
        install-precommit \
        aes-plan aes-build aes-verify aes-review aes-learn \
        aes-wake aes-sleep

# --- Configurable commands ---
AES_LANGUAGE ?= python
AES_LINT_RUFF ?= ruff check
AES_LINT_MYPY ?= mypy --strict
AES_LINT_BANDIT ?= bandit -r
AES_TEST_UNIT ?= pytest -m "not integration and not android and not slow" --cov=src/voicevision --cov-report=term-missing
AES_TEST_INTEGRATION ?= pytest -m "integration" --cov=src/voicevision --cov-report=term-missing --cov-append
AES_TEST_ALL ?= pytest --cov=src/voicevision --cov-report=term-missing --cov-fail-under=80
AES_FORMAT ?= ruff format
AES_BUILD ?= python -m build
AES_RUN ?= python -m src.main || python src/main.py

export AES_LANGUAGE AES_LINT_RUFF AES_LINT_MYPY AES_TEST_UNIT AES_FORMAT AES_BUILD AES_RUN

# --- Setup ---
setup:
	@echo "Setting up $(AES_LANGUAGE) environment..."
	@uv sync 2>/dev/null || pip install -e ".[dev]"

install-precommit:
	@pre-commit install
	@pre-commit install --hook-type commit-msg

# --- Run ---
run:
	@$(AES_RUN)

# --- Test ---
test: test-unit

test-unit:
	@$(AES_TEST_UNIT)

test-integration:
	@$(AES_TEST_INTEGRATION)

test-all:
	@$(AES_TEST_ALL)

test-coverage:
	@$(AES_TEST_ALL) --cov-report=html
	@echo "Coverage report: htmlcov/index.html"

# --- Lint ---
lint: lint-ruff lint-mypy lint-bandit

lint-ruff:
	@$(AES_LINT_RUFF) src tests

lint-mypy:
	@$(AES_LINT_MYPY) src

lint-bandit:
	@$(AES_LINT_BANDIT) src

# --- Format ---
format: format-ruff

format-ruff:
	@$(AES_FORMAT) src tests

# --- Build ---
build:
	@$(AES_BUILD)

# --- Check (AES Quality Gate) ---
check: docs-check code-check test-check lint-check
	@echo "✅ All quality gates passed"

docs-check:
	@test -f docs/VISION.md && grep -q "Problem" docs/VISION.md || (echo "VISION.md missing Problem section" && exit 1)
	@test -f docs/PERSONAS.md && grep -q "User" docs/PERSONAS.md || (echo "PERSONAS.md missing User section" && exit 1)
	@test -f docs/REQUIREMENTS.md && grep -q "Functional" docs/REQUIREMENTS.md || (echo "REQUIREMENTS.md missing Functional section" && exit 1)
	@test -f docs/ROADMAP.md && grep -q "Roadmap" docs/ROADMAP.md || (echo "ROADMAP.md missing content" && exit 1)

code-check:
	@test -d src/voicevision || (echo "src/voicevision not found" && exit 1)
	@! grep -R "TODO:" src/ tests/ 2>/dev/null || (echo "TODO comments found in source" && exit 1)
	@! grep -R "FIXME:" src/ tests/ 2>/dev/null || (echo "FIXME comments found in source" && exit 1)

test-check:
	@$(AES_TEST_UNIT) --cov-fail-under=80

lint-check:
	@$(AES_LINT_RUFF) src tests
	@$(AES_LINT_MYPY) src

# --- Verify Implementation (AES Phase 4) ---
verify-implementation:
	@bash scripts/verify-implementation.sh

# --- Doctor ---
doctor:
	@echo "=== Environment ==="
	@echo "Language: $(AES_LANGUAGE)"
	@echo "Python: $$(python --version 2>&1 || echo not-found)"
	@echo "uv: $$(uv --version 2>&1 || echo not-found)"
	@echo "ruff: $$(ruff --version 2>&1 || echo not-found)"
	@echo "mypy: $$(mypy --version 2>&1 || echo not-found)"
	@echo "pytest: $$(pytest --version 2>&1 || echo not-found)"
	@echo ""
	@echo "=== Optional Deps ==="
	@python3 -c "deps = ['httpx', 'llama_cpp', 'whisper_cpp', 'faster_whisper', 'piper', 'moondream', 'torch', 'cv2', 'chaquopy']; [print(f'  ✓ {d}') if __import__(d, fromlist=['']) else None for d in deps] if True else None"

# --- Clean ---
clean:
	@rm -rf build dist *.egg-info htmlcov .coverage .pytest_cache .mypy_cache .ruff_cache
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete 2>/dev/null || true

# --- AES Phase Delegation (for project mode) ---
aes-plan:
	@echo "Run: /aes-plan TXXX"

aes-build:
	@echo "Run: /aes-build TXXX"

aes-verify:
	@echo "Run: /aes-verify TXXX"

aes-review:
	@echo "Run: /aes-review TXXX"

aes-learn:
	@echo "Run: /aes-learn TXXX"

aes-wake:
	@echo "Loading context..."
	@make doctor
	@cat aes/INDEX.md 2>/dev/null || echo "No INDEX.md yet"
	@cat aes/kanban.md 2>/dev/null || echo "No kanban.md yet"

aes-sleep:
	@echo "Running sleep consolidation..."
	@bash ~/.config/opencode/skills/aes/scripts/aes-sleep.sh 2>/dev/null || echo "aes-sleep not installed"

# --- Help ---
help:
	@echo "voicevision — AES Commands:"
	@echo ""
	@echo "  Setup:"
	@echo "    make setup              Install deps (uv or pip)"
	@echo "    make install-precommit  Install git hooks"
	@echo ""
	@echo "  Development:"
	@echo "    make run                Run main entry point"
	@echo "    make test               Run unit tests (fast)"
	@echo "    make test-integration   Run integration tests (requires models)"
	@echo "    make test-all           Run all tests with coverage"
	@echo "    make test-coverage      HTML coverage report"
	@echo "    make lint               Run all linters"
	@echo "    make format             Format code"
	@echo "    make build              Build package"
	@echo ""
	@echo "  Quality Gates:"
	@echo "    make check              Full AES quality gate (REQUIRED before commit)"
	@echo "    make verify-implementation  Verify acceptance criteria"
	@echo ""
	@echo "  AES Project Mode:"
	@echo "    make aes-wake           Load context (start of session)"
	@echo "    make aes-sleep          Consolidate memory (end of session)"
	@echo ""
	@echo "  Maintenance:"
	@echo "    make doctor             Show environment status"
	@echo "    make clean              Remove build artifacts"