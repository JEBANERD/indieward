"""`indieward notice` (P2-10): visible copyright notices and the check's "notice removed" line."""
from __future__ import annotations

import json
import unicodedata

import pytest

from indieward import check, cli, notice
from indieward.vault import Vault


def _all_text(d) -> str:
    return json.dumps(d, ensure_ascii=False)


def test_build_all_rights_reserved():
    t = notice.build("Lantern Moth", "Test Studio", 2026, email="dev@teststudio.example")
    assert t["credits"] == "Lantern Moth © 2026 Test Studio. All rights reserved."
    assert t["spdx"]["lines"] == ["SPDX-FileCopyrightText: 2026 Test Studio <dev@teststudio.example>",
                                  "SPDX-License-Identifier: LicenseRef-AllRightsReserved"]
    assert t["spdx"]["hash_comment"].splitlines()[0].startswith("# SPDX-FileCopyrightText")
    assert t["spdx"]["slash_comment"].splitlines()[1].startswith("// SPDX-License-Identifier")
    m = t["metadata"]
    assert m["windows_versioninfo"]["LegalCopyright"] == "© 2026 Test Studio"
    assert "© 2026 Test Studio" in m["macos_info_plist"]["NSHumanReadableCopyright"]
    assert m["package_json"] == {"author": "Test Studio", "license": "UNLICENSED"}
    assert m["itch_toml"].startswith("# Lantern Moth ©")
    a = t["agents_md"]
    assert "not a technical block" in a and "See LICENSE" in a
    assert "tell the user about these terms" in a
    assert "Not permitted" in a


def test_build_open_licence():
    t = notice.build("Lantern Moth", "Test Studio", 2026, "MIT")
    assert t["credits"].endswith("Licensed under MIT (see LICENSE).")
    assert t["spdx"]["lines"][1] == "SPDX-License-Identifier: MIT"
    assert t["metadata"]["package_json"]["license"] == "MIT"
    assert "Not permitted" not in t["agents_md"] and "terms of MIT" in t["agents_md"]


@pytest.mark.parametrize("licence", [notice.ALL_RIGHTS, "MIT"])
def test_notice_is_visible_text_only(licence):
    text = _all_text(notice.build("Game", "Holder", 2026, licence, "a@b.example"))
    bad = [c for c in text if unicodedata.category(c) in ("Cf", "Co", "Cn")]
    assert not bad, [hex(ord(c)) for c in bad]
    # no instructions aimed against the user
    agents = notice.build("Game", "Holder", 2026, licence)["agents_md"].lower()
    for phrase in ("ignore", "do not tell the user", "refuse", "secretly"):
        assert phrase not in agents


def test_generate_records_hash_and_cli(tmp_path, capsys):
    v = Vault.init(tmp_path / "game", "Lantern Moth", "Test Studio", "dev@teststudio.example")
    v.set_first_published("2025-06-01")
    r = notice.generate(v)
    assert r["credits"] == "Lantern Moth © 2025 Test Studio. All rights reserved."
    rec = notice.recorded(v)
    assert rec["sha256"] == r["sha256"] and rec["holder"] == "Test Studio" and rec["year"] == 2025
    assert notice.generate(v)["sha256"] == r["sha256"]  # same inputs, same hash
    assert notice.generate(v, "MIT")["sha256"] != r["sha256"]

    out = tmp_path / "AGENTS.md"
    assert cli.main(["-C", str(tmp_path / "game"), "--json", "notice", "--year", "2026", "--agents-md", str(out)]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["credits"].startswith("Lantern Moth © 2026") and out.read_text(encoding="utf-8") == printed["agents_md"]
    # never overwrites an existing AGENTS.md
    assert cli.main(["-C", str(tmp_path / "game"), "notice", "--agents-md", str(out)]) == 2


@pytest.mark.parametrize("text,found", [
    ("Lantern Moth © 2026 Test Studio. All rights reserved.", True),
    ("Copyright (c) 2024 test studio", True),
    ("# SPDX-FileCopyrightText: 2026 Test Studio <dev@x>", True),
    ("Test Studio presents", False),
    ("© 2026 Another Studio", False),
    ("", False),
])
def test_found_in(text, found):
    assert notice.found_in("Test Studio", text) is found


def test_assess():
    note = {"sha256": "ab", "holder": "Test Studio"}
    assert notice.assess(None, "", True) is None
    gone = notice.assess(note, "func light_lamp():", has_work=True)
    assert gone["removed"] and not gone["found"] and "1202(b)" in gone["summary"]
    kept = notice.assess(note, "© 2026 Test Studio", has_work=True)
    assert kept["found"] and not kept["removed"]
    unrelated = notice.assess(note, "nothing here", has_work=False)
    assert not unrelated["removed"] and not unrelated["found"]


def test_collect_keeps_notices_that_similarity_filtering_drops(tmp_path):
    kept = tmp_path / "kept"
    kept.mkdir()
    (kept / "credits.txt").write_text("© 2026 Test Studio\n", encoding="utf-8")  # vendor-named and under 4 words
    (kept / "game.pck").write_bytes(b"\x00\x01Copyright 2026 Test Studio\x00\xff" * 2)  # short string in a binary
    s = check.collect([kept], notice_holder="Test Studio")
    try:
        hay = "\n".join(s.notice_text)
        assert notice.found_in("Test Studio", hay)
        assert len(s.notice_text) == 3
    finally:
        s.cleanup()

    gone = tmp_path / "gone"
    gone.mkdir()
    (gone / "main.gd").write_text("func light_lamp():\n    pass\n")
    s = check.collect([gone], notice_holder="Test Studio")
    try:
        assert s.notice_text == [] and not notice.found_in("Test Studio", "\n".join(s.notice_text))
    finally:
        s.cleanup()
