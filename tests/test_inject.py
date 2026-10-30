"""P2-09: `indieward traps inject` adds trap strings to the creator's own localization files."""
from __future__ import annotations

import csv
import difflib
import io
import json

import pytest

from indieward import cli, inject, traps, verify
from indieward.vault import NotVerified, Vault

URL = "https://enginetest.itch.io/trap-check"


@pytest.fixture
def vb(tmp_path, monkeypatch):
    v = Vault.init(tmp_path / "game", "Lantern Moth", "Test Studio")
    code = v.project()["verify_code"]
    page = f'<div class="formatted_description">{code}</div><div class="game_comments_widget"></div>'
    monkeypatch.setattr(verify, "http_get", lambda url, timeout=20.0: (200, page.encode()))
    verify.verify_page(v, "itch", URL)
    return v, traps.generate(v, "v1", "web")["build_id"]


def _strings(v, b):
    return [t["value"] for t in traps.records(v, b) if t["kind"] == "string"]


def _applied(v, b, path):
    before = path.read_bytes()
    plan = inject.plan(v, b, path)
    assert path.read_bytes() == before  # plan never writes
    r = inject.apply(v, b, path)
    after = path.read_bytes()
    ops = difflib.SequenceMatcher(None, before.decode("utf-8"), after.decode("utf-8"), autojunk=False).get_opcodes()
    assert {op for op, *_ in ops} <= {"equal", "insert"}  # existing text is never changed or removed
    assert r["backup"] and open(r["backup"], "rb").read() == before
    assert all(e["key"] in plan["diff"] for e in r["entries"])
    return after.decode("utf-8")


def test_csv_appends_rows_in_matching_style(vb, tmp_path):
    v, b = vb
    f = tmp_path / "strings.csv"
    f.write_bytes(("key,en,fr\nMENU_START,Start,Commencer\nMENU_QUIT,Quit,Quitter\n").encode("utf-8"))
    out = _applied(v, b, f)
    rows = list(csv.reader(io.StringIO(out)))
    assert rows[:3] == [["key", "en", "fr"], ["MENU_START", "Start", "Commencer"], ["MENU_QUIT", "Quit", "Quitter"]]
    new = rows[3:]
    assert len(new) == len(_strings(v, b))
    assert all(r[0].startswith("MENU_") and r[0].isupper() and r[1] == r[2] for r in new)
    assert {r[1] for r in new} == set(_strings(v, b))


def test_crlf_files_keep_crlf(vb, tmp_path):
    v, b = vb
    f = tmp_path / "en.json"
    f.write_bytes(b'{\r\n  "title": "Moth"\r\n}\r\n')
    out = _applied(v, b, f)
    assert "\r\n" in out and "\n" not in out.replace("\r\n", "")


def test_csv_without_key_column_is_refused(vb, tmp_path):
    v, b = vb
    f = tmp_path / "enemies.csv"
    f.write_bytes(("hp,speed,sprite\n10,2,bat.png\n").encode("utf-8"))
    with pytest.raises(inject.InjectError, match="key column"):
        inject.plan(v, b, f)


def test_json_flat_keeps_bytes_and_style(vb, tmp_path):
    v, b = vb
    f = tmp_path / "en.json"
    original = '{\n    "menu.start": "Start",\n    "menu.quit": "Quit"\n}\n'
    f.write_bytes((original).encode("utf-8"))
    out = _applied(v, b, f)
    assert out.startswith('{\n    "menu.start": "Start",\n    "menu.quit": "Quit",\n    "menu.')
    data = json.loads(out)
    assert data["menu.start"] == "Start" and data["menu.quit"] == "Quit"
    added = {k: x for k, x in data.items() if k not in ("menu.start", "menu.quit")}
    assert set(added.values()) == set(_strings(v, b)) and all(k.startswith("menu.") for k in added)


def test_json_per_locale_objects_and_one_line(vb, tmp_path):
    v, b = vb
    f = tmp_path / "strings.json"
    f.write_text('{"en": {"title": "Moth", "playButton": "Play"}, "fr": {"title": "Papillon", "playButton": "Jouer"}}',
                 encoding="utf-8")
    data = json.loads(_applied(v, b, f))
    for loc in ("en", "fr"):
        extra = {k: x for k, x in data[loc].items() if k not in ("title", "playButton")}
        assert set(extra.values()) == set(_strings(v, b))
        assert all(k[0].islower() and "_" not in k and "." not in k for k in extra)  # camelCase like the rest
    assert data["en"]["title"] == "Moth" and data["fr"]["playButton"] == "Jouer"


def test_json_list_is_refused(vb, tmp_path):
    v, b = vb
    f = tmp_path / "items.json"
    f.write_bytes(('[{"id": "sword", "dmg": 3}]').encode("utf-8"))
    with pytest.raises(inject.InjectError, match="list"):
        inject.plan(v, b, f)


def test_po_appends_entries(vb, tmp_path):
    v, b = vb
    f = tmp_path / "fr.po"
    original = 'msgid ""\nmsgstr ""\n"Language: fr\\n"\n\nmsgid "menu_start"\nmsgstr "Commencer"\n'
    f.write_bytes((original).encode("utf-8"))
    out = _applied(v, b, f)
    assert out.startswith(original)
    for value in _strings(v, b):
        assert f'msgstr "{value}"' in out
    assert out.count("msgid") == 2 + len(_strings(v, b))


def test_injected_file_carries_the_build_traps(vb, tmp_path):
    v, b = vb
    proj = tmp_path / "export"
    proj.mkdir()
    f = proj / "en.json"
    f.write_bytes(('{"title": "Moth", "play": "Play"}').encode("utf-8"))
    inject.apply(v, b, f)
    for bak in proj.glob("*.bak"):
        bak.unlink()
    r = traps.verify_build(v, b, proj)
    assert r["ok"], r


def test_twice_is_refused_and_unverified_vault_blocked(vb, tmp_path):
    v, b = vb
    f = tmp_path / "en.json"
    f.write_bytes(('{"title": "Moth"}').encode("utf-8"))
    inject.apply(v, b, f)
    with pytest.raises(inject.InjectError, match="already"):
        inject.plan(v, b, f)
    u = Vault.init(tmp_path / "other", "G", "C")
    with pytest.raises(NotVerified):
        inject.plan(u, b, f)


def test_cli_shows_diff_and_needs_apply(vb, tmp_path, capsys):
    v, b = vb
    f = tmp_path / "en.json"
    f.write_bytes(('{"title": "Moth"}').encode("utf-8"))
    assert cli.main(["-C", str(tmp_path / "game"), "traps", "inject", "--build", b, "--into", str(f)]) == 0
    out = capsys.readouterr().out
    assert out.startswith("---") and "Nothing written" in out and json.loads(f.read_text()) == {"title": "Moth"}
    assert cli.main(["-C", str(tmp_path / "game"), "traps", "inject", "--build", b, "--into", str(f), "--apply"]) == 0
    assert len(json.loads(f.read_text())) == 1 + len(_strings(v, b))
