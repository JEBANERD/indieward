"""IndieWard's built-in common-material index (data/common.json, built by scripts/build_common.py).

Code fingerprints of popular bundled libraries and normalized lines of common licence texts, so
shared material doesn't count as copying. Library fingerprints are excluded only for libraries a
suspect actually bundles: big libraries share many generic k-grams with ordinary code, and
excluding all of them everywhere would hide real copying.

Detection looks only at each library's unique fingerprints (in no other indexed library), because
big libraries also share generic JS, WebGL and maths patterns with each other: a three.js bundle
would otherwise "contain" excalibur. Once a library is detected, all its fingerprints are excluded.

A library is detected from any one of its indexed build files (development or production, global or
ES module): a game ships one build, and that build can be a small share of the library's whole set.
A thin entry file with fewer than MIN_SHARED unique fingerprints can't detect a library on its own.
"""
from __future__ import annotations

import base64
import json
import zlib
from collections import Counter
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).with_name("data") / "common.json"
MIN_SHARE = 0.10  # a suspect bundles a library when it has at least this share of its unique fingerprints...
MIN_SHARED = 200  # ...and at least this many


def _unpack_list(b64: str) -> list[str]:
    raw = zlib.decompress(base64.b64decode(b64))
    return [str(int.from_bytes(raw[i:i + 8], "big")) for i in range(0, len(raw), 8)]


def _unpack_indices(b64: str) -> list[int]:
    out, cur, shift, prev = [], 0, 0, -1
    for b in zlib.decompress(base64.b64decode(b64)):
        cur |= (b & 0x7F) << shift
        if b & 0x80:
            shift += 7
        else:
            prev += cur
            out.append(prev)
            cur, shift = 0, 0
    return out


@lru_cache(maxsize=1)
def load() -> dict:
    if not DATA.exists():
        return {"libraries": [], "lines": frozenset()}
    d = json.loads(DATA.read_text(encoding="utf-8"))
    if d.get("format") != 2:
        raise ValueError(f"{DATA}: unsupported common index format {d.get('format')!r}; rebuild with scripts/build_common.py")
    libs = []
    for x in d["libraries"]:
        ordered = _unpack_list(x["fingerprints"])
        libs.append({"name": x["name"], "version": x["version"], "fingerprints": frozenset(ordered),
                     "files": [frozenset(ordered[i] for i in _unpack_indices(f["indices"])) for f in x["files"]]})
    _add_unique(libs)
    lines = frozenset(line for lic in d["licences"] for line in lic["lines"])
    return {"libraries": libs, "lines": lines}


def _add_unique(libs: list[dict]) -> None:
    """Set each library's detection sets, one per build file: that file's fingerprints in no other indexed library.

    "detect" is the same thing for the whole library. Libraries given without per-file data count as one file."""
    seen = Counter(f for lib in libs for f in lib["fingerprints"])
    for lib in libs:
        unique = frozenset(f for f in lib["fingerprints"] if seen[f] == 1)
        # A library made almost entirely of another's code falls back to all its fingerprints,
        # so a standalone copy of it is still detected.
        whole = len(unique) >= MIN_SHARED
        lib["detect"] = unique if whole else lib["fingerprints"]
        files = lib.get("files") or [lib["fingerprints"]]
        lib["detect_files"] = [f & unique if whole else f for f in files]


def _trips(fps: set, detect: frozenset) -> bool:
    n = len(fps & detect)
    return n >= MIN_SHARED and n >= MIN_SHARE * len(detect)


def detect(fingerprints) -> tuple[list[str], set[str]]:
    """Libraries bundled in this set of code fingerprints, and the fingerprints to exclude for them."""
    fps = set(fingerprints)
    names, exclude = [], set()
    for lib in load()["libraries"]:
        if any(_trips(fps, d) for d in lib["detect_files"]):
            names.append(f"{lib['name']}@{lib['version']}")
            exclude |= lib["fingerprints"]
    return names, exclude


def licence_lines() -> frozenset[str]:
    return load()["lines"]
