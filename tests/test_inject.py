"""traps inject: hide a build's trap values in the creator's own CSV / JSON / PO data."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent / "engines"))
from helpers import verified_vault  # noqa: E402

from indieward import cli, traps  # noqa: E402
from indieward.inject import InjectError, _key, _style, inject  # noqa: E402
from indieward.vault import NotVerified, Vault  # noqa: E402


@pytest.fixture
def vb(tmp_path, monkeypatch):
    v = verified_vault(tmp_path / "vault", monkeypatch)
    return v, traps.generate(v, "inject test", "generic")["build_id"]


def _check(v, b, path: Path, before: str):
    """Old content kept, traps found in the file alone."""
    after = path.read_bytes().decode("utf-8")
    old_lines = [l for l in before.splitlines() if l.strip()]
    new_lines = after.splitlines()
    assert all(l in new_lines or l + "," in new_lines for l in old_lines)
    res = traps.verify_build(v, b, path)
    assert res["ok"], res
    return after


def test_csv_rows_match_style(vb, tmp_path):
    v, b = vb
    f = tmp_path / "strings.csv"
    before = "key,en,fr\r\nmenu.start,Start,Commencer\r\nmenu.quit,Quit,Quitter\r\nhud.score,Score,Score\r\n"
    f.write_bytes(before.encode())
    r = inject(v, b, f, apply=True)  # key + language columns: a localization table, no flag needed
    assert "warning" not in r
    after = _check(v, b, f, before)
    assert after.startswith(before) and after.count("\r\n") == 7 and "\n\n" not in after
    assert all(k.startswith("menu.") and k == k.lower() for k in r["keys"])
    rows = [l.split(",") for l in after.splitlines()[4:]]
    assert all(len(row) == 3 and row[1] == row[2] for row in rows)


def test_csv_semicolon_and_no_trailing_newline(vb, tmp_path):
    v, b = vb
    f = tmp_path / "items.csv"
    before = "ID;Name;Desc\nITEM_SWORD;Sword;A sword\nITEM_SHIELD;Shield;A shield"
    f.write_bytes(before.encode())
    with pytest.raises(InjectError, match="--rows"):  # an item table: a game listing its items would show traps
        inject(v, b, f)
    assert f.read_bytes() == before.encode()
    r = inject(v, b, f, apply=True, rows=True)
    assert "loops over every row" in r["warning"]
    after = _check(v, b, f, before)
    assert ";" in after.splitlines()[-1] and all(k.startswith("ITEM_") and k.isupper() for k in r["keys"])


def test_json_flat_table(vb, tmp_path):
    v, b = vb
    f = tmp_path / "en.json"
    before = json.dumps({"menu.start": "Start", "menu.quit": "Quit", "menu.options": "Options"}, indent=2) + "\n"
    f.write_bytes(before.encode())
    r = inject(v, b, f, apply=True)
    after = _check(v, b, f, before)
    data = json.loads(after)
    assert list(data)[:3] == ["menu.start", "menu.quit", "menu.options"] and len(data) == 6
    assert all(k.startswith("menu.") for k in r["keys"]) and after.endswith("}\n")


def test_json_nested_picks_biggest_string_table(vb, tmp_path):
    v, b = vb
    f = tmp_path / "loc.json"
    src = {"version": 3, "strings": {"titleScreen": "Title", "pauseMenu": "Paused", "gameOver": "Game over"},
           "meta": {"lang": "en"}}
    before = json.dumps(src, indent=4)
    f.write_bytes(before.encode())
    r = inject(v, b, f, apply=True)
    _check(v, b, f, before)
    data = json.loads(f.read_text())
    assert data["version"] == 3 and data["meta"] == {"lang": "en"} and len(data["strings"]) == 6
    assert all(k[0].islower() and "_" not in k for k in r["keys"])  # camelCase like the table


def test_json_manifest_rows(vb, tmp_path):
    v, b = vb
    f = tmp_path / "manifest.json"
    src = [{"id": "sfx_jump", "path": "audio/jump.ogg", "volume": 0.8, "loop": False},
           {"id": "sfx_coin", "path": "audio/coin.ogg", "volume": 0.6, "loop": False}]
    before = json.dumps(src, indent=2)
    f.write_bytes(before.encode())
    with pytest.raises(InjectError, match="--rows"):  # games often loop over manifests: opt-in only
        inject(v, b, f)
    r = inject(v, b, f, apply=True, rows=True)
    assert "loops over every row" in r["warning"]
    _check(v, b, f, before)
    rows = json.loads(f.read_text())
    assert rows[:2] == src and len(rows) == 5
    assert all(set(x) == set(src[0]) and x["id"].startswith("sfx_") and x["loop"] is False for x in rows[2:])
    assert r["keys"] == [x["id"] for x in rows[2:]]


def test_json_minified_kept_minified(vb, tmp_path):
    v, b = vb
    f = tmp_path / "min.json"
    f.write_bytes('{"a.one":"One","a.two":"Two"}'.encode())
    inject(v, b, f, apply=True)
    assert "\n" not in f.read_text() and traps.verify_build(v, b, f)["ok"]


def test_json_with_windows_line_endings(vb, tmp_path):
    v, b = vb
    f = tmp_path / "en.json"
    before = json.dumps({"menu.start": "Start", "menu.quit": "Quit"}, indent=2).replace("\n", "\r\n") + "\r\n"
    f.write_bytes(before.encode())
    inject(v, b, f, apply=True)
    after = _check(v, b, f, before)
    assert "\n" not in after.replace("\r\n", "") and after.endswith("}\r\n")


def test_json_with_unusual_formatting_is_refused(vb, tmp_path):
    v, b = vb
    f = tmp_path / "odd.json"
    f.write_bytes('{ "a" : "One",\n      "b":"Two" }\n'.encode())
    with pytest.raises(InjectError, match="reformatting"):
        inject(v, b, f)


def test_po_key_style_and_context(vb, tmp_path):
    v, b = vb
    f = tmp_path / "fr.po"
    before = ('msgid ""\nmsgstr ""\n"Content-Type: text/plain; charset=UTF-8\\n"\n\n'
              'msgctxt "ui"\nmsgid "menu_start"\nmsgstr "Commencer"\n\n'
              'msgctxt "ui"\nmsgid "menu_quit"\nmsgstr "Quitter"\n')
    f.write_bytes(before.encode())
    r = inject(v, b, f, apply=True)
    after = _check(v, b, f, before)
    assert after.startswith(before) and after.count('msgctxt "ui"') == 5
    assert all(k.startswith("menu_") for k in r["keys"])


def test_po_source_text_style(vb, tmp_path):
    v, b = vb
    f = tmp_path / "de.po"
    before = 'msgid "Start game"\nmsgstr "Spiel starten"\n\nmsgid "Quit"\nmsgstr "Beenden"\n'
    f.write_bytes(before.encode())
    inject(v, b, f, apply=True)
    _check(v, b, f, before)


def test_dry_run_writes_nothing_then_apply_backs_up(vb, tmp_path):
    v, b = vb
    f = tmp_path / "en.json"
    before = json.dumps({"x.a": "A", "x.b": "B"}, indent=2)
    f.write_bytes(before.encode())
    r = inject(v, b, f)
    assert not r["applied"] and r["diff"].count("\n+") >= 3 and f.read_text() == before
    r = inject(v, b, f, apply=True)
    assert Path(r["backup"]).read_text() == before and ".indieward" in r["backup"]
    from indieward.check import _setting
    log = _setting(v, "injections", [])
    assert log[-1]["build_id"] == b and log[-1]["keys"] == r["keys"]
    with pytest.raises(InjectError, match="already holds"):
        inject(v, b, f)


def test_refuses_unverified_vault_and_unknown_types(vb, tmp_path):
    v, b = vb
    raw = Vault.init(tmp_path / "raw", "G", "C")
    f = tmp_path / "en.json"
    f.write_bytes('{"a": "A", "b": "B"}'.encode())
    with pytest.raises(NotVerified):
        inject(raw, b, f)
    (tmp_path / "x.yaml").write_text("a: b\n")
    with pytest.raises(InjectError, match="unsupported"):
        inject(v, b, tmp_path / "x.yaml")


def test_cli_shows_diff_and_needs_apply(vb, tmp_path, capsys):
    v, b = vb
    f = tmp_path / "en.json"
    before = json.dumps({"ui.ok": "OK", "ui.cancel": "Cancel"}, indent=2)
    f.write_bytes(before.encode())
    assert cli.main(["-C", str(tmp_path / "vault"), "traps", "inject",
                     "--build", b, "--into", str(f)]) == 0
    out = capsys.readouterr().out
    assert out.startswith("---") and "--apply" in out and f.read_text() == before


@pytest.mark.parametrize("header,ok", [
    (["keys", "en", "es"], True), (["key", "en_US", "pt-BR", "zh_Hans"], True), (["\ufeffid", "en"], True),
    (["ID", "Name", "Desc"], False), (["key", "en", "price"], False), (["en"], False),
])
def test_localization_csv_header(header, ok):
    from indieward.inject import _is_localization_csv

    assert _is_localization_csv(header) is ok


@pytest.mark.parametrize("keys,word,expect", [
    (["menu.start", "menu.quit"], "kabo_zeta", "menu.kabo_zeta"),
    (["ITEM_SWORD", "ITEM_SHIELD"], "kabo_zeta", "ITEM_KABO_ZETA"),
    (["titleScreen", "pauseMenu"], "kabo_zeta", "kaboZeta"),
    (["TitleScreen", "PauseMenu"], "kabo_zeta", "KaboZeta"),
    (["hello", "world"], "kabo_zeta", "kabo_zeta"),
])
def test_key_style(keys, word, expect):
    assert _key(_style(keys), word) == expect
