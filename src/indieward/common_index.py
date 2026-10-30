"""IndieWard's built-in common-material index (data/common.json, built by scripts/build_common.py).

Code fingerprints of popular bundled libraries and normalized lines of common licence texts, so
shared material doesn't count as copying. Library fingerprints are excluded only for libraries a
suspect actually bundles: big libraries share many generic k-grams with ordinary code, and
excluding all of them everywhere would hide real copying.
"""
from __future__ import annotations

import base64
import json
import zlib
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).with_name("data") / "common.json"
MIN_SHARE = 0.10  # a suspect bundles a library when it has at least this share of its fingerprints...
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
    lines = frozenset(line for lic in d["licences"] for line in lic["lines"])
    return {"libraries": libs, "lines": lines}


def detect(fingerprints) -> tuple[list[str], set[str]]:
    """Libraries bundled in this set of code fingerprints, and the fingerprints to exclude for them."""
    fps = set(fingerprints)
    names, exclude = [], set()
    for lib in load()["libraries"]:
        n = len(fps & lib["fingerprints"])
        if n >= MIN_SHARED and n >= MIN_SHARE * len(lib["fingerprints"]):
            names.append(f"{lib['name']}@{lib['version']}")
            exclude |= lib["fingerprints"]
    return names, exclude


def licence_lines() -> frozenset[str]:
    return load()["lines"]
