"""Release helper for .github/workflows/release.yml.

    python scripts/release_notes.py --version   # print the version; fail unless pyproject.toml and __version__ agree
    python scripts/release_notes.py 0.1.0       # print that version's CHANGELOG.md section; fail if there is none
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def version() -> str:
    pyproject = re.search(r'(?m)^version\s*=\s*"([^"]+)"', (ROOT / "pyproject.toml").read_text("utf-8")).group(1)
    module = re.search(r'(?m)^__version__\s*=\s*"([^"]+)"',
                       (ROOT / "src" / "indieward" / "__init__.py").read_text("utf-8")).group(1)
    if pyproject != module:
        raise SystemExit(f"pyproject.toml says {pyproject} but src/indieward/__init__.py says {module}")
    return pyproject


def section(ver: str, text: str | None = None) -> str:
    """The body under '## [ver]' (Keep a Changelog style), up to the next '## ' heading."""
    text = (ROOT / "CHANGELOG.md").read_text("utf-8") if text is None else text
    m = re.search(rf"(?ms)^## \[{re.escape(ver)}\][^\n]*\n(.*?)(?=^## |\Z)", text)
    if not m or not m.group(1).strip():
        raise SystemExit(f"CHANGELOG.md has no '## [{ver}]' section")
    return m.group(1).strip() + "\n"


if __name__ == "__main__":
    if sys.argv[1:] == ["--version"]:
        print(version())
    elif len(sys.argv) == 2:
        sys.stdout.write(section(sys.argv[1]))
    else:
        raise SystemExit(__doc__)
