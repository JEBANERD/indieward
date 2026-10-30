"""Web: trap markers survive a Vite production build (minify + tree-shaking)."""
from __future__ import annotations

import json
import subprocess

import pytest

from helpers import copy_snippets, need, verified_vault

from indieward import registry, traps

pytestmark = pytest.mark.engine


def test_traps_survive_vite_build(tmp_path, monkeypatch):
    npm = need("npm")
    v = verified_vault(tmp_path / "vault", monkeypatch)
    t = traps.generate(v, "web test", "web")
    proj = tmp_path / "site"
    (proj / "src").mkdir(parents=True)
    copy_snippets(v, t["build_id"], proj / "src")
    # Vite serves public/ from the project root
    (proj / "src" / "public").rename(proj / "public")
    js = next((proj / "src").rglob("*.js"))
    rel = js.relative_to(proj / "src").as_posix()
    (proj / "src" / "main.js").write_text(
        f'import "./{rel}";\ndocument.body.textContent = "hello";\n')
    (proj / "index.html").write_text('<!doctype html><html><body><script type="module" src="/src/main.js">'
                                     '</script></body></html>')
    (proj / "package.json").write_text(json.dumps({"name": "t", "private": True, "type": "module",
                                                   "scripts": {"build": "vite build"},
                                                   "devDependencies": {"vite": "^6"}}))
    subprocess.run([npm, "install", "--silent", "--no-audit", "--no-fund"], cwd=proj, check=True)
    subprocess.run([npm, "run", "build", "--silent"], cwd=proj, check=True)
    res = registry.register_build(v, t["build_id"], proj / "dist")
    # the JS bundle alone (without public/) must still carry core + build traps
    js_only = tmp_path / "js_only"
    js_only.mkdir()
    for f in (proj / "dist" / "assets").glob("*.js"):
        (js_only / f.name).write_bytes(f.read_bytes())
    r2 = traps.verify_build(v, t["build_id"], js_only)
    assert res["ok"], res
    assert r2["ok"], r2


def test_injected_json_traps_survive_vite_build(tmp_path, monkeypatch):
    """P2-09: traps injected into the game's own strings.json, imported whole, survive minify + tree-shaking."""
    from indieward import inject

    npm = need("npm")
    v = verified_vault(tmp_path / "vault", monkeypatch)
    t = traps.generate(v, "web inject test", "web")
    proj = tmp_path / "site"
    (proj / "src").mkdir(parents=True)
    strings = proj / "src" / "strings.json"
    strings.write_text(json.dumps({"title": "Lantern Moth", "play": "Play", "quit": "Quit"}, indent=2))
    inject.apply(v, t["build_id"], strings)
    for bak in (proj / "src").glob("*.bak"):
        bak.unlink()
    # Look strings up by key at runtime, as localization code does. Fixed property reads (strings.title)
    # let Rollup drop every unused key, real ones included.
    (proj / "src" / "main.js").write_text(
        'import strings from "./strings.json";\nconst t = (key) => strings[key] ?? key;\n'
        'document.body.textContent = t(document.body.dataset.key || "title");\n')
    (proj / "index.html").write_text('<!doctype html><html><body><script type="module" src="/src/main.js">'
                                     '</script></body></html>')
    (proj / "package.json").write_text(json.dumps({"name": "t", "private": True, "type": "module",
                                                   "scripts": {"build": "vite build"},
                                                   "devDependencies": {"vite": "^6"}}))
    subprocess.run([npm, "install", "--silent", "--no-audit", "--no-fund"], cwd=proj, check=True)
    subprocess.run([npm, "run", "build", "--silent"], cwd=proj, check=True)
    r = traps.verify_build(v, t["build_id"], proj / "dist")
    assert r["ok"], r
