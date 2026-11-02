# Makefile — developer automation for strawberry-alchemy
#
# Conventions:
#   make help              - print this help
#   make <target>          - run a target
#   make test ARGS="-k x"  - forward args to pytest

BLUE   := \033[0;34m
GREEN  := \033[0;32m
YELLOW := \033[0;33m
BOLD   := \033[1m
NC     := \033[0m

ARGS ?=

.DEFAULT_GOAL := help

.PHONY: help sync install sync-frozen doctor check-versions \
        lint format typecheck test ci ci-strict build clean hooks \
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
	@printf "  make sync && make doctor\n"
	@printf "  make test ARGS=\"-k filter_or\"\n"
	@printf "  make ci\n\n"

# =============================================================================
# Project setup
# =============================================================================

sync: ## Install deps from lockfile
	uv sync

install: sync ## Alias for sync

sync-frozen: ## Install exactly as locked (CI parity)
	uv sync --frozen

hooks: ## Install pre-commit git hooks
	uv run pre-commit install

doctor: ## Check local toolchain
	@command -v uv >/dev/null || { printf "$(YELLOW)FAIL: uv missing$(NC)\n"; exit 1; }
	@printf "$(GREEN)uv:$(NC)      " && uv --version
	@printf "$(GREEN)Python:$(NC)  " && uv run python -c 'import sys; print(sys.version.split()[0]); assert sys.version_info >= (3, 13), sys.version'
	@printf "$(GREEN)ruff:$(NC)    " && uv run ruff --version
	@printf "$(GREEN)mypy:$(NC)    " && uv run mypy --version
	@printf "$(GREEN)pytest:$(NC)  " && uv run pytest --version
	@printf "$(GREEN)✔ toolchain ok$(NC)\n"

check-versions: ## Print toolchain versions
	@printf "$(GREEN)Python:$(NC) " && uv run python --version
	@printf "$(GREEN)UV:$(NC)     " && uv --version
	@printf "$(GREEN)Ruff:$(NC)   " && uv run ruff --version
	@printf "$(GREEN)mypy:$(NC)   " && uv run mypy --version
	@printf "$(GREEN)pytest:$(NC) " && uv run pytest --version

# =============================================================================
# Quality
# =============================================================================

lint: ## Ruff check + format check
	uv run ruff check src tests
	uv run ruff format --check src tests

format: ## Auto-fix lint + format
	uv run ruff check --fix src tests
	uv run ruff format src tests

typecheck: ## mypy on src/
	uv run mypy src/

test: ## pytest (ARGS=...)
	uv run pytest -v $(ARGS)

ci: lint test build ## Local CI pipeline (lint + test + build)

ci-strict: lint typecheck test build ## CI plus mypy (mypy still has known debt)

build: ## Build distributable packages
	uv build

clean: ## Remove caches and build artifacts
	rm -rf dist/ build/ *.egg-info/ .mypy_cache/ .ruff_cache/ .pytest_cache/ .coverage htmlcov/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

# =============================================================================
# Version
# =============================================================================

version: ## Print package version from pyproject.toml
	@uv run python -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])"

_check_version:
	@if [ -z "$(VERSION)" ]; then \
		echo "Error: VERSION is required. Usage: make bump-version VERSION=X.Y.Z"; \
		exit 1; \
	fi

bump-patch: ## Bump patch version (0.1.0 → 0.1.1)
	@uv run python scripts/bump_version.py patch

bump-minor: ## Bump minor version (0.1.0 → 0.2.0)
	@uv run python scripts/bump_version.py minor

bump-major: ## Bump major version (0.1.0 → 1.0.0)
	@uv run python scripts/bump_version.py major

bump-version: _check_version ## Bump to VERSION=X.Y.Z
	@uv run python scripts/bump_version.py set $(VERSION)
