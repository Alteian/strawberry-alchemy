# Makefile — developer automation for strawberry-alchemy
#
# Conventions:
#   make help              - print this help
#   make <target>          - run a target
#   make test ARGS="-k x"  - forward args to pytest
#
# Tool versions come from mise.toml (local + CI via jdx/mise-action).
# We put mise shims/bin-paths on PATH and call `uv` directly — nesting
# `mise exec -- uv run pytest` has hung GitHub Actions postgres jobs.

BLUE   := \033[0;34m
GREEN  := \033[0;32m
YELLOW := \033[0;33m
BOLD   := \033[1m
NC     := \033[0m

ARGS ?=
MISE ?= mise

# Prefer mise-managed tools when available (no-op if mise missing / already activated).
MISE_PATHS := $(shell command -v $(MISE) >/dev/null 2>&1 && $(MISE) bin-paths 2>/dev/null | paste -sd: -)
ifneq ($(MISE_PATHS),)
export PATH := $(MISE_PATHS):$(PATH)
endif

UV := uv

.DEFAULT_GOAL := help

.PHONY: help sync install sync-frozen doctor check-versions \
        lint format typecheck test test-postgres docs docs-serve ci ci-strict build clean hooks \
        version bump-patch bump-minor bump-major bump-version

# =============================================================================
# Help
# =============================================================================

help: ## Show this help
	@printf "\n$(BOLD)$(BLUE)strawberry-alchemy$(NC)\n\n"
	@printf "Usage: $(BOLD)make <target> [ARGS=\"...\"]$(NC)\n\n"
	@awk ' \
		BEGIN {FS = ":.*?## "; in_section = 0} \
		/^# ====+/ { in_section = 1; next } \
		in_section && /^# [A-Z]/ { sub(/^# /, ""); printf "\n$(BOLD)$(GREEN)%s$(NC)\n", $$0; in_section = 0; next } \
		/^# ====+/ { in_section = 0 } \
		/^[a-zA-Z0-9_.-]+:.*## / { printf "  $(YELLOW)%-22s$(NC) %s\n", $$1, $$2 } \
	' $(MAKEFILE_LIST)
	@printf "\n$(BOLD)Examples:$(NC)\n"
	@printf "  mise install && make sync && make doctor\n"
	@printf "  make test ARGS=\"-k filter_or\"\n"
	@printf "  make ci\n\n"

# =============================================================================
# Project setup
# =============================================================================

sync: ## Install deps from lockfile
	$(UV) sync

install: sync ## Alias for sync

sync-frozen: ## Install exactly as locked (CI parity)
	$(UV) sync --frozen

hooks: ## Install pre-commit git hooks
	$(UV) run pre-commit install

doctor: ## Check local toolchain (mise pins in mise.toml)
	@command -v $(MISE) >/dev/null || { printf "$(YELLOW)FAIL: mise missing — install from https://mise.jdx.dev$(NC)\n"; exit 1; }
	@$(MISE) install
	@command -v $(UV) >/dev/null || { printf "$(YELLOW)FAIL: uv missing after mise install$(NC)\n"; exit 1; }
	@printf "$(GREEN)mise:$(NC)    " && $(MISE) --version
	@printf "$(GREEN)uv:$(NC)      " && $(UV) --version
	@printf "$(GREEN)Python:$(NC)  " && $(UV) run python -c 'import sys; print(sys.version.split()[0]); assert sys.version_info >= (3, 13), sys.version'
	@printf "$(GREEN)ruff:$(NC)    " && $(UV) run ruff --version
	@printf "$(GREEN)mypy:$(NC)    " && $(UV) run mypy --version
	@printf "$(GREEN)pytest:$(NC)  " && $(UV) run pytest --version
	@printf "$(GREEN)✔ toolchain ok$(NC)\n"

check-versions: ## Print toolchain versions
	@printf "$(GREEN)Python:$(NC) " && $(UV) run python --version
	@printf "$(GREEN)UV:$(NC)     " && $(UV) --version
	@printf "$(GREEN)Ruff:$(NC)   " && $(UV) run ruff --version
	@printf "$(GREEN)mypy:$(NC)   " && $(UV) run mypy --version
	@printf "$(GREEN)pytest:$(NC) " && $(UV) run pytest --version

# =============================================================================
# Quality
# =============================================================================

lint: ## Ruff check + format check
	$(UV) run ruff check src tests
	$(UV) run ruff format --check src tests

format: ## Auto-fix lint + format
	$(UV) run ruff check --fix src tests
	$(UV) run ruff format src tests

typecheck: ## mypy on src/
	$(UV) run mypy src/

test: ## pytest (ARGS=...); skips postgres by default
	$(UV) run pytest -v --cov=strawberry_alchemy --cov-report=term-missing --cov-fail-under=68 -m "not postgres" $(ARGS)

test-postgres: ## pytest postgres-marked tests (needs STRAWBERRY_ALCHEMY_PG_URL)
	$(UV) run pytest -v -m postgres $(ARGS)

docs: ## Build MkDocs site into site/
	$(UV) run mkdocs build --strict

docs-serve: ## Serve MkDocs locally
	$(UV) run mkdocs serve

ci: lint typecheck test build ## Full local CI (lint + mypy + test + build)

ci-strict: ci ## Alias for ci (kept for older docs/scripts)

build: ## Build distributable packages
	$(UV) build

clean: ## Remove caches and build artifacts
	rm -rf dist/ build/ *.egg-info/ .mypy_cache/ .ruff_cache/ .pytest_cache/ .coverage htmlcov/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

# =============================================================================
# Version
# =============================================================================

version: ## Print package version from pyproject.toml
	@$(UV) run python -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])"

_check_version:
	@if [ -z "$(VERSION)" ]; then \
		echo "Error: VERSION is required. Usage: make bump-version VERSION=X.Y.Z"; \
		exit 1; \
	fi

bump-patch: ## Bump patch version (0.1.0 → 0.1.1)
	@$(UV) run python scripts/bump_version.py patch

bump-minor: ## Bump minor version (0.1.0 → 0.2.0)
	@$(UV) run python scripts/bump_version.py minor

bump-major: ## Bump major version (0.1.0 → 1.0.0)
	@$(UV) run python scripts/bump_version.py major

bump-version: _check_version ## Bump to VERSION=X.Y.Z
	@$(UV) run python scripts/bump_version.py set $(VERSION)
