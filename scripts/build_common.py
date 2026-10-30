"""Rebuild src/indieward/data/common.json, IndieWard's default common-material index.

    python scripts/build_common.py

Downloads pinned npm tarballs (checked against the registry's sha512 integrity), reads the
bundled library files in memory and stores only their code fingerprints, never their source.
Licence texts come from the CC0 `spdx-license-list` package and are stored as normalized lines.
Same pins, same output.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import re
import sys
import tarfile
import urllib.request
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from indieward import fp_code, fp_text  # noqa: E402

REGISTRY = "https://registry.npmjs.org"
# (npm package, pinned version, regex of files inside the tarball to fingerprint)
LIBS = [
    ("three", "0.187.0", r"^package/build/[^/]+\.(?:js|cjs|mjs)$"),
    ("phaser", "4.2.1", r"^package/dist/[^/]+\.(?:js|mjs)$"),
    ("pixi.js", "8.22.0", r"^package/dist/[^/]+\.(?:js|mjs)$"),
    ("howler", "2.2.4", r"^package/dist/[^/]+\.js$"),
    ("matter-js", "0.20.0", r"^package/build/[^/]+\.js$"),
    ("lodash", "4.18.1", r"^package/(?:lodash|lodash\.min|core|core\.min)\.js$"),
]
LICENCE_PKG = ("spdx-license-list", "6.12.0")
LICENCES = ["MIT", "Apache-2.0", "BSD-3-Clause", "CC-BY-4.0", "OFL-1.1"]
OUT = ROOT / "src" / "indieward" / "data" / "common.json"


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "IndieWard build_common.py"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def _tarball(name: str, version: str) -> tuple[dict, tarfile.TarFile]:
    meta = json.loads(_get(f"{REGISTRY}/{name}/{version}"))
    dist = meta["dist"]
    data = _get(dist["tarball"])
    algo, want = dist["integrity"].split("-", 1)
    if algo != "sha512" or base64.b64encode(hashlib.sha512(data).digest()).decode() != want:
        raise SystemExit(f"{name}@{version}: tarball integrity mismatch")
    return {"name": name, "version": version, "license": meta.get("license"), "tarball": dist["tarball"],
            "integrity": dist["integrity"]}, tarfile.open(fileobj=io.BytesIO(data), mode="r:gz")


def pack(fps: set[int]) -> str:
    """Sorted big-endian uint64s, zlib-compressed, base64."""
    raw = b"".join(h.to_bytes(8, "big") for h in sorted(fps))
    return base64.b64encode(zlib.compress(raw, 9)).decode()


def build() -> dict:
    libs = []
    for name, version, pattern in LIBS:
        info, tar = _tarball(name, version)
        rx = re.compile(pattern)
        fps: set[int] = set()
        files = []
        for m in sorted(tar.getmembers(), key=lambda m: m.name):
            if m.isfile() and rx.match(m.name):
                text = tar.extractfile(m).read().decode("utf-8", "replace")
                fps |= set(fp_code.winnow(fp_code.tokens_with_lines(text)))
                files.append(m.name.removeprefix("package/"))
        libs.append({**info, "files": files, "count": len(fps), "fingerprints": pack(fps)})
        print(f"{name}@{version}: {len(files)} files, {len(fps)} fingerprints", file=sys.stderr)
    info, tar = _tarball(*LICENCE_PKG)
    full = json.loads(tar.extractfile("package/spdx-full.json").read())
    licences = []
    for lid in LICENCES:
        lines = sorted({fp_text.normalize(x) for x in fp_text.split_lines(full[lid]["licenseText"])})
        licences.append({"id": lid, "lines": lines})
    return {"format": 1, "generated_by": "scripts/build_common.py", "k": fp_code.K, "w": fp_code.W,
            "libraries": libs, "licence_source": {k: info[k] for k in ("name", "version", "license", "integrity")},
            "licences": licences}


if __name__ == "__main__":
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(build(), indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {OUT} ({OUT.stat().st_size // 1024} KB)", file=sys.stderr)
