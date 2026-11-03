# Contributing

Thanks for your interest in contributing! Here are the guidelines.

---

## Development Setup

Install [mise](https://mise.jdx.dev), then:

```bash
git clone https://github.com/Alteian/strawberry-alchemy.git
cd strawberry-alchemy
mise install          # Python + uv from mise.toml / mise.lock
make sync
make doctor
make hooks            # optional: install pre-commit
```

CI uses the same `mise.toml` pins and the same Make targets (`make lint`,
`make typecheck`, `make test`, …). Use `make help` for the full target list.

---

## Code Style

- We use **ruff** for linting and formatting (`make format` / `make lint`).
- Target Python **3.13+** — use modern syntax (`type[X]`, `X | Y`, generics with `[T]`).
- Type annotations are required — `make typecheck` runs mypy. Clearing existing
  mypy debt so CI can hard-gate is tracked in [docs/roadmap.md](docs/roadmap.md).

---

## Testing

```bash
make test
# or: make test ARGS="-k filter_or"
```

All new features and bug fixes must include tests. We use:
- `pytest` with `pytest-asyncio` for async tests
- `aiosqlite` for in-memory database integration tests
- `pytest-cov` in CI

---

## Making Changes

1. **Fork** the repo and create a feature branch from `master`.
2. **Make your changes** with tests.
3. Ensure the local CI pipeline is green:
   ```bash
   make ci
   ```
4. **Update `CHANGELOG.md`** — add your changes under the `[Unreleased]` section.

---

## Pull Requests

1. Push your branch and open a PR against `master`.
2. Write a clear PR description — what changed, why, and any breaking changes.
3. CI must be green before review.
4. A maintainer will review and merge.

---

## Release Process (for maintainers)

1. Update `CHANGELOG.md` — move entries from `[Unreleased]` to a new version heading.
2. Bump the version:
   ```bash
   make bump-patch    # 0.1.0 → 0.1.1 (bug fixes)
   make bump-minor    # 0.1.0 → 0.2.0 (new features)
   make bump-major    # 0.1.0 → 1.0.0 (breaking changes)
   ```
3. Review the diff with `git diff`.
4. Commit, tag, push:
   ```bash
   git add pyproject.toml src/ CHANGELOG.md
   git commit -m "Release v$(make version)"
   git tag -a "v$(make version)" -m "Release v$(make version)"
   git push origin master --follow-tags
   ```

CI handles the rest (build, test, publish to PyPI) when a `v*` tag is pushed.

---

## License

By contributing you agree that your contributions will be licensed under the MIT License.
