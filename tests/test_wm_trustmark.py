"""Optional TrustMark image backend (P2-05).

The packing, tag and MAC logic is tested everywhere with a fake model. The
tests marked ``trustmark`` run the real model and skip when the extra isn't
installed (the "trustmark" CI job installs it).
"""
from __future__ import annotations

import io
import json
import os

import numpy as np
import pytest
from PIL import Image

import gamefixture as gf
from indieward import check, cli, payload as pl, registry, verify, wm_trustmark
from indieward.vault import Vault

URL = "https://teststudio.itch.io/lantern-moth"


def _vault(root, monkeypatch, name="Lantern Moth"):
    v = Vault.init(root, name, "Test Studio", "dev@teststudio.example")
    code = v.project()["verify_code"]
    page = f'<div class="formatted_description">{code}</div><div class="game_comments_widget"></div>'
    monkeypatch.setattr(verify, "http_get", lambda url, timeout=20.0: (200, page.encode()))
    verify.verify_page(v, "itch", URL)
    return v


def _art(path, seed=7, size=512):
    gf._art(seed, size=size).convert("RGB").save(path)
    return path


class FakeTM:
    """Stands in for the TrustMark model: remembers the last secret, returns it on decode."""

    def __init__(self):
        self.secret, self.found = "", False

    def encode(self, img, bits, MODE="binary"):
        assert MODE == "binary" and len(bits) == 68
        self.secret, self.found = bits, True
        return img.copy()

    def decode(self, img, MODE="binary"):
        return self.secret, self.found, 2


@pytest.fixture
def fake_tm(monkeypatch):
    tm = FakeTM()
    monkeypatch.setattr(wm_trustmark, "_TM", tm)
    return tm


def test_packing_is_payload_then_tag():
    p = (0x12345_67890 << 24) | 0xABCDEF
    bits = wm_trustmark._bits(p)
    assert len(bits) == 68 and bits.endswith(wm_trustmark.TAG) and int(bits[:64], 2) == p


def test_unknown_backend_rejected(tmp_path, monkeypatch):
    v = _vault(tmp_path / "game", monkeypatch)
    with pytest.raises(ValueError, match="backend"):
        registry.register_file(v, _art(tmp_path / "a.png"), backend="nope")


def test_missing_extra_gives_install_hint(tmp_path, monkeypatch):
    import builtins

    real_import = builtins.__import__

    def no_trustmark(name, *a, **k):
        if name == "trustmark" or name.startswith("trustmark."):
            raise ImportError("no trustmark")
        return real_import(name, *a, **k)

    monkeypatch.setattr(wm_trustmark, "_TM", None)
    monkeypatch.setattr(builtins, "__import__", no_trustmark)
    v = _vault(tmp_path / "game", monkeypatch)
    with pytest.raises(wm_trustmark.Unavailable, match=r"indieward\[trustmark\]"):
        registry.register_path(v, _art(tmp_path / "a.png"), backend="trustmark")
    assert registry.assets(v) == []  # nothing half-registered


def test_register_and_detect_with_fake_model(tmp_path, monkeypatch, fake_tm, capsys):
    v = _vault(tmp_path / "game", monkeypatch)
    src = _art(tmp_path / "hero.png")
    assert cli.main(["-C", str(tmp_path / "game"), "--json", "register", str(src), "--backend", "trustmark",
                     "--out", str(tmp_path / "out")]) == 0
    res = json.loads(capsys.readouterr().out)
    row = registry.assets(v, "image")[0]
    assert row["wm_backend"] == wm_trustmark.BACKEND and row["ref_path"] is None
    assert int(fake_tm.secret[:64], 2) == int(row["wm_payload"], 16)
    assert "hero.png" in json.dumps(res)

    d = cli.detect_file(v, tmp_path / "out" / "hero.png")
    assert d["detected"] and d["matches"][0]["mac_ok"] and d["matches"][0]["registered"] == "hero.png"


def test_wrong_tag_or_foreign_key_is_not_a_hit(tmp_path, monkeypatch, fake_tm):
    v = _vault(tmp_path / "game", monkeypatch)
    registry.register_file(v, _art(tmp_path / "hero.png"), out_dir=tmp_path / "out", backend="trustmark")
    rows = registry.assets(v, "image")
    img = Image.open(tmp_path / "out" / "hero.png")
    assert wm_trustmark.matches(img, v.mac_key(), rows)

    good = fake_tm.secret
    fake_tm.secret = good[:64] + "0011"  # a TrustMark from another tool: wrong tag
    assert wm_trustmark.decode_image(img) is None and not wm_trustmark.matches(img, v.mac_key(), rows)

    fake_tm.secret = good
    other = _vault(tmp_path / "other", monkeypatch, "Other Game")
    got = wm_trustmark.read(img, other.mac_key())
    assert got and not got["genuine"]  # anyone can read the ID; only the owner's key confirms it
    assert got["record"] == pl.fmt(rows[0]["record_id"])

    fake_tm.found = False
    assert wm_trustmark.read(img, v.mac_key()) is None


def test_check_report_lists_blind_hit(tmp_path, monkeypatch, fake_tm):
    v = _vault(tmp_path / "game", monkeypatch)
    registry.register_file(v, _art(tmp_path / "hero.png"), out_dir=tmp_path / "out", backend="trustmark")
    res = check.run(v, [tmp_path / "out" / "hero.png"])
    report = json.loads(open(res["report_json"], encoding="utf-8").read())
    assert [w["backend"] for w in report["watermarks"]] == [wm_trustmark.BACKEND]
    html = open(res["report_html"], encoding="utf-8").read()
    assert "blind read, MAC verified" in html and "cannot show whether an AI was used" in html


def test_check_says_when_trustmark_marks_were_not_checked(tmp_path, monkeypatch, fake_tm):
    v = _vault(tmp_path / "game", monkeypatch)
    registry.register_file(v, _art(tmp_path / "hero.png"), out_dir=tmp_path / "out", backend="trustmark")

    def gone():
        raise wm_trustmark.Unavailable('the TrustMark backend needs: pip install "indieward[trustmark]"')

    monkeypatch.setattr(wm_trustmark, "_tm", gone)
    res = check.run(v, [tmp_path / "out" / "hero.png"])
    report = json.loads(open(res["report_json"], encoding="utf-8").read())
    assert report["watermarks"] == [] and "weren't checked" in report["watermark_note"]
    assert "Not checked:" in open(res["report_html"], encoding="utf-8").read()


def test_other_schema_is_not_a_hit(tmp_path, monkeypatch, fake_tm):
    v = _vault(tmp_path / "game", monkeypatch)
    registry.register_file(v, _art(tmp_path / "hero.png"), out_dir=tmp_path / "out", backend="trustmark")
    monkeypatch.setattr(fake_tm, "decode", lambda img, MODE="binary": (fake_tm.secret, True, 1))
    assert wm_trustmark.decode_image(Image.open(tmp_path / "out" / "hero.png")) is None


# --- real model --------------------------------------------------------------

def _need_trustmark():
    """Skip without the extra, except in the CI job that installs it (INDIEWARD_REQUIRE_TRUSTMARK=1)."""
    if os.environ.get("INDIEWARD_REQUIRE_TRUSTMARK") == "1":
        import trustmark  # noqa: F401  (fail loudly instead of skipping)
    else:
        pytest.importorskip("trustmark")


def _jpeg(img, q):
    b = io.BytesIO()
    img.convert("RGB").save(b, "JPEG", quality=q)
    return Image.open(io.BytesIO(b.getvalue()))


@pytest.mark.trustmark
def test_real_trustmark_survives_jpeg_and_resize(tmp_path, monkeypatch):
    _need_trustmark()
    monkeypatch.setattr(wm_trustmark, "_TM", None)
    v = _vault(tmp_path / "game", monkeypatch)
    r = registry.register_file(v, _art(tmp_path / "hero.png"), out_dir=tmp_path / "out", backend="trustmark")
    assert r["quality"]["psnr_db"] > 38
    rows = registry.assets(v, "image")
    marked = Image.open(tmp_path / "out" / "hero.png")
    small = marked.resize((marked.width // 2, marked.height // 2), Image.Resampling.LANCZOS)
    for img in (marked, _jpeg(marked, 75), small):
        assert wm_trustmark.matches(img, v.mac_key(), rows)

    # the unmarked original carries nothing the owner's key accepts
    assert not wm_trustmark.matches(Image.open(tmp_path / "hero.png"), v.mac_key(), rows)


@pytest.mark.trustmark
def test_real_trustmark_keeps_alpha(tmp_path, monkeypatch):
    _need_trustmark()
    monkeypatch.setattr(wm_trustmark, "_TM", None)
    v = _vault(tmp_path / "game", monkeypatch)
    rgba = np.dstack([np.asarray(gf._art(3, size=256).convert("RGB")), np.full((256, 256), 180, np.uint8)])
    Image.fromarray(rgba, "RGBA").save(tmp_path / "sprite.png")
    registry.register_file(v, tmp_path / "sprite.png", out_dir=tmp_path / "out", backend="trustmark")
    out = Image.open(tmp_path / "out" / "sprite.png")
    assert out.mode == "RGBA" and np.all(np.asarray(out)[..., 3] == 180)
