"""Trap markers ("trap streets") for game builds.

A trap is an inert, unique, made-up detail recorded in your vault: a nonsense
string, a float constant nobody would type, a function that only returns a
nonsense word, a tiny hidden image with an odd name. None of them is shown to
players, none changes gameplay or performance (each is read at most once at
startup), and none touches player data or the network.

Two tiers:
- core traps: the same in every build of the game. A cloner who diffs two of
  your builds won't see them change.
- build traps: unique to one build. They tell you which build was ripped.

Finding your trap inside a suspect build is near-proof the suspect was made
from your files, even when the art was redrawn. It proves copying, not by
itself infringement, so reports pair trap hits with the copied expressive
work (art, code, text) that came along with them.

Survival: compilers, linkers, IL2CPP stripping and JS tree-shaking delete
unreferenced code and data. Every snippet here is *referenced* once at load
so it survives. Run ``indieward traps verify <exported build>`` after every
export to confirm.
"""
from __future__ import annotations

import hashlib
import hmac
import io
import json
import secrets
import struct
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image

from . import util
from .vault import Vault

CONS = "bdfgklmnprstvz"
VOW = "aeiou"
ENGINES = ("godot", "unity", "ue5", "roblox", "web", "generic")


def _stream(key: bytes, label: str, n: int) -> bytes:
    out = b""
    i = 0
    while len(out) < n:
        out += hmac.new(key, f"{label}|{i}".encode(), hashlib.sha256).digest()
        i += 1
    return out[:n]


def _word(b: bytes) -> str:
    return "".join(CONS[x % len(CONS)] + VOW[(x // len(CONS)) % len(VOW)] for x in b)


def _token(key, label) -> str:
    b = _stream(key, label, 9)
    return f"{_word(b[:4])}{CONS[b[4] % 14]}_{_word(b[5:9])}"


def _float(key, label) -> float:
    b = _stream(key, label, 8)
    mant = int.from_bytes(b[:7], "big") / float(1 << 56)
    return float(f"{(1.0 + mant) * 1e-4 * (1 + b[7] % 7):.16g}")


def _png(key, label) -> bytes:
    b = np.frombuffer(_stream(key, label, 16 * 16 * 4), dtype=np.uint8).reshape(16, 16, 4).copy()
    b[..., 3] = 1 + b[..., 3] % 6  # nearly transparent; never displayed anyway
    buf = io.BytesIO()
    Image.fromarray(b, mode="RGBA").save(buf, format="PNG", optimize=False)
    return buf.getvalue()


def _core_scope(vault: Vault) -> str:
    from .check import _setting

    return f"core|{vault.project()['id']}|r{_setting(vault, 'core_rotation', 0)}"


def rotate_core(vault: Vault) -> int:
    """Start a new set of core traps (do this after a takedown package revealed the old ones)."""
    from .check import _setting, set_setting

    n = int(_setting(vault, "core_rotation", 0)) + 1
    set_setting(vault, "core_rotation", n)
    return n


def _names(key: bytes, scope: str) -> dict:
    """Neutral, per-project names, so a grep for a fixed prefix finds nothing."""
    w = lambda tag, n=3: _word(_stream(key, f"{scope}|name|{tag}", n))  # noqa: E731
    return {"folder": w("folder", 2), "file": w("file", 3), "cls": w("cls", 3).capitalize() + "Table",
            "fn": "_" + w("fn", 4), "asset": f"{w('asset', 2)}_{w('asset2', 2)}.png", "glob": "_" + w("glob", 3)}


def generate(vault: Vault, label: str, engine: str = "generic") -> dict:
    """Create the trap set for a new build, record it privately, return its id."""
    if engine not in ENGINES:
        raise ValueError(f"engine must be one of {', '.join(ENGINES)}")
    vault.require_verified("generate trap markers")
    key = vault.mac_key()
    build_id = "b" + secrets.token_hex(5)
    core = _core_scope(vault)
    nm = _names(key, core)
    traps = [
        ("core", "string", "loc_key", _token(key, core + "|s1")),
        ("core", "string", "meta_value", _token(key, core + "|s2")),
        ("core", "float", "constant", repr(_float(key, core + "|f1"))),
        ("core", "function", "dead_function", nm["fn"]),
        ("core", "string", "function_return", _token(key, core + "|fr")),
        ("core", "asset", "hidden_asset", nm["asset"]),
        ("core", "asset_sha256", "hidden_asset_hash", util.sha256_bytes(_png(key, core + "|png"))),
    ]
    b_scope = f"build|{vault.project()['id']}|{build_id}"
    traps += [("build", "string", "build_tag", _token(key, b_scope + "|s1")),
              ("build", "float", "build_constant", repr(_float(key, b_scope + "|f1")))]
    # Each trap has its own random salt, so revealing found traps reveals nothing about the rest.
    rows = [(tier, kind, lab, value, secrets.token_hex(16)) for tier, kind, lab, value in traps]
    commitments = [_commit(salt, tier, kind, value) for tier, kind, _, value, salt in rows]
    commitment = util.sha256_bytes("|".join(commitments).encode())
    vault.db.execute(
        "INSERT INTO builds (id,label,registered_at,engine,trap_commitment,trap_salt) VALUES (?,?,?,?,?,?)",
        (build_id, label, util.now_iso(), engine, commitment, "per-trap"),
    )
    for tier, kind, lab, value, salt in rows:
        vault.db.execute("INSERT INTO traps (build_id,tier,kind,label,value,salt) VALUES (?,?,?,?,?,?)",
                         (build_id, tier, kind, lab, value, salt))
    vault.db.commit()
    out = vault.path("traps", build_id)
    files = write_snippets(vault, build_id, out, engine)
    snippet_names = sorted({Path(f).name.lower() for f in files if not Path(f).name.startswith("README_")})
    vault.db.execute("UPDATE builds SET snippet_files=? WHERE id=?", (json.dumps(snippet_names), build_id))
    vault.db.commit()
    return {"build_id": build_id, "engine": engine, "snippets": str(out), "count": len(traps),
            "commitment": commitment}


def _commit(salt: str, tier: str, kind: str, value: str) -> str:
    return util.sha256_bytes(f"{salt}|{tier}|{kind}|{value}".encode())


def snippet_names(vault: Vault) -> set[str]:
    out = set()
    for (v,) in vault.db.execute("SELECT snippet_files FROM builds WHERE snippet_files IS NOT NULL"):
        out |= set(json.loads(v))
    return out


def is_snippet_path(path: str, names: set[str]) -> bool:
    return Path(path).name.lower() in names


def records(vault: Vault, build_id: str | None = None) -> list[dict]:
    q = "SELECT * FROM traps" + (" WHERE build_id=?" if build_id else "") + " ORDER BY id"
    rows = vault.db.execute(q, (build_id,) if build_id else ()).fetchall()
    return [dict(r) for r in rows]


def trap_commitment(vault: Vault, trap: dict) -> str:
    row = vault.db.execute("SELECT salt FROM traps WHERE id=?", (trap["id"],)).fetchone()
    return _commit(row[0], trap["tier"], trap["kind"], trap["value"])


def _vals(vault, build_id) -> dict:
    return {r["label"]: r["value"] for r in records(vault, build_id)}


GUIDE = {
    "godot": "Add {folder}/{file}.gd as an Autoload (Project > Project Settings > Autoload) and keep the {folder}/ "
             "folder in your export preset's resource filter. In the preset's Scripts tab, set GDScript Export "
             "Mode to Text or Binary tokens, not Compressed binary tokens (the 4.3+ default), which hides the "
             "trap strings.",
    "unity": "Put {cls}.cs and link.xml anywhere under Assets/, and the PNG in Assets/Resources/{folder}/. "
             "[Preserve] and link.xml keep IL2CPP from stripping it.",
    "ue5": "Add {cls}.h/.cpp to your game module and call {cls}::Touch() once from your GameInstance::Init(). C++ "
           "string literals end up in the executable, which can be scanned even when paks are encrypted. "
           "Blueprint-only: import the CSV as a String Table and the PNG as a texture, reference both from one "
           "always-loaded Data Asset, and verify against the unpacked pak.",
    "roblox": "Put the ModuleScript from ReplicatedStorage/ in ReplicatedStorage (client copies include it) and "
              "require it once from a LocalScript. Put the ServerStorage/ copy in ServerStorage; it shows up if "
              "your place file itself leaks. Roblox places can't carry loose PNGs; the strings are enough.",
    "web": "Import {folder}/{file}.js once from your entry point (it registers itself, so bundlers keep it) and "
           "serve public/{folder}/ with your build.",
    "generic": "Place each value somewhere your build keeps and reads once at load.",
}


def write_snippets(vault: Vault, build_id: str, out_dir, engine: str) -> list[str]:
    v = _vals(vault, build_id)
    key = vault.mac_key()
    core = _core_scope(vault)
    nm = _names(key, core)
    png = _png(key, core + "|png")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    files: dict[str, str | bytes] = {}
    s1, s2, k, fn, fr = v["loc_key"], v["meta_value"], v["constant"], v["dead_function"], v["function_return"]
    bt, bk, asset = v["build_tag"], v["build_constant"], v["hidden_asset"]
    fo, fi, cls, gl = nm["folder"], nm["file"], nm["cls"], nm["glob"]
    hdr = "Generated data table. Keep as is."  # deliberately bland: shipped files shouldn't announce themselves
    if engine == "godot":
        files[f"{fo}/{fi}.gd"] = f'''# {hdr}
extends Node

const _A := "{s1}"
const _B := "{s2}"
const _K := {k}
const _C := "{bt}"
const _CK := {bk}
const _ART := preload("res://{fo}/{asset}")

var _n := 0

func _ready() -> void:
\t_n = _A.length() + _B.length() + _C.length() + int(_K * 0.0) + int(_CK * 0.0)
\t_n += 0 if _ART == null else 0
\t_n += {fn}().length() * 0

func {fn}() -> String:
\treturn "{fr}"
'''
        files[f"{fo}/{asset}"] = png
    elif engine == "unity":
        files[f"{cls}.cs"] = f'''// {hdr}
using UnityEngine;
using UnityEngine.Scripting;

[Preserve]
public static class {cls}
{{
    [Preserve] public static readonly string A = "{s1}";
    [Preserve] public static readonly string B = "{s2}";
    [Preserve] public static readonly double K = {k};
    [Preserve] public static readonly string C = "{bt}";
    [Preserve] public static readonly double CK = {bk};
    static int _n;

    [Preserve, RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
    static void Touch()
    {{
        _n = A.Length + B.Length + C.Length + {fn}().Length * 0 + (int)(K * 0.0 + CK * 0.0);
        var art = Resources.Load<Texture2D>("{fo}/{Path(asset).stem}");
        _n += art == null ? 0 : 0;
    }}

    [Preserve] public static string {fn}() {{ return "{fr}"; }}
}}
'''
        files["link.xml"] = f'<linker>\n  <assembly fullname="Assembly-CSharp">\n    <type fullname="{cls}" preserve="all"/>\n  </assembly>\n</linker>\n'
        files[f"Resources/{fo}/{asset}"] = png
    elif engine == "ue5":
        files[f"Source/{cls}.h"] = f'''// {hdr}
#pragma once
#include "CoreMinimal.h"

namespace {cls}
{{
    void Touch();
    const TCHAR* {fn}();
}}
'''
        files[f"Source/{cls}.cpp"] = f'''// {hdr}
#include "{cls}.h"

namespace {cls}
{{
    static const TCHAR* GTable[] = {{ TEXT("{s1}"), TEXT("{s2}"), TEXT("{bt}") }};
    static volatile double GK = {k};
    static volatile double GCK = {bk};
    static volatile int32 GN = 0;

    const TCHAR* {fn}() {{ return TEXT("{fr}"); }}

    void Touch()
    {{
        int32 N = 0;
        for (const TCHAR* T : GTable) {{ N += FCString::Strlen(T); }}
        GN = N + (int32)(GK * 0.0 + GCK * 0.0) + FCString::Strlen({fn}()) * 0;
    }}
}}
'''
        files[f"Content/{fo}/{fi}.csv"] = f'Key,SourceString\n{s1},"{s2}"\n{bt},"{fr}"\n'
        files[f"Content/{fo}/{asset}"] = png
    elif engine == "roblox":
        mod = f'''-- {hdr}
local M = {{}}
M.a = "{s1}"
M.b = "{s2}"
M.k = {k}
M.c = "{bt}"
M.ck = {bk}
M.art = "{asset}"
function M.{fn}()
\treturn "{fr}"
end
return M
'''
        files[f"ReplicatedStorage/{cls}.lua"] = mod
        files[f"ServerStorage/{cls}Server.lua"] = mod
    elif engine == "web":
        files[f"{fo}/{fi}.js"] = f'''/*! build {bt} */
// {hdr}
export const T = ["{s1}", "{s2}", "{bt}", {k}, {bk}];
export function {fn}() {{ return "{fr}"; }}
globalThis["{gl}"] = T;  // a visible side effect, so bundlers don't tree-shake this module
'''
        files[f"public/{fo}/{fi}.json"] = json.dumps({"k": s2, "b": bt, "v": k}, indent=2) + "\n"
        files[f"public/{fo}/{asset}"] = png
    else:
        files[f"{fi}.txt"] = f"# {hdr}\n" + "\n".join(f"{lab} = {val}" for lab, val in v.items()) + "\n"
        files[asset] = png
    files["README_INDIEWARD.txt"] = (
        "Trap markers for this build. Do NOT ship this README. Keep the values secret.\n"
        "These files are inert: read once at startup, never shown, no network, no player data.\n\n"
        + GUIDE[engine].format(folder=fo, file=fi, cls=cls) + "\n\n"
        "Harder to spot: also hide the traps in one of your own localization or data files (CSV, JSON or PO)\n"
        f"  indieward traps inject --build {build_id} --into <your file>   (shows a diff; add --apply to write)\n"
        "\nAfter exporting, run:\n"
        f"  indieward build register --build {build_id} <exported build>\n")
    written = []
    for name, content in files.items():
        p = out / name
        p.parent.mkdir(parents=True, exist_ok=True)
        (p.write_bytes if isinstance(content, bytes) else p.write_text)(content)
        written.append(str(p))
    return written


# --- scanning -----------------------------------------------------------------

def _lz4_block(src: bytes, usize: int) -> bytes:
    dst = bytearray()
    i, n = 0, len(src)
    while i < n:
        tok = src[i]
        i += 1
        lit = tok >> 4
        if lit == 15:
            while True:
                b = src[i]
                i += 1
                lit += b
                if b != 255:
                    break
        dst += src[i : i + lit]
        i += lit
        if i >= n or len(dst) >= usize:
            break
        off = src[i] | (src[i + 1] << 8)
        i += 2
        ml = tok & 15
        if ml == 15:
            while True:
                b = src[i]
                i += 1
                ml += b
                if b != 255:
                    break
        ml += 4
        start = len(dst) - off
        for k in range(ml):
            dst.append(dst[start + k])
    return bytes(dst)


def _rbxl_chunks(data: bytes) -> bytes:
    """Decompress a binary Roblox place/model so its strings are searchable."""
    out = bytearray()
    i = 32
    while i + 16 <= len(data):
        name = data[i : i + 4]
        clen, ulen = struct.unpack_from("<II", data, i + 4)
        i += 16
        body = data[i : i + (clen or ulen)]
        i += clen or ulen
        if clen:
            if body[:4] == b"\x28\xb5\x2f\xfd":
                try:
                    import zstandard  # optional

                    body = zstandard.ZstdDecompressor().decompress(body, max_output_size=ulen)
                except Exception:
                    continue
            else:
                body = _lz4_block(body, ulen)
        out += body
        if name == b"END\x00":
            break
    return bytes(out)


def iter_blobs(root, max_bytes: int = 512 << 20):
    """Yield (display path, bytes) for every file, looking inside zips and .rbxl places."""
    for p in util.iter_files(root):
        try:
            if p.stat().st_size > max_bytes:
                continue
            data = p.read_bytes()
        except OSError:
            continue
        name = str(p)
        yield name, data
        if data[:4] == b"PK\x03\x04":
            try:
                with zipfile.ZipFile(io.BytesIO(data)) as z:
                    for info in z.infolist():
                        if not info.is_dir() and info.file_size <= max_bytes:
                            yield f"{name}!/{info.filename}", z.read(info)
            except zipfile.BadZipFile:
                pass
        if data[:8] == b"<roblox!" and data[8:9] == b"\x89":
            yield f"{name}!/decompressed", _rbxl_chunks(data)


def _needles(trap: dict) -> list[tuple[str, bytes]]:
    v = trap["value"]
    if trap["kind"] == "float":
        f = float(v)
        out = [("float64-le", struct.pack("<d", f))]
        for fmt in ("%.15g", "%.16g", "%.17g", "%r"):
            s = (fmt % f) if fmt != "%r" else repr(f)
            out.append(("text", s.encode()))
        return list({b: (lab, b) for lab, b in out}.values())  # dedupe identical encodings
    if trap["kind"] == "asset_sha256":
        return []
    text = v
    return [("utf-8", text.encode()), ("utf-16le", text.encode("utf-16-le")), ("utf-32le", text.encode("utf-32-le"))]


def scan(root, trap_rows: list[dict]) -> dict:
    """Search a build (folder, archive or file) for trap markers."""
    asset_hashes = {t["value"]: t for t in trap_rows if t["kind"] == "asset_sha256"}
    needles = [(t, enc, nd) for t in trap_rows for enc, nd in _needles(t)]
    hits: dict[int, dict] = {}
    files = 0
    for name, data in iter_blobs(root):
        files += 1
        h = util.sha256_bytes(data)
        if h in asset_hashes:
            t = asset_hashes[h]
            hits.setdefault(t["id"], {**_pub(t), "found_in": []})["found_in"].append(
                {"file": name, "encoding": "exact file"})
        if data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) < 4096 and asset_hashes:
            try:
                im = np.asarray(Image.open(io.BytesIO(data)).convert("RGBA"))
                for t in asset_hashes.values():
                    ref = _png_from_hash_row(t)
                    if ref is not None and im.shape == ref.shape and np.array_equal(im, ref):
                        hits.setdefault(t["id"], {**_pub(t), "found_in": []})["found_in"].append(
                            {"file": name, "encoding": "same pixels"})
            except Exception:
                pass
        for t, enc, nd in needles:
            off = data.find(nd)
            if off >= 0:
                hits.setdefault(t["id"], {**_pub(t), "found_in": []})["found_in"].append(
                    {"file": name, "offset": off, "encoding": enc})
    found = list(hits.values())
    core = sum(1 for f in found if f["tier"] == "core")
    build_ids = sorted({f["build_id"] for f in found if f["tier"] == "build"})
    return {"files_scanned": files, "found": found, "core_found": core, "builds_identified": build_ids,
            "total_traps": len({t["id"] for t in trap_rows})}


_PNG_CACHE: dict[str, np.ndarray] = {}


def _png_from_hash_row(t: dict):
    return _PNG_CACHE.get(t["value"])


def prime_png_cache(vault: Vault) -> None:
    from .check import _setting

    key = vault.mac_key()
    for r in range(int(_setting(vault, "core_rotation", 0)) + 1):
        data = _png(key, f"core|{vault.project()['id']}|r{r}|png")
        _PNG_CACHE[util.sha256_bytes(data)] = np.asarray(Image.open(io.BytesIO(data)).convert("RGBA"))


def _pub(t: dict) -> dict:
    return {"id": t["id"], "build_id": t["build_id"], "tier": t["tier"], "kind": t["kind"], "label": t["label"],
            "value": t["value"]}


def verify_build(vault: Vault, build_id: str, build_path) -> dict:
    """Post-export check: are this build's traps present in the exported files?"""
    rows = records(vault, build_id)
    if not rows:
        raise ValueError(f"unknown build {build_id}")
    prime_png_cache(vault)
    res = scan(build_path, rows)
    found_ids = {f["id"] for f in res["found"]}
    missing = [_pub(t) | {"value": "(hidden)"} for t in rows if t["id"] not in found_ids]
    ok = res["core_found"] >= 2 and any(f["tier"] == "build" for f in res["found"])
    manifest = util.sha256_bytes(util.canonical_json(sorted(
        util.sha256_bytes(d) for _, d in iter_blobs(build_path))))
    vault.db.execute("UPDATE builds SET verified_at=?, verify_result=?, manifest_sha256=? WHERE id=?",
                     (util.now_iso(), json.dumps({"ok": ok, "found": len(found_ids), "of": len(rows)}), manifest,
                      build_id))
    vault.db.commit()
    return {"ok": ok, "found": len(found_ids), "of": len(rows), "missing": missing,
            "files_scanned": res["files_scanned"], "manifest_sha256": manifest,
            "advice": None if ok else
            "Some traps were stripped by the export. Make sure the snippet is referenced at startup and its "
            "folder is included in the export, then export and verify again."}


def scan_all(vault: Vault, suspect_path) -> dict:
    prime_png_cache(vault)
    return scan(suspect_path, records(vault))
