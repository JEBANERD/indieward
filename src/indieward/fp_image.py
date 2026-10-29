"""Art and UI fingerprints: perceptual hashes on recolor-tolerant views.

For each image IndieWard keeps:
- pHash and dHash of equalized luminance (survive resize, recompress, small edits)
- pHash of a chroma-invariant edge map (max gradient across R, G and B), which
  survives hue shifts and palette swaps because shapes keep their outlines
- a 24x24 edge-map thumbnail for cosine similarity
- the same hashes for the mirrored image

Images with little detail (flat fills, plain gradients, two-tone scenes) are
not compared at all, because perceptual hashes can't tell them apart.

Fails on true redraws, heavy crops and new compositions. Screenshots of a
scene only match registered screenshots or key art, not individual sprites;
register your own screenshots too. An optional CLIP backend can add semantic
similarity.
"""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageOps
from scipy.fft import dctn

THUMB = 24


def _gray_eq(img: Image.Image) -> Image.Image:
    return ImageOps.equalize(img.convert("L"))


def _edge_raw(img: Image.Image, size: int = 96) -> np.ndarray:
    a = np.asarray(img.convert("RGB").resize((size, size), Image.Resampling.BOX), dtype=np.float64)
    gx = np.abs(np.diff(a, axis=1, append=a[:, -1:, :]))
    gy = np.abs(np.diff(a, axis=0, append=a[-1:, :, :]))
    return np.max(gx + gy, axis=2)


def _edge(img: Image.Image, size: int = 96) -> np.ndarray:
    e = _edge_raw(img, size)
    return e / (e.max() + 1e-9)


# Images with too little detail (flat fills, plain gradients, two-tone scenes) carry almost no
# information for perceptual hashing; any two of them look "identical". They are not compared.
MIN_DETAIL = 0.06


def detail(img: Image.Image) -> float:
    """Share of pixels on a clear edge, at 96x96."""
    return float((_edge_raw(img) > 12).mean())


def _phash(arr: np.ndarray) -> int:
    img = Image.fromarray((arr * 255 if arr.max() <= 1.0 else arr).astype(np.float32), mode="F")
    a = np.asarray(img.resize((32, 32), Image.Resampling.BOX), dtype=np.float64)
    c = dctn(a, norm="ortho")[:8, :8].ravel()
    med = np.median(c[1:])
    return int("".join("1" if v > med else "0" for v in c), 2)


def _dhash(img: Image.Image) -> int:
    a = np.asarray(img.resize((9, 8), Image.Resampling.BOX), dtype=np.float64)
    bits = (a[:, 1:] > a[:, :-1]).ravel()
    return int("".join("1" if b else "0" for b in bits), 2)


def _thumb(e: np.ndarray) -> list[float]:
    t = np.asarray(Image.fromarray(e.astype(np.float32), mode="F").resize((THUMB, THUMB), Image.Resampling.BOX))
    t = t - t.mean()
    n = np.linalg.norm(t) + 1e-9
    return [round(float(x), 4) for x in (t / n).ravel()]


def fingerprint_image(img: Image.Image) -> dict:
    img = img.convert("RGB")
    out = {}
    for tag, im in (("", img), ("m_", ImageOps.mirror(img))):
        g = _gray_eq(im)
        e = _edge(im)
        out[tag + "ph"] = f"{_phash(np.asarray(g, dtype=np.float64)):016x}"
        out[tag + "dh"] = f"{_dhash(g):016x}"
        out[tag + "eh"] = f"{_phash(e):016x}"
        if not tag:
            out["thumb"] = _thumb(e)
    out["size"] = list(img.size)
    out["detail"] = round(detail(img), 4)
    return out


def fingerprint_file(path) -> dict:
    with Image.open(path) as im:
        return fingerprint_image(im)


def _sim_hash(a: str, b: str) -> float:
    return 1.0 - bin(int(a, 16) ^ int(b, 16)).count("1") / 64.0


def similarity(fa: dict, fb: dict) -> float:
    """0..1 confidence that fb is a copy or edit of fa. 0 when either image is too plain to judge."""
    if fa.get("detail", 1.0) < MIN_DETAIL or fb.get("detail", 1.0) < MIN_DETAIL:
        return 0.0
    best_hash = 0.0
    for tag in ("", "m_"):
        for k in ("ph", "dh", "eh"):
            best_hash = max(best_hash, _sim_hash(fa[k], fb[tag + k]))
    cos = float(np.dot(fa["thumb"], fb["thumb"]))
    # Random image pairs sit near 0.5 hash similarity and 0.0-0.3 cosine.
    c_hash = np.clip((best_hash - 0.72) / 0.22, 0, 1)
    c_cos = np.clip((cos - 0.55) / 0.35, 0, 1)
    # Both views must agree: hashes alone collide on simple images, cosine alone on similar layouts.
    return float(np.sqrt(c_hash * c_cos))
