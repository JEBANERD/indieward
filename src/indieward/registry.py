"""Register assets and builds: hash, watermark, fingerprint, record."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np

from . import fp_audio, fp_code, fp_image, fp_text, fp_video, mediaio, payload as pl, traps, util
from . import wm_audio, wm_image, wm_trustmark, wm_video
from .vault import Vault

DEFAULT_CATEGORY = {"image": "art", "audio": "audio", "video": "video", "code": "code", "text": "text",
                    "other": "other"}
CATEGORIES = ("art", "ui", "logo", "audio", "video", "code", "text", "other")
IMAGE_BACKENDS = ("builtin", "trustmark")


def _save_json(path: Path, obj) -> None:
    path.write_text(json.dumps(obj))


def register_file(vault: Vault, path, category: str | None = None, watermark: bool = True,
                  out_dir=None, keep_copy: bool = False, note: str | None = None, backend: str = "builtin") -> dict:
    vault.require_verified("register assets")
    if backend not in IMAGE_BACKENDS:
        raise ValueError(f"image backend must be one of {', '.join(IMAGE_BACKENDS)}")
    path = Path(path)
    kind = util.kind_for(path)
    category = category or DEFAULT_CATEGORY[kind]
    if category not in CATEGORIES:
        raise ValueError(f"category must be one of {', '.join(CATEGORIES)}")
    sha = util.sha256_file(path)
    dup = vault.db.execute("SELECT record_id FROM assets WHERE sha256=?", (sha,)).fetchone()
    if dup:
        return {"skipped": True, "reason": "already registered", "record": pl.fmt(dup[0]), "path": str(path)}
    rid = pl.new_record_id()
    while vault.db.execute("SELECT 1 FROM assets WHERE record_id=?", (rid,)).fetchone():
        rid = pl.new_record_id()
    payload = pl.make(vault.mac_key(), rid)
    out_dir = Path(out_dir) if out_dir else vault.project_root / "indieward_out"
    info: dict = {}
    wm_out = ref_path = None
    image_backend, backend = backend, None
    fp: dict = {}

    if kind == "image":
        fp = fp_image.fingerprint_file(path)
        if watermark and image_backend == "trustmark":
            out_dir.mkdir(parents=True, exist_ok=True)
            wm_out = out_dir / path.name
            info = wm_trustmark.embed_file(path, wm_out, payload)
            backend = wm_trustmark.BACKEND
        elif watermark:
            out_dir.mkdir(parents=True, exist_ok=True)
            wm_out = out_dir / path.name
            info, ref = wm_image.embed_file(path, wm_out, payload)
            ref_path = vault.path("refs", f"{rid:010x}.npy")
            np.save(ref_path, ref.astype(np.float16))
            backend = "builtin-image-v1"
    elif kind == "audio":
        data, sr = mediaio.read_audio(path)
        fp = fp_audio.fingerprint_array(data, sr)
        if watermark:
            out_dir.mkdir(parents=True, exist_ok=True)
            wm_out = out_dir / path.name
            marked = wm_audio.embed_array(data, sr, payload)
            mediaio.write_audio(wm_out, marked, sr)
            ref_path = vault.path("refs", f"{rid:010x}.npy")
            np.save(ref_path, wm_audio.reference(data, sr))
            snr = 10 * np.log10(np.sum(data**2) / max(np.sum((marked - data) ** 2), 1e-12))
            info = {"snr_db": round(float(snr), 1), "sample_rate": sr, "seconds": round(len(data) / sr, 2)}
            backend = "builtin-audio-v1"
    elif kind == "video":
        fp = fp_video.fingerprint_file(path)
        if watermark:
            out_dir.mkdir(parents=True, exist_ok=True)
            wm_out = out_dir / (path.stem + ".mp4")
            info = wm_video.embed_file(path, wm_out, payload)
            backend = "builtin-video-v1"
    elif kind == "code":
        fp = fp_code.fingerprint_files([path])
    elif kind == "text":
        fp = {"lines": fp_text.lines_from_file(path)}

    fp_path = vault.path("fp", f"{rid:010x}.json")
    _save_json(fp_path, fp)
    if keep_copy:
        dst = vault.path("assets", f"{rid:010x}{path.suffix.lower()}")
        shutil.copy2(path, dst)
    vault.db.execute(
        "INSERT INTO assets (record_id,kind,category,name,source_path,sha256,size,registered_at,wm_payload,"
        "wm_backend,wm_info,wm_output,wm_output_sha256,ref_path,fp_path,note) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (rid, kind, category, path.name, str(path.resolve()), sha, path.stat().st_size, util.now_iso(),
         f"{payload:016x}" if wm_out else None, backend, json.dumps(info) if info else None,
         str(wm_out) if wm_out else None, util.sha256_file(wm_out) if wm_out else None,
         vault.rel(ref_path) if ref_path else None, vault.rel(fp_path), note),
    )
    vault.db.commit()
    return {"record": pl.fmt(rid), "kind": kind, "category": category, "sha256": sha,
            "watermarked": str(wm_out) if wm_out else None, "backend": backend, **({"quality": info} if info else {})}


def register_path(vault: Vault, path, category: str | None = None, watermark: bool = True, out_dir=None,
                  keep_copy: bool = False, backend: str = "builtin") -> list[dict]:
    vault.require_verified("register assets")
    path = Path(path)
    results = []
    for p in util.iter_files(path):
        if util.kind_for(p) == "other":
            continue
        try:
            results.append(register_file(vault, p, category, watermark, out_dir, keep_copy, backend=backend))
        except ValueError as e:  # e.g. too small to watermark: register without a mark
            if watermark:
                r = register_file(vault, p, category, False, out_dir, keep_copy)
                r["note"] = f"not watermarked: {e}"
                results.append(r)
            else:
                raise
    return results


def register_build(vault: Vault, build_id: str, build_path) -> dict:
    """Store fingerprints for an exported build and confirm its traps survived."""
    vault.require_verified("register builds")
    res = traps.verify_build(vault, build_id, build_path)
    code_blobs, text_lines = {}, []
    snip = traps.snippet_names(vault)
    for name, data in traps.iter_blobs(build_path):
        inner = name.split("!/")[-1]
        if traps.is_snippet_path(inner, snip) or util.is_vendor_path(inner):
            continue  # trap snippets are matched as traps; bundled third-party code isn't yours
        k = util.kind_for(inner)
        if k in ("code", "text") and len(data) < 5_000_000:
            txt = data.decode("utf-8", "replace")
            if k == "code":
                code_blobs[Path(name).name] = txt
            else:
                text_lines += fp_text.split_lines(txt)
    fp = {"code": fp_code.fingerprint_text_blobs(code_blobs), "lines": text_lines[:20000]}
    fp_path = vault.path("fp", f"build_{build_id}.json")
    _save_json(fp_path, fp)
    vault.db.execute("UPDATE builds SET fp_path=? WHERE id=?", (vault.rel(fp_path), build_id))
    vault.db.commit()
    return {**res, "build_id": build_id, "fingerprints": {"code": len(fp["code"]["fingerprints"]),
                                                          "text_lines": len(fp["lines"])}}


def assets(vault: Vault, kind: str | None = None) -> list[dict]:
    q = "SELECT * FROM assets" + (" WHERE kind=?" if kind else "") + " ORDER BY id"
    return [dict(r) for r in vault.db.execute(q, (kind,) if kind else ()).fetchall()]


def load_fp(vault: Vault, row: dict) -> dict:
    return json.loads(vault.path(row["fp_path"]).read_text())
