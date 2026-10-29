"""Roblox: trap markers survive a Rojo build, in both XML (.rbxlx) and binary (.rbxl) place files."""
from __future__ import annotations

import json
import subprocess

import pytest
from helpers import copy_snippets, need, verified_vault

from indieward import registry, traps

pytestmark = pytest.mark.engine


@pytest.mark.parametrize("ext", ["rbxlx", "rbxl"])
def test_traps_survive_rojo_build(tmp_path, monkeypatch, ext):
    rojo = need("rojo")
    v = verified_vault(tmp_path / "vault", monkeypatch)
    t = traps.generate(v, f"rojo {ext}", "roblox")
    proj = tmp_path / "place"
    proj.mkdir()
    copy_snippets(v, t["build_id"], proj / "src")
    (proj / "default.project.json").write_text(json.dumps({
        "name": "TrapCheck",
        "tree": {"$className": "DataModel",
                 "ReplicatedStorage": {"$path": "src/ReplicatedStorage"},
                 "ServerStorage": {"$path": "src/ServerStorage"}},
    }))
    out = tmp_path / "build" / f"place.{ext}"
    out.parent.mkdir()
    subprocess.run([rojo, "build", str(proj), "--output", str(out)], check=True, timeout=300)
    res = registry.register_build(v, t["build_id"], out.parent)
    assert res["ok"], res
