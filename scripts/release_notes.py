"""Release notes for a tag, checked against the package version.

    python scripts/release_notes.py v0.1.0 > notes.md

Fails (exit 1, message on stderr) when the tag isn't ``v<version>`` for the
version in pyproject.toml, or when CHANGELOG.md has no ``## [<version>]``
section with something in it. The release workflow runs this before it builds
anything, so a mistyped tag or a forgotten changelog entry stops the release.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def project_version(pyproject: str) -> str:
    m = re.search(r'(?m)^version\s*=\s*"([^"]+)"', pyproject)
    if not m:
        raise ValueError("no version in pyproject.toml")
    return m.group(1)


def section(changelog: str, version: str) -> str:
    """Body of the ``## [version]`` section, up to the next ``## `` heading."""
    m = re.search(rf"(?m)^## \[{re.escape(version)}\][^\n]*\n(.*?)(?=^## |\Z)", changelog, re.S)
    body = m.group(1).strip() if m else ""
    if not body:
        raise ValueError(f"CHANGELOG.md has no entries under '## [{version}]'; move the Unreleased notes there first")
    return body


def notes_for(tag: str, root: Path | None = None) -> str:
    root = root or ROOT
    version = project_version((root / "pyproject.toml").read_text(encoding="utf-8"))
    if tag != f"v{version}":
        raise ValueError(f"tag {tag!r} doesn't match pyproject.toml version {version!r} (expected 'v{version}')")
    return section((root / "CHANGELOG.md").read_text(encoding="utf-8"), version)


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: release_notes.py <tag>", file=sys.stderr)
        return 2
    try:
        print(notes_for(argv[0]))
    except ValueError as e:
        print(f"release_notes: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
