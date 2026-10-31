"""Optional image backend: Adobe TrustMark carrying the IW-Mark v1 payload.

Install with ``pip install "indieward[trustmark]"`` (pulls in PyTorch; CPU is
fine). Then ``indieward register --backend trustmark`` marks images with
TrustMark instead of the built-in watermark.

Why it exists: the built-in image mark is *informed*. Only the owner, holding
the vault reference, can find it. TrustMark is a *blind* neural watermark:
anyone with the open TrustMark decoder can read the 64-bit payload straight
from the image, so a store or platform could read the record ID without the
creator's vault. Whether a payload is genuine still needs the creator's MAC
key (see payload.py), so reading a mark doesn't let anyone forge one.

Packing (documented in docs/spec/iw-mark-v1.md, section 2.1):
TrustMark variant Q, BCH_4 mode: 100 bits = 68 data + 28 ECC + 4 schema bits,
correcting up to 4 flipped bits. The 68 data bits are the 64-bit payload
followed by the 4-bit tag ``0001`` ("IW-Mark v1"), so a TrustMark written by
another tool isn't mistaken for an IndieWard mark.

Trade-off: it is more visible than the built-in mark (about 41 dB PSNR versus
46 dB on the test art) in exchange for blind reading and tolerance of ~10%
crops and slight rotation, which defeat the built-in check.

Limits, stated plainly: heavy JPEG (quality 50 and below) sometimes defeats
it; large crops, rotation beyond a few degrees, AI regeneration or redrawing,
and TrustMark's own published remover defeat it. An unmarked image can decode
as a valid BCH packet by chance; the tag and the MAC check rule that out.

The model weights download once, from TrustMark's official host
(cai-watermark.adobe.net), the first time the backend is used. They are MIT
licensed like the code. IndieWard checks their published MD5 checksums before
use and refuses to run if they don't match.
"""
from __future__ import annotations

import hashlib
import pathlib

import numpy as np
from PIL import Image

from . import payload as pl, wm_core

BACKEND = "trustmark-q-bch4-v1"
MODEL_TYPE = "Q"
TAG = "0001"  # 4 data bits after the 64-bit payload: IW-Mark v1
SCHEMA_BCH_4 = 2  # TrustMark's schema number for BCH_4 (TrustMark.Encoding.BCH_4)
MIN_SIDE = 96

_TM = None


class Unavailable(RuntimeError):
    pass


def available() -> bool:
    try:
        import trustmark  # noqa: F401
    except ImportError:
        return False
    return True


def _verify_weights(tm_mod) -> None:
    """Refuse to run on model files that don't match TrustMark's published checksums."""
    models = pathlib.Path(tm_mod.__file__).parent / "models"
    for name in (f"trustmark_{MODEL_TYPE}.yaml", f"encoder_{MODEL_TYPE}.ckpt", f"decoder_{MODEL_TYPE}.ckpt"):
        f = models / name
        want = tm_mod.MODEL_CHECKSUMS[name]
        got = hashlib.md5(f.read_bytes()).hexdigest() if f.is_file() else None
        if got != want:
            raise Unavailable(f"TrustMark model file {f} is missing or doesn't match its published checksum; "
                              "delete it and run again to re-download from cai-watermark.adobe.net")


def _tm():
    global _TM
    if _TM is None:
        try:
            from trustmark import TrustMark, trustmark as tm_mod
        except ImportError as e:
            raise Unavailable('the TrustMark backend needs: pip install "indieward[trustmark]"') from e
        tm = TrustMark(verbose=False, model_type=MODEL_TYPE, encoding_type=TrustMark.Encoding.BCH_4,
                       loadRemover=False, device="cpu")
        _verify_weights(tm_mod)
        _TM = tm
    return _TM


def _bits(payload: int) -> str:
    return format(payload, f"0{wm_core.NBITS}b") + TAG


def embed_file(src, dst, payload: int) -> dict:
    img = Image.open(src)
    alpha = None
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        alpha = img.convert("RGBA").getchannel("A")
    rgb = img.convert("RGB")
    if min(rgb.size) < MIN_SIDE:
        raise ValueError(f"image too small to watermark ({rgb.width}x{rgb.height}); minimum side is {MIN_SIDE}px")
    out = _tm().encode(rgb, _bits(payload), MODE="binary")
    a, b = np.asarray(rgb, dtype=np.float64), np.asarray(out, dtype=np.float64)
    psnr = 10 * np.log10(255.0**2 / max(float(np.mean((a - b) ** 2)), 1e-12))
    if alpha is not None:
        out = out.convert("RGBA")
        out.putalpha(alpha)
    params = {"quality": 95} if str(dst).lower().endswith((".jpg", ".jpeg")) else {}
    out.save(dst, **params)
    return {"psnr_db": round(float(psnr), 2), "width": rgb.width, "height": rgb.height,
            "trustmark": {"model": MODEL_TYPE, "ecc": "BCH_4"}}


def decode_image(img: Image.Image) -> int | None:
    """Blind read. Returns the 64-bit payload, or None if no IW-Mark TrustMark was found.

    A returned payload is only a claim: check it with payload.is_genuine.
    """
    secret, found, schema = _tm().decode(img.convert("RGB"), MODE="binary")
    if not found or schema != SCHEMA_BCH_4 or len(secret) < wm_core.NBITS + len(TAG) or secret[wm_core.NBITS:wm_core.NBITS + len(TAG)] != TAG:
        return None
    return int(secret[:wm_core.NBITS], 2)


def read(img: Image.Image, mac_key: bytes) -> dict | None:
    """Blind read plus the owner's MAC check. None when there is no IW-Mark at all."""
    p = decode_image(img)
    if p is None:
        return None
    rid, _ = pl.split(p)
    return {"payload": f"{p:016x}", "record": pl.fmt(rid), "record_id": rid, "genuine": pl.is_genuine(mac_key, p)}


def matches(img: Image.Image, mac_key: bytes, rows: list[dict]) -> list[tuple[dict, dict]]:
    """Registered TrustMark rows whose payload was read from ``img`` with a genuine MAC.

    Unlike the built-in check there is no z-score: the BCH code, the tag and the
    24-bit MAC together are the evidence. Even if an unmarked image decodes as a
    valid BCH packet (it happens), it must also carry the 4-bit tag and a MAC
    only the creator's key produces: under one chance in a billion per image.
    """
    tm_rows = [r for r in rows if r.get("wm_backend") == BACKEND and r.get("wm_payload")]
    if not tm_rows:
        return []
    got = read(img, mac_key)
    if not got or not got["genuine"]:
        return []
    m = {"backend": BACKEND, "detected": True, "mac_ok": True, "z": None}
    return [(r, dict(m)) for r in tm_rows if r["wm_payload"] == got["payload"]]
