"""End-to-end test of the MVP on a synthetic game, a planted clone and an unrelated game.

Maps to the "Done Means" list:
- verified creator registers assets; watermarks in an image, an audio clip and a video; traps in the build
- watermarks survive a screenshot and re-encodes
- a timestamped, signed proof-of-ownership certificate is exported
- fingerprints and trap records are stored for every registered build
- the planted clone scores high with traps detected; an unrelated game scores low with no traps
- every report labels categories Strong / Supporting / Weak and flags mechanics-only reports
- a takedown package with a pre-addressed draft per store (Steam, itch.io, Roblox), all attachments, nothing sent
- an unverified account cannot register assets
"""
from __future__ import annotations

import email
import io
import json
import re
import subprocess
import zipfile
from email import policy
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

import gamefixture as gf
from indieward import check, certificate, cli, mediaio, package, registry, timestamp, traps, verify
from indieward.vault import NotVerified, Vault

ITCH_URL = "https://teststudio.itch.io/lantern-moth"
IMPOSTOR_URL = "https://teststudio.itch.io/lantern-moth-2"
IMPOSTOR_CODE = [""]
SRC = Path(__file__).resolve().parents[1] / "src" / "indieward"


@pytest.fixture(scope="session")
def world(tmp_path_factory, local_tsa):
    mp = pytest.MonkeyPatch()
    root = tmp_path_factory.mktemp("world")
    orig = root / "LanternMoth"
    gf.make_original(orig)
    v = Vault.init(orig, "Lantern Moth", "Test Studio", "dev@teststudio.example")
    code = v.project()["verify_code"]

    def fake_get(url, timeout=20.0):
        if url == ITCH_URL:
            page = (f"<html><head><title>Lantern Moth by Test Studio</title></head><body>"
                    f"<div class=\"formatted_description user_formatted\"><p>A cozy night game.</p><p>{code}</p></div>"
                    f"<div class=\"more_information_toggle\">More information</div>"
                    f"<div class=\"game_comments_widget\"><div class=\"community_post_body\">nice!</div></div></body></html>")
            return 200, page.encode()
        if url == IMPOSTOR_URL:
            # the real creator's page, with the impostor's code posted as a comment
            page = (f"<html><body><div class=\"formatted_description\"><p>A cozy night game.</p></div>"
                    f"<div class=\"game_comments_widget\"><div class=\"community_post_body\">{IMPOSTOR_CODE[0]}</div></div>"
                    f"</body></html>")
            return 200, page.encode()
        return 404, b""

    mp.setattr(verify, "http_get", fake_get)
    mp.setattr(timestamp, "http_post", local_tsa["post"])

    # before verification nothing can be registered
    with pytest.raises(NotVerified):
        registry.register_file(v, orig / "art" / "moth_0.png")
    vres = verify.verify_page(v, "itch", ITCH_URL)
    v.set_first_published("2026-10-01")
    check.set_setting(v, "mechanics", ["lamp", "chain", "bell", "night cycle", "glow"])

    reg = []
    reg += registry.register_path(v, orig / "art", "art")
    reg += registry.register_path(v, orig / "ui", "ui")
    reg += registry.register_path(v, orig / "text", "text")
    reg += registry.register_path(v, orig / "src", "code")
    reg += registry.register_path(v, orig / "audio", "audio")
    reg += registry.register_path(v, orig / "video", "video")

    tr = traps.generate(v, "v1.0 itch release", "godot")
    snippets = Path(tr["snippets"])
    build_zip = gf.export_build(orig, snippets, root / "LanternMoth_v1.zip", art_dir=orig / "indieward_out")
    build = registry.register_build(v, tr["build_id"], build_zip)
    cert = certificate.issue(v)

    clone_zip = gf.make_clone(orig, build_zip, root / "clone")
    clone_page = root / "clone" / "store.html"
    clone_page.write_text(
        "<html><head><meta property='og:title' content='Lantern Moths: Night Flight'></head><body>"
        "<p>Light every lamp before the bell tower rings! Chain lamps, keep your glow, survive the night cycle.</p>"
        "</body></html>")
    unrelated_zip = gf.make_unrelated(root / "unrelated")
    mech_page = root / "mech.html"
    mech_page.write_text("<html><head><title>Wick Runner</title></head><body><p>Keep your glow up, chain lamp after "
                         "lamp, and beat the night cycle before the bell sounds.</p></body></html>")

    c_clone = check.run(v, [clone_zip], page_file=clone_page)
    c_unrel = check.run(v, [unrelated_zip], suspect_name="Crystal Quarry")
    c_mech = check.run(v, page_file=mech_page)
    w = {"root": root, "orig": orig, "vault": v, "reg": reg, "verify": vres, "traps": tr, "build": build,
         "build_zip": build_zip, "cert": cert, "clone": c_clone, "unrelated": c_unrel, "mech": c_mech,
         "tsa": local_tsa, "mp": mp}
    yield w
    mp.undo()


def _report(w, key):
    return json.loads(Path(w[key]["report_json"]).read_text())


# --- verification gate ---------------------------------------------------------

def test_unverified_account_cannot_register_or_file(tmp_path):
    (tmp_path / "a.png").write_bytes(b"")
    gf._art(1).save(tmp_path / "a.png")
    v = Vault.init(tmp_path, "Somebody Else's Game", "Not The Creator")
    assert not v.is_verified()
    for fn in (lambda: registry.register_file(v, tmp_path / "a.png"),
               lambda: traps.generate(v, "x", "godot"),
               lambda: check.run(v, [tmp_path]),
               lambda: certificate.issue(v, do_stamp=False)):
        with pytest.raises(NotVerified):
            fn()
    # CLI path too
    assert cli.main(["-C", str(tmp_path), "register", str(tmp_path / "a.png")]) == 2


def test_page_verification_rejects_wrong_page(world, tmp_path):
    v = Vault.init(tmp_path, "Lantern Moth", "Impostor")
    with pytest.raises(verify.VerifyError):  # the page shows the real creator's code, not this one
        verify.verify_page(v, "itch", ITCH_URL)
    IMPOSTOR_CODE[0] = v.project()["verify_code"]
    with pytest.raises(verify.VerifyError):  # posting your code as a comment doesn't count
        verify.verify_page(v, "itch", IMPOSTOR_URL)
    assert not v.is_verified()
    with pytest.raises(verify.VerifyError):
        verify.parse_store_url("itch", "https://evil.example.com/lantern-moth")


def test_verified_creator_registered_everything(world):
    v = world["vault"]
    assert world["verify"]["status"] == "verified"
    kinds = {r["kind"] for r in world["reg"]}
    assert {"image", "audio", "video", "code", "text"} <= kinds
    marked = {r["kind"] for r in world["reg"] if r.get("watermarked")}
    assert {"image", "audio", "video"} <= marked
    for r in world["reg"]:
        if r["kind"] == "image":
            assert r["quality"]["psnr_db"] >= 38, r


# --- watermarks -----------------------------------------------------------------

def _screenshot(path: Path, out: Path, scale=1.25, crop=(0.02, 0.01, 0.015, 0.02)) -> Path:
    im = Image.open(path).convert("RGB")
    w, h = im.size
    s = im.resize((int(w * scale), int(h * scale)), Image.Resampling.BILINEAR)
    W, H = s.size
    s = s.crop((int(crop[0] * W), int(crop[2] * H), W - int(crop[1] * W), H - int(crop[3] * H)))
    s.save(out)  # PNG, like a screen capture
    return out


def test_image_watermark_survives_screenshot_and_reencode(world, tmp_path):
    v = world["vault"]
    marked = world["orig"] / "indieward_out" / "moth_2.png"
    shot = _screenshot(marked, tmp_path / "shot.png")
    jpg = tmp_path / "shot_reencoded.jpg"
    Image.open(shot).convert("RGB").save(jpg, quality=70)
    webp = tmp_path / "reencoded.webp"
    Image.open(marked).convert("RGB").resize((180, 180)).save(webp, quality=75)
    for f in (shot, jpg, webp):
        r = cli.detect_file(v, f)
        assert r["detected"], (f, r)
        assert r["matches"][0]["registered"] == "moth_2.png"
    clean = _screenshot(world["orig"] / "art" / "moth_2.png", tmp_path / "clean.png")
    assert not cli.detect_file(v, clean)["detected"]


def test_image_watermark_screenshot_margin_across_payloads(tmp_path):
    # Every vault gets random payloads, so detection must not hinge on a lucky one.
    # moth_1 is the fixture image with the least headroom under the screenshot transform.
    from indieward import payload, wm_core, wm_image
    src = tmp_path / "moth_1.png"
    gf._art(101).save(src)
    rgb = np.asarray(Image.open(src).convert("RGB"), dtype=np.float64)
    rng = np.random.default_rng(2026)
    zs = []
    for i in range(6):
        p = payload.make(rng.bytes(32), int(rng.integers(0, 2**payload.ID_BITS)))
        out, ref = wm_image.embed_array(rgb, p)
        marked = tmp_path / f"marked_{i}.png"
        Image.fromarray(out.astype(np.uint8)).save(marked)
        shot = _screenshot(marked, tmp_path / f"shot_{i}.png")
        zs.append(wm_image.match_array(np.asarray(Image.open(shot).convert("RGB"), dtype=np.float64), p, ref)["z"])
    assert min(zs) >= wm_core.DETECT_Z + 1.0, zs


def test_audio_watermark_survives_reencode(world, tmp_path):
    v = world["vault"]
    marked = world["orig"] / "indieward_out" / "theme.wav"
    mp3 = tmp_path / "theme.mp3"
    mediaio.transcode(marked, mp3, ["-b:a", "128k"])
    trimmed = tmp_path / "theme_trim.ogg"
    mediaio.transcode(marked, trimmed, ["-ss", "1.7", *mediaio.vorbis_args(5)])
    for f in (mp3, trimmed):
        r = cli.detect_file(v, f)
        assert r["detected"], (f, r)
    clean = tmp_path / "clean.mp3"
    mediaio.transcode(world["orig"] / "audio" / "theme.wav", clean, ["-b:a", "128k"])
    assert not cli.detect_file(v, clean)["detected"]


def test_video_watermark_survives_reencode(world, tmp_path):
    v = world["vault"]
    marked = world["orig"] / "indieward_out" / "trailer.mp4"
    re1 = tmp_path / "trailer_480.mp4"
    mediaio.transcode(marked, re1, ["-vf", "scale=426:240", "-c:v", "libx264", "-crf", "23"])
    re2 = tmp_path / "trailer_cut.mp4"
    mediaio.transcode(marked, re2, ["-ss", "2.5", "-r", "24", "-c:v", "libx264", "-crf", "26"])
    for f in (re1, re2):
        r = cli.detect_file(v, f)
        assert r["detected"], (f, r)
    clean = tmp_path / "clean.mp4"
    mediaio.transcode(world["orig"] / "video" / "trailer.mp4", clean, ["-c:v", "libx264", "-crf", "26"])
    assert not cli.detect_file(v, clean)["detected"]


# --- certificate -----------------------------------------------------------------

def test_certificate_signed_and_timestamped(world, tmp_path):
    cert = world["cert"]
    assert Path(cert["pdf"]).exists()
    assert cert["timestamps"]["rfc3161"] == "stamped"
    assert cert["timestamps"]["opentimestamps"] == "pending-bitcoin"
    body = json.loads(Path(cert["json"]).read_text())
    assert certificate.verify(body)["valid"]
    assert certificate.verify(body)["rfc3161_token"].startswith("imprint matches")
    assert certificate.verify(body, world["tsa"]["cert"])["rfc3161_token"] == "verified against TSA certificate"
    assert len(body["assets"]) == len(world["reg"])
    assert body["verified_store_links"][0]["url"] == ITCH_URL
    # the RFC 3161 token verifies against the TSA's certificate with plain openssl
    tok = tmp_path / "t.tsr"
    import base64

    tok.write_bytes(base64.b64decode(body["timestamps"]["rfc3161"]["token_b64"]))
    out = subprocess.run(["openssl", "ts", "-verify", "-digest", body["digest_sha256"], "-in", str(tok),
                          "-CAfile", str(world["tsa"]["cert"])], capture_output=True, text=True)
    assert "Verification: OK" in out.stdout, out.stdout + out.stderr
    # tampering breaks it
    body["assets"][0]["sha256"] = "0" * 64
    assert not certificate.verify(body)["valid"]


# --- builds ----------------------------------------------------------------------

def test_build_traps_and_fingerprints_stored(world):
    v = world["vault"]
    b = world["build"]
    assert b["ok"], b
    row = v.db.execute("SELECT * FROM builds WHERE id=?", (world["traps"]["build_id"],)).fetchone()
    assert row["fp_path"] and row["trap_commitment"] and row["manifest_sha256"]
    assert len(traps.records(v, row["id"])) == 9
    assert b["fingerprints"]["code"] > 20 and b["fingerprints"]["text_lines"] >= 10
    # the trap snippet is inert (only constants and a function returning a constant) and doesn't announce itself
    snip = Path(world["traps"]["snippets"])
    gd = next(snip.rglob("*.gd")).read_text()
    assert "http" not in gd.lower() and "OS." not in gd and "FileAccess" not in gd
    assert (snip / "README_INDIEWARD.txt").exists()
    with zipfile.ZipFile(world["build_zip"]) as z:
        for n in z.namelist():
            assert "indieward" not in n.lower() and "readme_indieward" not in n.lower()
            if n.endswith(".gd") and not n.startswith("scripts/"):
                assert b"IndieWard" not in z.read(n) and b"trap" not in z.read(n).lower()


# --- scoring -----------------------------------------------------------------------

def test_clone_scores_high_and_traps_detected(world):
    r = _report(world, "clone")
    cats = {c["key"]: c for c in r["categories"]}
    print({k: c["score"] for k, c in cats.items()}, r["overall"])
    assert r["traps"]["count"] >= 3
    assert any(t["tier"] == "core" for t in r["traps"]["found"])
    assert cats["traps"]["score"] == 100
    assert cats["code"]["score"] >= 60
    assert cats["art"]["score"] >= 60
    assert cats["text"]["score"] >= 60
    assert r["overall"] >= 80
    assert r["recommendation"] == "file"
    assert not r["weak_only"]
    assert r["watermarks"] == []  # the clone was built from unmarked art and audio


def test_unrelated_scores_low_no_traps(world):
    r = _report(world, "unrelated")
    print({c["key"]: c["score"] for c in r["categories"]}, r["overall"])
    assert r["traps"]["count"] == 0
    assert r["overall"] <= 20
    assert r["recommendation"] == "do_not_file"
    assert all(c["score"] <= 25 for c in r["categories"] if c["strength"] == "Strong")


def test_every_report_labels_strength_and_carries_disclaimer(world):
    for key in ("clone", "unrelated", "mech"):
        r = _report(world, key)
        assert {c["strength"] for c in r["categories"]} == {"Strong", "Supporting", "Weak"}
        assert {c["key"]: c["strength"] for c in r["categories"]}["mechanics"] == "Weak"
        assert "cannot show whether an AI was used" in r["disclaimer"]
        html = Path(world[key]["report_html"]).read_text()
        assert "cannot show whether an AI was used" in html
        for c in r["categories"]:
            if c["score"] > 0 and c["key"] != "mechanics":
                assert c["evidence"], c["key"]  # every score shows what matched


def test_mechanics_only_report_flagged_and_package_refused(world):
    r = _report(world, "mech")
    assert r["weak_only"] is True
    assert r["recommendation"] == "do_not_file"
    assert "mechanics" in r["message"]
    with pytest.raises(package.WeakEvidence):
        package.build(world["vault"], world["mech"]["id"])


# --- takedown package ---------------------------------------------------------------

def test_package_drafts_for_each_store_nothing_sent(world):
    v = world["vault"]
    urls = ["https://clonefarm.itch.io/lantern-moths", "https://store.steampowered.com/app/999999/Lantern_Moths/",
            "https://www.roblox.com/games/123456/Lantern-Moths"]
    certificate.issue(v)  # a later certificate exists too; the package must still cite the earliest one
    res = package.build(v, world["clone"]["id"], suspect_urls=urls)
    first = json.loads(Path(world["cert"]["json"]).read_text())
    assert res["certificate_issued"] == first["issued_at"]
    assert res["sent"] is False
    expected_to = {"itch": "support@itch.io", "roblox": "copyright_agent@roblox.com", "steam": "dev@teststudio.example"}
    want = {"certificate.pdf", "certificate.json", "check_report.html", "evidence.zip", "trap_disclosure.json"}
    for st, d in res["drafts"].items():
        msg = email.message_from_bytes(Path(d["eml"]).read_bytes(), policy=policy.default)
        assert msg["To"] == expected_to[st]
        assert msg["X-Unsent"] == "1"
        names = {p.get_filename() for p in msg.iter_attachments()}
        assert names == want, (st, names)
        body = msg.get_body(("plain",)).get_content()
        for phrase in ("good faith belief", "penalty of perjury", "clonefarm.itch.io", "trap markers"):
            assert phrase in body, (st, phrase)
        if st == "steam":
            assert "steamcommunity.com/dmca/create" in body
    pdir = Path(res["package_dir"])
    for f in ("BEFORE_YOU_SEND.md", "registration_hashes.csv", "steam/CHECKLIST.md", "itch/CHECKLIST.md",
              "roblox/CHECKLIST.md"):
        assert (pdir / f).exists(), f
    disc = json.loads((pdir / "trap_disclosure.json").read_text())
    assert disc["found"] and all(t["salt"] for t in disc["found"])
    assert "salts" not in disc  # unfound traps' salts are never revealed
    # each revealed trap's commitment recomputes from its own salt and rolls up to the certificate's commitment
    import hashlib

    cert = json.loads((pdir / "certificate.json").read_text())
    for t in disc["found"]:
        c = hashlib.sha256(f"{t['salt']}|{t['tier']}|{t['kind']}|{t['value']}".encode()).hexdigest()
        assert c == t["commitment"] and c in disc["build_commitment_lists"][t["build_id"]]
    for b, lst in disc["build_commitment_lists"].items():
        roll = hashlib.sha256("|".join(lst).encode()).hexdigest()
        assert roll == next(x["trap_commitment"] for x in cert["builds"] if x["build_id"] == b)
    with zipfile.ZipFile(res["zip"]) as z:
        assert "itch/itch_copyright_draft.eml" in z.namelist()
    rows = v.db.execute("SELECT status FROM takedowns WHERE check_id=?", (world["clone"]["id"],)).fetchall()
    assert len(rows) == 3 and all(r[0] == "drafted (not sent)" for r in rows)


def test_package_only_targets_stores_the_clone_is_on(world):
    with pytest.raises(ValueError):
        package.build(world["vault"], world["clone"]["id"], ["steam"],
                      suspect_urls=["https://clonefarm.itch.io/lantern-moths"])


def test_traps_alone_recommend_review_not_file(world, tmp_path):
    v = world["vault"]
    z = tmp_path / "only_traps.zip"
    snip = Path(world["traps"]["snippets"])
    with zipfile.ZipFile(z, "w") as zz:
        for f in snip.rglob("*"):
            if f.is_file() and not f.name.startswith("README_"):
                zz.write(f, f.relative_to(snip))
    r = check.run(v, [z])
    assert r["traps_found"] >= 3
    assert r["recommendation"] == "review"


def test_plain_images_never_count_as_copies():
    from PIL import ImageDraw

    from indieward import fp_image

    def scene(seed):
        rng = np.random.default_rng(seed)
        im = Image.new("RGB", (256, 256), tuple(int(x) for x in rng.integers(100, 255, 3)))
        ImageDraw.Draw(im).rectangle((0, 160, 256, 256), fill=tuple(int(x) for x in rng.integers(0, 120, 3)))
        return im

    pairs = [(Image.new("RGB", (64, 64), (255, 0, 0)), Image.new("RGB", (64, 64), (0, 0, 255))),
             (scene(2), scene(3))]
    for a, b in pairs:
        assert fp_image.similarity(fp_image.fingerprint_image(a), fp_image.fingerprint_image(b)) == 0.0


def test_no_code_path_can_send_anything():
    banned = re.compile(r"import smtplib|from smtplib|smtplib\.|\.sendmail\(|\.send_message\(|SMTP\(|SMTP_SSL\(")
    for f in SRC.rglob("*.py"):
        assert not banned.search(f.read_text()), f
