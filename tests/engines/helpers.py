"""Shared setup for engine export tests: a verified vault without touching the network."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from indieward import traps, verify
from indieward.vault import Vault

URL = "https://enginetest.itch.io/trap-check"


def verified_vault(root: Path, monkeypatch) -> Vault:
    v = Vault.init(root, "Trap Check", "Engine Test")
    code = v.project()["verify_code"]
    page = f'<div class="formatted_description">{code}</div><div class="game_comments_widget"></div>'
    monkeypatch.setattr(verify, "http_get", lambda url, timeout=20.0: (200, page.encode()))
    verify.verify_page(v, "itch", URL)
    return v


def need(tool: str) -> str:
    path = shutil.which(tool)
    if not path:
        pytest.skip(f"{tool} not on PATH (runs in the engines CI workflow)")
    return path


def copy_snippets(v: Vault, build_id: str, dest: Path) -> None:
    """Copy the generated trap files into a project, never the README."""
    src = v.path("traps", build_id)
    for f in src.rglob("*"):
        if f.is_file() and not f.name.startswith("README_"):
            out = dest / f.relative_to(src)
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, out)
    _ = traps
