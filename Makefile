# Makefile — developer automation for strawberry-alchemy
#
# Usage:
#   make lint               Run the linter + formatter check
#   make format             Auto-format code
#   make typecheck          Run mypy
#   make test               Run the test suite
#   make ci                 Full CI pipeline (lint → typecheck → test → build)
#   make build              Build distributable packages
#   make clean              Remove build artifacts
#   make version            Print the current version
#   make bump-patch         Bump patch version (0.1.0 → 0.1.1)
#   make bump-minor         Bump minor version (0.1.0 → 0.2.0)
#   make bump-major         Bump major version (0.1.0 → 1.0.0)
#   make bump-version VERSION=X.Y.Z   Bump to a specific version

.PHONY: lint format typecheck test ci build clean version \
        bump-patch bump-minor bump-major bump-version

# ── Development ───────────────────────────────────────────────────────────────

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff check --fix .
	uv run ruff format .

typecheck:
	uv run mypy src/

test:
	uv run pytest -v

ci: lint typecheck test build

build:
	uv build

clean:
	rm -rf dist/ build/ *.egg-info/ .mypy_cache/ .ruff_cache/ .pytest_cache/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

# ── Version ───────────────────────────────────────────────────────────────────

version:
	@uv run python -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])"

# ── Version management ────────────────────────────────────────────────────────

_check_version:
	@if [ -z "$(VERSION)" ]; then \
		echo "Error: VERSION is required. Usage: make bump-version VERSION=X.Y.Z"; \
		exit 1; \
	fi

bump-patch:
	@uv run python scripts/bump_version.py patch

bump-minor:
	@uv run python scripts/bump_version.py minor

bump-major:
	@uv run python scripts/bump_version.py major

bump-version: _check_version
	@uv run python scripts/bump_version.py set $(VERSION)
