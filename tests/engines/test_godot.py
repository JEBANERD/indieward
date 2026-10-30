"""Godot 4: trap markers survive a headless export (runs where `godot` is on PATH)."""
from __future__ import annotations

import subprocess

import pytest

from helpers import copy_snippets, need, verified_vault

from indieward import registry, traps

pytestmark = pytest.mark.engine

PROJECT = """config_version=5

[application]
config/name="TrapCheck"
run/main_scene="res://main.tscn"

[autoload]
{name}="*res://{path}"
"""

MAIN = """[gd_scene format=3]

[node name="Main" type="Node"]
"""

# script_export_mode: 0 = text, 1 = binary tokens, 2 = compressed binary tokens (the 4.3+ default).
# Compressed tokens hide string constants, so IndieWard's guide tells creators to use 1 (or 0).
PRESETS = """[preset.0]

name="Linux"
platform="Linux"
runnable=true
export_filter="all_resources"
include_filter=""
exclude_filter=""
export_path="build/game.pck"
script_export_mode={mode}

[preset.0.options]
"""


def _export(tmp_path, monkeypatch, mode: int) -> dict:
    godot = need("godot")
    v = verified_vault(tmp_path / "vault", monkeypatch)
    t = traps.generate(v, "godot test", "godot")
    proj = tmp_path / "game"
    proj.mkdir()
    copy_snippets(v, t["build_id"], proj)
    gd = next(proj.rglob("*.gd")).relative_to(proj).as_posix()
    (proj / "project.godot").write_text(PROJECT.format(name="GameData", path=gd))
    (proj / "main.tscn").write_text(MAIN)
    (proj / "export_presets.cfg").write_text(PRESETS.format(mode=mode))
    (proj / "build").mkdir()
    subprocess.run([godot, "--headless", "--path", str(proj), "--import"], check=False, timeout=600)
    subprocess.run([godot, "--headless", "--path", str(proj), "--export-pack", "Linux", "build/game.pck"],
                   check=True, timeout=600)
    return registry.register_build(v, t["build_id"], proj / "build")


def test_traps_survive_godot_export(tmp_path, monkeypatch):
    res = _export(tmp_path, monkeypatch, mode=1)
    assert res["ok"], res


@pytest.mark.xfail(strict=False, reason="compressed binary tokens (script_export_mode=2) compress the script, "
                                        "so the build-tier trap strings may not be readable in the .pck")
def test_traps_with_compressed_script_tokens(tmp_path, monkeypatch):
    res = _export(tmp_path, monkeypatch, mode=2)
    assert res["ok"], res
