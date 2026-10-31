"""IndieWard's built-in common-material index (data/common.json, built by scripts/build_common.py).

Code fingerprints of popular bundled libraries and normalized lines of common licence texts, so
shared material doesn't count as copying. Library fingerprints are excluded only for libraries a
suspect actually bundles: big libraries share many generic k-grams with ordinary code, and
excluding all of them everywhere would hide real copying.

Detection looks only at each library's unique fingerprints (in no other indexed library), because
big libraries also share generic JS, WebGL and maths patterns with each other: a three.js bundle
would otherwise "contain" excalibur. Once a library is detected, all its fingerprints are excluded.
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


def _unpack(b64: str) -> frozenset[str]:
    raw = zlib.decompress(base64.b64decode(b64))
    return frozenset(str(int.from_bytes(raw[i:i + 8], "big")) for i in range(0, len(raw), 8))


@lru_cache(maxsize=1)
def load() -> dict:
    if not DATA.exists():
        return {"libraries": [], "lines": frozenset()}
    d = json.loads(DATA.read_text(encoding="utf-8"))
    libs = [{"name": x["name"], "version": x["version"], "fingerprints": _unpack(x["fingerprints"])}
            for x in d["libraries"]]
    _add_unique(libs)
    lines = frozenset(line for lic in d["licences"] for line in lic["lines"])
    return {"libraries": libs, "lines": lines}


def _add_unique(libs: list[dict]) -> None:
    """Set each library's "detect" fingerprints: those in no other indexed library."""
    seen = Counter(f for lib in libs for f in lib["fingerprints"])
    for lib in libs:
        unique = frozenset(f for f in lib["fingerprints"] if seen[f] == 1)
        # A library made almost entirely of another's code falls back to all its fingerprints,
        # so a standalone copy of it is still detected.
        lib["detect"] = unique if len(unique) >= MIN_SHARED else lib["fingerprints"]


def detect(fingerprints) -> tuple[list[str], set[str]]:
    """Libraries bundled in this set of code fingerprints, and the fingerprints to exclude for them."""
    fps = set(fingerprints)
    names, exclude = [], set()
    for lib in load()["libraries"]:
        n = len(fps & lib["detect"])
        if n >= MIN_SHARED and n >= MIN_SHARE * len(lib["detect"]):
            names.append(f"{lib['name']}@{lib['version']}")
            exclude |= lib["fingerprints"]
    return names, exclude


def licence_lines() -> frozenset[str]:
    return load()["lines"]
