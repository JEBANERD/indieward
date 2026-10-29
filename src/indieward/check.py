"""Manual "check a suspect" flow: traps, watermarks, fingerprints, scores, labels.

Give it a suspect build (folder, zip, .rbxl/.rbxlx, .pck...), screenshots,
audio, clips, and/or a store page. It looks for your trap markers and
watermarks, compares fingerprints category by category, and writes a report
with the matched evidence side by side.

Every score measures similarity to your registered work. It cannot show
whether an AI was used or what any AI read. It is evidence for you to weigh,
not a legal finding.
"""
from __future__ import annotations

import html
import io
import json
import re
import secrets
import shutil
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

from . import fp_audio, fp_code, fp_image, fp_text, fp_video, mediaio, payload as pl, registry, traps, util, verify
from . import wm_audio, wm_image, wm_video
from .vault import Vault

STRENGTH = {"traps": "Strong", "code": "Strong", "art": "Strong", "text": "Strong",
            "ui": "Supporting", "audio": "Supporting", "name": "Supporting", "video": "Supporting",
            "mechanics": "Weak"}
LABELS = {"traps": "Trap markers", "code": "Code", "art": "Art", "text": "Story and text", "ui": "UI",
          "audio": "Audio", "name": "Name and logo", "video": "Video", "mechanics": "Mechanics"}
STRENGTH_NOTE = {
    "Strong": "Strong basis for a copyright notice when the matches are your original expression.",
    "Supporting": "Supports a notice; rarely enough on its own (trademark claims need a mark, ideally registered).",
    "Weak": "Game mechanics and rules aren't protected by copyright (17 U.S.C. 102(b)). Don't file on this alone.",
}


# --- collecting the suspect -------------------------------------------------------

class Suspect:
    def __init__(self):
        self.images: list[tuple[str, Image.Image]] = []
        self.audio: list[tuple[str, Path]] = []
        self.video: list[tuple[str, Path]] = []
        self.code: dict[str, str] = {}
        self.lines: list[str] = []
        self.names: list[str] = []
        self.page_text = ""
        self.sources: list[str] = []
        self._tmp = Path(tempfile.mkdtemp(prefix="iw_suspect_"))

    def cleanup(self):
        shutil.rmtree(self._tmp, ignore_errors=True)


_STR_RE = re.compile(rb"[\x20-\x7e]{28,}")


def collect(paths, store_url=None, page_file=None, name=None, max_images=1500) -> Suspect:
    s = Suspect()
    for root in paths or []:
        s.sources.append(str(root))
        for disp, data in traps.iter_blobs(root):
            inner = disp.split("!/")[-1]
            k = util.kind_for(inner)
            if k in ("code", "text") and util.is_vendor_path(inner):
                continue
            if k == "image" and len(s.images) < max_images:
                try:
                    im = Image.open(io.BytesIO(data))
                    im.load()
                    if min(im.size) >= 32:
                        s.images.append((disp, im.convert("RGB")))
                except Exception:
                    pass
            elif k in ("audio", "video"):
                p = Path(disp) if "!/" not in disp else s._tmp / f"{len(s.audio) + len(s.video)}_{Path(inner).name}"
                if "!/" in disp:
                    p.write_bytes(data)
                (s.audio if k == "audio" else s.video).append((disp, p))
            elif k == "code":
                s.code[disp] = data.decode("utf-8", "replace")
            elif k == "text":
                txt = data.decode("utf-8", "replace")
                if inner.lower().endswith((".gd", ".lua")):
                    s.code[disp] = txt
                s.lines += fp_text.split_lines(_json_strings(txt) if inner.lower().endswith(".json") else txt)
            elif len(data) < 64 << 20:
                # Compiled or packed files: pull readable strings (dialogue often survives) and embedded scripts.
                strings = [m.group(0).decode("ascii", "replace") for m in _STR_RE.finditer(data)]
                s.lines += fp_text.split_lines("\n".join(strings))
                if disp.endswith("!/decompressed") or inner.endswith((".rbxlx", ".rbxmx")):
                    s.code[disp] = "\n".join(strings)
    if store_url or page_file:
        _collect_page(s, store_url, page_file)
    if name:
        s.names.append(name)
    return s


def _json_strings(txt: str) -> str:
    try:
        vals = []

        def walk(o):
            if isinstance(o, str):
                vals.append(o)
            elif isinstance(o, dict):
                [walk(v) for v in o.values()]
            elif isinstance(o, list):
                [walk(v) for v in o]

        walk(json.loads(txt))
        return "\n".join(vals)
    except Exception:
        return txt


def _collect_page(s: Suspect, url, page_file):
    """One store page: its title, description text and up to 12 images. One request per item, no crawling."""
    if page_file:
        raw = Path(page_file).read_text("utf-8", errors="replace")
        s.sources.append(f"page file {page_file}")
    else:
        status, body = verify.http_get(url)
        if status != 200:
            raise ValueError(f"Couldn't read {url} (HTTP {status})")
        raw = body.decode("utf-8", "replace")
        s.sources.append(url)
    title = re.search(r"<meta[^>]+property=[\"']og:title[\"'][^>]+content=[\"']([^\"']+)", raw, re.I) or \
        re.search(r"<title>(.*?)</title>", raw, re.I | re.S)
    if title:
        s.names.append(html.unescape(title.group(1)).split("|")[0].split(" on Steam")[0].strip())
    text = re.sub(r"<script.*?</script>|<style.*?</style>", " ", raw, flags=re.S | re.I)
    text = html.unescape(re.sub(r"<br\s*/?>|</p>|</div>|</li>", "\n", text, flags=re.I))
    text = re.sub(r"<[^>]+>", " ", text)
    s.page_text = text
    s.lines += fp_text.split_lines(text)
    if page_file:
        base = Path(page_file).parent
        for src in re.findall(r"<img[^>]+src=[\"']([^\"']+)", raw, re.I)[:12]:
            p = base / src
            if p.exists():
                try:
                    s.images.append((f"page image {src}", Image.open(p).convert("RGB")))
                except Exception:
                    pass
    else:
        for src in re.findall(r"<img[^>]+src=[\"'](https://[^\"']+)", raw, re.I)[:12]:
            try:
                st, b = verify.http_get(src)
                if st == 200:
                    s.images.append((f"page image {src}", Image.open(io.BytesIO(b)).convert("RGB")))
            except Exception:
                pass


# --- scoring -----------------------------------------------------------------------

def _image_category(reg_rows, reg_fps, sus_imgs, sus_fps):
    if not reg_rows or not sus_imgs:
        return 0, [], {}
    sim = np.zeros((len(reg_rows), len(sus_imgs)))
    for i, fa in enumerate(reg_fps):
        for j, fb in enumerate(sus_fps):
            sim[i, j] = fp_image.similarity(fa, fb)
    best_o = sim.max(axis=1)
    best_s = sim.max(axis=0)
    matched = int((best_o >= 0.5).sum())
    cov_o = float(np.where(best_o >= 0.5, best_o, 0).sum() / len(reg_rows))
    cov_s = float(np.where(best_s >= 0.5, best_s, 0).sum() / len(sus_imgs))
    conf_n = min(1.0, matched / 3.0)
    score = int(round(100 * max(cov_o, cov_s) * conf_n))
    pairs = []
    for i in np.argsort(-best_o):
        if best_o[i] < 0.5 or len(pairs) >= 12:
            break
        j = int(np.argmax(sim[i]))
        pairs.append({"registered": reg_rows[i], "suspect_index": j, "similarity": round(float(best_o[i]), 3)})
    return score, pairs, {"sim": sim}


def run(vault: Vault, paths=None, store_url=None, page_file=None, suspect_name=None,
        mechanics: list[str] | None = None) -> dict:
    vault.require_verified("run checks")
    check_id = "c" + secrets.token_hex(5)
    out = vault.path("checks", check_id)
    (out / "evidence").mkdir(parents=True, exist_ok=True)
    sus = collect(paths, store_url, page_file, suspect_name)
    try:
        report = _score(vault, sus, out, mechanics)
    finally:
        sus.cleanup()
    report.update({"id": check_id, "created_at": util.now_iso(), "project": vault.project()["name"],
                   "suspect": {"sources": sus.sources, "names": sus.names, "store_url": store_url},
                   "disclaimer": util.DISCLAIMER})
    (out / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))
    (out / "report.html").write_text(render_html(report), encoding="utf-8")
    vault.db.execute("INSERT INTO checks VALUES (?,?,?,?,?,?)",
                     (check_id, report["created_at"], json.dumps(report["suspect"]), report["overall"],
                      report["recommendation"], vault.rel(out / "report.json")))
    vault.db.commit()
    return {"id": check_id, "overall": report["overall"], "recommendation": report["recommendation"],
            "weak_only": report["weak_only"], "report_html": str(out / "report.html"),
            "report_json": str(out / "report.json"),
            "categories": {c["key"]: {"score": c["score"], "strength": c["strength"]} for c in report["categories"]},
            "traps_found": report["traps"]["count"], "watermarks_found": len(report["watermarks"])}


def _thumb(img: Image.Image, path: Path, size=256) -> str:
    im = img.copy()
    im.thumbnail((size, size))
    im.save(path)
    return path.name


def _score(vault: Vault, sus: Suspect, out: Path, mechanics) -> dict:
    ev = out / "evidence"
    cats = []
    assets = registry.assets(vault)
    builds = [dict(r) for r in vault.db.execute("SELECT * FROM builds").fetchall()]
    common = _common(vault)

    # 1. traps
    tr = {"found": [], "core_found": 0, "builds_identified": []}
    for p in sus.sources:
        if Path(p).exists():
            r = traps.scan_all(vault, p)
            tr["found"] += r["found"]
            tr["core_found"] += r["core_found"]
            tr["builds_identified"] += r["builds_identified"]
    n_traps = len({f["id"] for f in tr["found"]})
    trap_score = 0 if n_traps == 0 else (100 if n_traps >= 2 else 80)
    builds_by_id = {b["id"]: b for b in builds}
    trap_ev = [{"id": f["id"], "kind": f["kind"], "label": f["label"], "tier": f["tier"], "build": builds_by_id.get(f["build_id"], {}).get("label"),
                "build_id": f["build_id"], "value": f["value"], "commitment": traps.trap_commitment(vault, f),
                "found_in": f["found_in"][:3]} for f in tr["found"]]
    cats.append(_cat("traps", trap_score,
                     f"{n_traps} of your trap markers found" + (
                         f"; build traps point to: {', '.join(builds_by_id.get(b, {}).get('label', b) for b in sorted(set(tr['builds_identified'])))}"
                         if tr["builds_identified"] else "") if n_traps else "No trap markers found.",
                     trap_ev))

    # 2. code
    reg_code = {"fingerprints": {}}
    for a in assets:
        if a["kind"] == "code":
            reg_code["fingerprints"].update(registry.load_fp(vault, a)["fingerprints"])
    for b in builds:
        if b.get("fp_path"):
            reg_code["fingerprints"].update(json.loads(vault.path(b["fp_path"]).read_text())["code"]["fingerprints"])
    sus_code = fp_code.fingerprint_text_blobs({Path(k.split("!/")[-1]).name: v for k, v in sus.code.items()})
    cc = fp_code.compare(reg_code, sus_code, common.get("code"))
    code_ev = []
    src_by_name = {Path(a["name"]).name: a for a in assets if a["kind"] == "code"}
    sus_by_name = {Path(k.split("!/")[-1]).name: v for k, v in sus.code.items()}
    for p in cc["pairs"][:6]:
        o_src = src_by_name.get(p["original_file"])
        o_text = _lines(Path(o_src["source_path"]), *p["original_lines"]) if o_src and Path(o_src["source_path"]).exists() else "(original source not on this machine)"
        s_text = _lines_text(sus_by_name.get(p["suspect_file"], ""), *p["suspect_lines"])
        code_ev.append({**p, "original_excerpt": o_text, "suspect_excerpt": s_text})
    cats.append(_cat("code", cc["score"] if reg_code["fingerprints"] else 0,
                     f"{cc['matched']} shared code fingerprints; {int(cc['coverage_original']*100)}% of your registered "
                     f"code and {int(cc['coverage_suspect']*100)}% of the suspect's code match after renaming is "
                     f"ignored." + (f" {cc['excluded_common']} common-boilerplate fingerprints excluded." if cc["excluded_common"] else "")
                     if reg_code["fingerprints"] and sus.code else "No comparable code (none registered or none found in the suspect).",
                     code_ev))

    # 3/4/name-logo. images
    sus_fps = [fp_image.fingerprint_image(im) for _, im in sus.images]
    for key in ("art", "ui", "logo"):
        rows = [a for a in assets if a["kind"] == "image" and a["category"] == key]
        rows = [r for r in rows if not _is_common_image(registry.load_fp(vault, r), common)]
        fps = [registry.load_fp(vault, r) for r in rows]
        score, pairs, extra = _image_category(rows, fps, sus.images, sus_fps)
        evid = []
        for k, p in enumerate(pairs):
            r = p["registered"]
            j = p["suspect_index"]
            src = Path(r["source_path"]) if r["source_path"] and Path(r["source_path"]).exists() else None
            o_th = _thumb(Image.open(src).convert("RGB"), ev / f"{key}_{k}_orig.png") if src else None
            s_th = _thumb(sus.images[j][1], ev / f"{key}_{k}_suspect.png")
            evid.append({"registered": r["name"], "record": pl.fmt(r["record_id"]),
                         "suspect": sus.images[j][0], "similarity": p["similarity"], "orig_thumb": o_th,
                         "suspect_thumb": s_th})
        if key == "logo":
            logo_score, logo_ev = score, evid
            continue
        cats.append(_cat(key, score,
                         f"{len(pairs)} of {len(rows)} registered {key} images have a close match among the "
                         f"suspect's {len(sus.images)} images." if rows and sus.images else
                         f"No comparable {key} images (none registered or none in the suspect).", evid))

    # watermarks in images: informed check against the closest registered originals
    wms = []
    img_rows = [a for a in assets if a["kind"] == "image" and a["ref_path"]]
    if img_rows and sus.images:
        rfps = [registry.load_fp(vault, r) for r in img_rows]
        cand = []
        for j, fb in enumerate(sus_fps):
            sims = [fp_image.similarity(fa, fb) for fa in rfps]
            for i in np.argsort(sims)[::-1][:2]:
                if sims[i] >= 0.3:
                    cand.append((sims[i], j, i))
        for _, j, i in sorted(cand, reverse=True)[:40]:
            r = img_rows[i]
            ref = np.load(vault.path(r["ref_path"])).astype(np.float32)
            m = wm_image.match_array(np.asarray(sus.images[j][1], dtype=np.float64), int(r["wm_payload"], 16), ref)
            if m["detected"]:
                wms.append({"media": "image", "category": r["category"], "registered": r["name"],
                            "suspect": sus.images[j][0], **m})

    # 5. text
    reg_lines = []
    for a in assets:
        if a["kind"] == "text":
            reg_lines += registry.load_fp(vault, a)["lines"]
    for b in builds:
        if b.get("fp_path"):
            reg_lines += json.loads(vault.path(b["fp_path"]).read_text())["lines"]
    common_lines = common.get("lines", set())
    reg_lines = [x for x in dict.fromkeys(reg_lines) if fp_text.normalize(x) not in common_lines]
    sus_lines = list(dict.fromkeys(sus.lines))
    tc = fp_text.compare(reg_lines, sus_lines)
    cats.append(_cat("text", tc["score"] if reg_lines else 0,
                     f"{tc['matched']} of your {tc['of']} registered lines appear in the suspect, verbatim or "
                     f"lightly reworded." if reg_lines and sus_lines else "No comparable text.", tc["pairs"]))

    # 6. audio
    a_rows = [a for a in assets if a["kind"] == "audio"]
    a_ev, a_best, a_sus_hit = [], {}, set()
    for disp, path in sus.audio:
        try:
            data, sr = mediaio.read_audio(path)
        except Exception:
            continue
        fb = fp_audio.fingerprint_array(data, sr)
        for r in a_rows:
            c = fp_audio.compare(registry.load_fp(vault, r), fb)
            wm = None
            if r["wm_payload"] and r["ref_path"] and c["confidence"] > 0.05:
                wm = wm_audio.match_array(data, sr, int(r["wm_payload"], 16),
                                          np.load(vault.path(r["ref_path"])).astype(np.float64))
                if wm["detected"]:
                    wms.append({"media": "audio", "category": "audio", "registered": r["name"], "suspect": disp, **wm})
            conf = 1.0 if wm and wm["detected"] else c["confidence"]
            if conf >= 0.3:
                a_best[r["id"]] = max(a_best.get(r["id"], 0), conf)
                a_sus_hit.add(disp)
                a_ev.append({"registered": r["name"], "suspect": disp, "confidence": round(conf, 3),
                             "offset_s": c["offset_s"], "aligned_hashes": c["aligned_hashes"]})
    a_score = int(round(100 * sum(a_best.values()) / len(a_rows))) if a_rows and a_best else 0
    if a_rows and sus.audio:
        a_score = max(a_score, int(round(100 * len(a_sus_hit) / max(1, len(sus.audio))
                                         * (sum(a_best.values()) / max(1, len(a_best))))))
    cats.append(_cat("audio", min(100, a_score),
                     f"{len(a_best)} of {len(a_rows)} registered audio files match suspect audio." if a_rows and sus.audio
                     else "No comparable audio.", a_ev[:10]))

    # 7. video
    v_rows = [a for a in assets if a["kind"] == "video"]
    v_ev, v_best = [], {}
    for disp, path in sus.video:
        try:
            fb = fp_video.fingerprint_file(path)
        except Exception:
            continue
        for r in v_rows:
            c = fp_video.compare(registry.load_fp(vault, r), fb)
            wm = wm_video.match_file(path, int(r["wm_payload"], 16)) if r["wm_payload"] else None
            if wm and wm["detected"]:
                wms.append({"media": "video", "category": "video", "registered": r["name"], "suspect": disp, **wm})
            conf = 1.0 if wm and wm["detected"] else c["confidence"]
            if conf >= 0.3:
                v_best[r["id"]] = max(v_best.get(r["id"], 0), conf)
                v_ev.append({"registered": r["name"], "suspect": disp, "confidence": round(conf, 3),
                             "matched_frames": c["matched_frames"]})
    v_score = int(round(100 * max(v_best.values()))) if v_best else 0
    cats.append(_cat("video", v_score, f"{len(v_best)} registered videos match suspect footage." if v_rows and sus.video
                     else "No comparable video.", v_ev[:10]))

    # 8. name / logo
    proj_name = vault.project()["name"]
    nsim = max([fp_text.name_similarity(proj_name, n) for n in sus.names] or [0.0])
    name_score = int(round(100 * nsim)) if nsim >= 0.7 else 0
    n_ev = [{"your_name": proj_name, "suspect_name": n, "similarity": round(fp_text.name_similarity(proj_name, n), 3)}
            for n in sus.names]
    name_score = max(name_score, logo_score)
    cats.append(_cat("name", name_score, (f"Suspect name similarity {int(nsim*100)}%." if sus.names else "No suspect name given.")
                     + (f" Logo match score {logo_score}." if logo_score else ""), n_ev + logo_ev))

    # 9. mechanics
    mech = mechanics or _setting(vault, "mechanics", [])
    hay = (sus.page_text + " " + " ".join(sus.lines[:2000])).lower()
    hits = [m for m in mech if re.search(r"\b" + re.escape(m.lower()) + r"s?\b", hay)]
    mech_score = int(round(100 * len(hits) / len(mech))) if mech else 0
    cats.append(_cat("mechanics", mech_score, f"{len(hits)} of {len(mech)} listed mechanics described by the suspect."
                     if mech else "No mechanics listed (indieward mechanics set ...).", [{"matched": hits}]))

    # bump media categories that have a watermark hit
    for c in cats:
        cat_of = {"logo": "name"}
        if any(cat_of.get(w["category"], w["category"]) == c["key"] for w in wms):
            c["score"] = max(c["score"], 90)
            c["summary"] += " Your watermark was detected (see Watermarks)."

    overall, rec, weak_only, message = _overall(cats)
    return {"categories": cats, "traps": {"count": n_traps, "found": trap_ev}, "watermarks": wms,
            "overall": overall, "recommendation": rec, "weak_only": weak_only, "message": message}


def _cat(key, score, summary, evidence):
    st = STRENGTH[key]
    return {"key": key, "label": LABELS[key], "strength": st, "strength_note": STRENGTH_NOTE[st],
            "score": int(max(0, min(100, score))), "summary": summary, "evidence": evidence}


def _overall(cats):
    strong = max([c["score"] for c in cats if c["strength"] == "Strong"] or [0])
    supp = max([c["score"] for c in cats if c["strength"] == "Supporting"] or [0])
    weak = max([c["score"] for c in cats if c["strength"] == "Weak"] or [0])
    if strong >= 20:
        overall = strong + (100 - strong) * 0.3 * supp / 100
    elif supp >= 20:
        overall = 0.6 * supp
    else:
        overall = min(30, 0.3 * weak)
    weak_only = strong < 20 and supp < 20 and weak >= 20
    traps_hit = next(c["score"] for c in cats if c["key"] == "traps") > 0
    expressive = max(c["score"] for c in cats if c["key"] in ("code", "art", "text"))
    if weak_only:
        rec = "do_not_file"
        msg = ("This report rests only on mechanics, which copyright doesn't protect. Filing on it would likely be "
               "rejected and can hurt your credibility with the store. Don't file. If you think expression was "
               "copied, register and check that material.")
    elif (strong >= 60 and not traps_hit) or (traps_hit and expressive >= 20):
        rec = "file"
        msg = ("Strong evidence of copying. Review every match, confirm the matched material is your original work "
               "(not shared assets or licensed packs), then build the takedown package.")
    elif traps_hit:
        rec = "review"
        msg = ("Your trap markers are in the suspect's files, which shows it was made from your build. But little of "
               "your art, code or text matched, and made-up trap values alone aren't protected expression. Look "
               "for what else was copied, and talk to a lawyer before filing.")
    elif strong >= 30 or supp >= 60:
        rec = "review"
        msg = ("Some evidence of copying, not conclusive. Look at each match closely. Consider talking to a lawyer "
               "before filing.")
    else:
        rec = "do_not_file"
        msg = "Little similarity to your registered work. Don't file on this evidence."
    return int(round(overall)), rec, weak_only, msg


def _common(vault: Vault) -> dict:
    p = vault.path("fp", "common.json")
    if not p.exists():
        return {}
    d = json.loads(p.read_text())
    return {"code": set(d.get("code", [])), "images": d.get("images", []), "lines": set(d.get("lines", []))}


def _is_common_image(fp, common) -> bool:
    return any(fp_image.similarity(c, fp) >= 0.8 for c in common.get("images", []))


def add_common(vault: Vault, path) -> dict:
    """Index shared material (engine templates, asset-store packs) so it never counts as copying."""
    p = vault.path("fp", "common.json")
    d = json.loads(p.read_text()) if p.exists() else {"code": [], "images": [], "lines": []}
    code, imgs, lines = set(d["code"]), d["images"], set(d.get("lines", []))
    blobs = {}
    for f in util.iter_files(path):
        k = util.kind_for(f)
        if k == "code":
            blobs[str(f)] = f.read_text("utf-8", errors="replace")
        elif k == "text":
            lines |= {fp_text.normalize(x) for x in fp_text.lines_from_file(f)}
        elif k == "image":
            try:
                imgs.append(fp_image.fingerprint_file(f))
            except Exception:
                pass
    code |= set(fp_code.fingerprint_text_blobs(blobs)["fingerprints"])
    p.write_text(json.dumps({"code": sorted(code), "images": imgs, "lines": sorted(lines)}))
    return {"code_fingerprints": len(code), "images": len(imgs), "text_lines": len(lines)}


def _setting(vault, key, default):
    vault.db.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
    r = vault.db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return json.loads(r[0]) if r else default


def set_setting(vault, key, value):
    vault.db.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
    vault.db.execute("INSERT OR REPLACE INTO settings VALUES (?,?)", (key, json.dumps(value)))
    vault.db.commit()


def _lines(path: Path, a: int, b: int) -> str:
    try:
        return _lines_text(path.read_text("utf-8", errors="replace"), a, b)
    except OSError:
        return ""


def _lines_text(text: str, a: int, b: int, limit: int = 14) -> str:
    rows = text.splitlines()
    a = max(1, a)
    b = min(len(rows), max(a, b), a + limit - 1)
    return "\n".join(f"{i:>4}  {rows[i - 1]}" for i in range(a, b + 1))


# --- HTML report -------------------------------------------------------------------

def render_html(r: dict) -> str:
    e = html.escape
    badge = {"Strong": "#1f7a3d", "Supporting": "#8a6d00", "Weak": "#8a1f1f"}
    rec = {"file": ("Strong evidence: consider filing", "#1f7a3d"), "review": ("Review before filing", "#8a6d00"),
           "do_not_file": ("Don't file on this evidence", "#8a1f1f")}[r["recommendation"]]
    parts = [f"""<!doctype html><html><head><meta charset="utf-8"><title>IndieWard check {e(r['id'])}</title>
<style>body{{font:15px/1.5 system-ui,sans-serif;max-width:1000px;margin:24px auto;padding:0 16px;color:#1d1d1f}}
.disc{{background:#fff7e0;border:1px solid #e8c95c;padding:10px 14px;border-radius:8px}}
.rec{{color:#fff;padding:10px 14px;border-radius:8px;font-weight:600}}
table{{border-collapse:collapse;width:100%;margin:8px 0;table-layout:auto}}td,th{{border:1px solid #ddd;padding:6px 8px;text-align:left;vertical-align:top;overflow-wrap:anywhere}}
.b{{color:#fff;border-radius:4px;padding:1px 6px;font-size:12px}}pre{{background:#f6f6f6;padding:8px;overflow:auto;font-size:12px;margin:0;white-space:pre-wrap;overflow-wrap:anywhere}}
.pair{{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:12px}}img{{max-width:100%;border:1px solid #ccc}}</style></head><body>
<h1>Check report: {e(r['project'])}</h1>
<p>Check {e(r['id'])} · {e(r['created_at'])} · Suspect: {e(', '.join(r['suspect']['sources']))}</p>
<p class="disc"><b>Read this first.</b> {e(r['disclaimer'])}</p>
<p class="rec" style="background:{rec[1]}">{e(rec[0])} · overall similarity {r['overall']}/100</p>
<p>{e(r['message'])}</p>
<h2>Scores by category</h2><table><tr><th>Category</th><th>Score</th><th>Filing strength</th><th>What matched</th></tr>"""]
    for c in r["categories"]:
        parts.append(f"<tr><td>{e(c['label'])}</td><td><b>{c['score']}</b>/100</td><td><span class='b' "
                     f"style='background:{badge[c['strength']]}'>{c['strength']}</span><br><small>{e(c['strength_note'])}</small></td>"
                     f"<td>{e(c['summary'])}</td></tr>")
    parts.append("</table>")
    if r["weak_only"]:
        parts.append("<p class='rec' style='background:#8a1f1f'>This report rests only on mechanics. Don't file.</p>")
    parts.append(f"<h2>Trap markers ({r['traps']['count']} found)</h2>")
    if r["traps"]["found"]:
        parts.append("<table><tr><th>Trap</th><th>Tier</th><th>Build</th><th>Value</th><th>Found in</th></tr>")
        for t in r["traps"]["found"]:
            loc = "<br>".join(e(f"{x['file']} ({x.get('encoding','')})") for x in t["found_in"])
            parts.append(f"<tr><td>{e(t['label'])}</td><td>{e(t['tier'])}</td><td>{e(str(t['build']))}</td>"
                         f"<td><code>{e(t['value'])}</code></td><td>{loc}</td></tr>")
        parts.append("</table><p><small>Each trap was recorded in your vault before release; its salted commitment "
                     "appears in your timestamped certificate, so you can show it existed before the suspect did.</small></p>")
    else:
        parts.append("<p>None found.</p>")
    parts.append(f"<h2>Watermarks ({len(r['watermarks'])} detected)</h2>")
    if r["watermarks"]:
        parts.append("<table><tr><th>Media</th><th>Your file</th><th>Suspect file</th><th>Detection strength (z)</th></tr>")
        for w in r["watermarks"]:
            parts.append(f"<tr><td>{e(w['media'])}</td><td>{e(w['registered'])}</td><td>{e(w['suspect'])}</td><td>{w['z']}</td></tr>")
        parts.append("</table><p><small>z above 6 means the chance of a false detection is about one in a billion per test.</small></p>")
    else:
        parts.append("<p>None detected. Watermarks are easy to strip; this doesn't mean nothing was copied.</p>")
    for c in r["categories"]:
        if c["key"] in ("traps",) or not c["evidence"]:
            continue
        parts.append(f"<h2>Evidence: {e(c['label'])}</h2>")
        for x in c["evidence"][:12]:
            if "orig_thumb" in x:
                o = f"<img src='evidence/{e(x['orig_thumb'])}'>" if x["orig_thumb"] else "<p>(original not on this machine)</p>"
                parts.append(f"<div class='pair'><div><b>Yours:</b> {e(x['registered'])}<br>{o}</div><div><b>Suspect:</b> "
                             f"{e(x['suspect'])}<br><img src='evidence/{e(x['suspect_thumb'])}'></div></div>"
                             f"<p>Similarity {x['similarity']}</p>")
            elif "original_excerpt" in x:
                parts.append(f"<div class='pair'><div><b>Yours:</b> {e(x['original_file'])} lines {x['original_lines']}"
                             f"<pre>{e(x['original_excerpt'])}</pre></div><div><b>Suspect:</b> {e(x['suspect_file'])} "
                             f"lines {x['suspect_lines']}<pre>{e(x['suspect_excerpt'])}</pre></div></div><p>{x['shared']} shared fingerprints</p>")
            elif "original" in x and "suspect" in x:
                parts.append(f"<div class='pair'><div><b>Yours:</b> {e(x['original'])}</div><div><b>Suspect:</b> {e(x['suspect'])}</div></div>"
                             f"<p><small>similarity {x['similarity']}</small></p>")
            else:
                parts.append(f"<pre>{e(json.dumps(x, ensure_ascii=False))}</pre>")
    parts.append(f"<hr><p class='disc'>{e(r['disclaimer'])}</p></body></html>")
    return "\n".join(parts)
