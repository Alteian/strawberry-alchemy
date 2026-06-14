from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = ROOT / "pyproject.toml"
CHANGELOG = ROOT / "CHANGELOG.md"


def current_version() -> str:
    content = PYPROJECT.read_text()
    match = re.search(r'^version\s*=\s*"([^"]+)"', content, re.MULTILINE)
    if not match:
        print("Error: Could not find version in pyproject.toml")
        sys.exit(1)
    return match.group(1)


def bump_patch(version: str) -> str:
    major, minor, patch = _parse_semver(version)
    return f"{major}.{minor}.{patch + 1}"


def bump_minor(version: str) -> str:
    major, minor, _patch = _parse_semver(version)
    return f"{major}.{minor + 1}.0"


def bump_major(version: str) -> str:
    major, _minor, _patch = _parse_semver(version)
    return f"{major + 1}.0.0"


def _parse_semver(version: str) -> tuple[int, int, int]:
    base = version.split("-")[0].split("+")[0]
    try:
        major, minor, patch = base.split(".")
        return int(major), int(minor), int(patch)
    except ValueError:
        print(f"Error: Cannot parse version '{version}' as MAJOR.MINOR.PATCH")
        sys.exit(1)


def update_pyproject(new_version: str) -> None:
    content = PYPROJECT.read_text()
    updated = re.sub(
        r'^(version\s*=\s*)"[^"]*"',
        rf'\1"{new_version}"',
        content,
        count=1,
        flags=re.MULTILINE,
    )
    PYPROJECT.write_text(updated)
    print(f"  pyproject.toml -> {new_version}")


def update_changelog(old_version: str, new_version: str) -> None:
    content = CHANGELOG.read_text()
    old_ref = f"v{old_version}...HEAD"
    new_ref = f"v{new_version}...HEAD"
    if old_ref in content:
        content = content.replace(old_ref, new_ref)
        CHANGELOG.write_text(content)
        print(f"  CHANGELOG.md    -> Unreleased link updated ({old_ref} -> {new_ref})")
    else:
        print(f"  CHANGELOG.md    -> Could not find '{old_ref}' to update")


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1]
    old = current_version()

    if command == "patch":
        new = bump_patch(old)
    elif command == "minor":
        new = bump_minor(old)
    elif command == "major":
        new = bump_major(old)
    elif command == "set":
        if len(sys.argv) < 3:
            print("Error: 'set' requires a version argument, e.g.: set 1.0.0")
            sys.exit(1)
        new = sys.argv[2]
    else:
        print(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)

    print(f"\nBumping version: {old} → {new}\n")
    update_pyproject(new)
    update_changelog(old, new)
    print("\nDone. Review changes with: git diff\n")
    print("Next steps:")
    print("  1. Update CHANGELOG.md unreleased entries under the new version heading")
    print("  2. git add pyproject.toml CHANGELOG.md")
    print(f'  3. git commit -m "Release v{new}"')
    print(f'  4. git tag -a v{new} -m "Release v{new}"')
    print("  5. git push origin master --follow-tags")


if __name__ == "__main__":
    main()
