"""Built-in invisible image watermark (IW-Mark v1, image profile).

How it works
------------
The 64-bit payload is spread over low/mid DCT coefficients of the image's
luminance, resampled to a fixed 256x256 grid. Because the grid is fixed, the
mark doesn't depend on the image's size, so it survives resizing and display
scaling. Low/mid frequencies survive JPEG, WebP and PNG re-saves.

Detection is *informed*: at registration the vault keeps a small reference of
the original (its 256x256 luminance grid, about 128 KB). When checking a
suspect, IndieWard aligns the suspect to that reference (undoing resizes and
small edge crops from screenshots), subtracts it, and correlates what is left
with the payload pattern, weighting each coefficient by how noisy its
neighbourhood is (resampling error is uneven across the band). Taking the host image out of the comparison is what
lets the mark stay faint and still be found after re-encodes.

Limits, stated plainly: heavy crops (more than about 5% a side), rotation,
mirroring, AI regeneration or redrawing, and targeted removal all defeat it.
Only the owner, holding the vault reference, can run the strong check. A
blind ``decode`` exists for the open format, but it is unreliable at this
strength; the optional TrustMark backend is the right choice for marks that
third parties should be able to read. Trap markers and fingerprints are the
backstop.
"""
from __future__ import annotations

import io

import numpy as np
from PIL import Image
from scipy.fft import dctn, idctn
from scipy.ndimage import gaussian_filter, uniform_filter

from . import wm_core

GRID = 256
LABEL = "image"
ALPHA = 0.04  # pattern strength relative to the local DCT envelope
MIN_SIDE = 96
LINE = tuple(float(x) for x in np.round(np.arange(0, 0.0501, 0.0025), 4))


def _band_mask() -> np.ndarray:
    u, v = np.meshgrid(np.arange(GRID), np.arange(GRID), indexing="ij")
    s = u + v
    return (s >= 4) & (s <= 96) & (u <= 80) & (v <= 80)


BAND = _band_mask()
N_FEAT = int(BAND.sum())


def luma(rgb: np.ndarray) -> np.ndarray:
    return 0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]


def _resize_f(a: np.ndarray, w: int, h: int, method=Image.Resampling.BOX) -> np.ndarray:
    return np.asarray(Image.fromarray(a.astype(np.float32), mode="F").resize((w, h), method), dtype=np.float64)


def to_grid(y: np.ndarray) -> np.ndarray:
    return _resize_f(y, GRID, GRID)


def _envelope(c: np.ndarray) -> np.ndarray:
    env = uniform_filter(np.abs(c), size=7, mode="nearest")
    floor = np.percentile(env[BAND], 10) + 1e-6
    return np.maximum(env, floor)


def _activity_mask(y: np.ndarray) -> np.ndarray:
    """Scale the mark down in flat areas (where it would show) and up in texture."""
    k = max(3, int(min(y.shape) / 64) | 1)
    mean = uniform_filter(y, size=k)
    sd = np.sqrt(np.maximum(uniform_filter(y * y, size=k) - mean * mean, 0))
    ref = np.median(sd) + 1e-6
    return np.clip(sd / ref, 0.3, 1.6)


def load_rgb(path) -> tuple[np.ndarray, np.ndarray | None]:
    img = Image.open(path)
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        arr = np.asarray(img.convert("RGBA"), dtype=np.float64)
        return arr[..., :3], arr[..., 3]
    return np.asarray(img.convert("RGB"), dtype=np.float64), None


def load_rgb_bytes(data: bytes) -> np.ndarray:
    return np.asarray(Image.open(io.BytesIO(data)).convert("RGB"), dtype=np.float64)


def embed_array(rgb: np.ndarray, payload: int, alpha: float = ALPHA) -> tuple[np.ndarray, np.ndarray]:
    """Return (watermarked rgb, reference grid of the original)."""
    h, w = rgb.shape[:2]
    if min(h, w) < MIN_SIDE:
        raise ValueError(f"image too small to watermark ({w}x{h}); minimum side is {MIN_SIDE}px")
    y = luma(rgb)
    ref = to_grid(y)
    c = dctn(ref, norm="ortho")
    env = _envelope(c)
    lay = wm_core.layout(LABEL, N_FEAT)
    delta_c = np.zeros_like(c)
    delta_c[BAND] = alpha * env[BAND] * wm_core.signs_for(payload, lay)
    delta = _resize_f(idctn(delta_c, norm="ortho"), w, h, Image.Resampling.BICUBIC)
    delta *= _activity_mask(y)
    out = np.clip(np.rint(rgb + delta[..., None]), 0, 255)
    return out, ref.astype(np.float32)


def embed_file(src, dst, payload: int, alpha: float = ALPHA) -> tuple[dict, np.ndarray]:
    rgb, a = load_rgb(src)
    out, ref = embed_array(rgb, payload, alpha)
    psnr = 10 * np.log10(255.0**2 / max(float(np.mean((out - rgb) ** 2)), 1e-12))
    if a is not None:
        img = Image.fromarray(np.dstack([out, a]).astype(np.uint8), mode="RGBA")
    else:
        img = Image.fromarray(out.astype(np.uint8), mode="RGB")
    params = {"quality": 95} if str(dst).lower().endswith((".jpg", ".jpeg")) else {}
    img.save(dst, **params)
    return {"psnr_db": round(float(psnr), 2), "width": rgb.shape[1], "height": rgb.shape[0]}, ref


# --- alignment -------------------------------------------------------------

def _canvas(y: np.ndarray, margins, ref: np.ndarray) -> tuple[np.ndarray, tuple]:
    """Put the suspect back where it would sit in the uncropped original.

    Areas the crop removed are filled from the reference, so they contribute
    nothing to the residual.
    """
    a, b, c, d = margins  # fraction cropped away: left, right, top, bottom
    x0, y0 = int(round(GRID * a)), int(round(GRID * c))
    x1, y1 = GRID - int(round(GRID * b)), GRID - int(round(GRID * d))
    inner = _resize_f(y, x1 - x0, y1 - y0)
    canvas = ref.astype(np.float64).copy()
    canvas[y0:y1, x0:x1] = inner
    return canvas, (x0, y0, x1, y1)


def _ncc(canvas: np.ndarray, ref_blur: np.ndarray, box) -> float:
    x0, y0, x1, y1 = box
    a = gaussian_filter(canvas, 1.5)[y0:y1, x0:x1].ravel()
    b = ref_blur[y0:y1, x0:x1].ravel()
    a = a - a.mean()
    b = b - b.mean()
    return float(a @ b / (np.sqrt((a @ a) * (b @ b)) + 1e-9))


def align(y: np.ndarray, ref: np.ndarray) -> tuple[np.ndarray, tuple, float]:
    ref_blur = gaussian_filter(ref.astype(np.float64), 1.5)
    m = [0.0, 0.0, 0.0, 0.0]
    canvas, box = _canvas(y, m, ref)
    best = _ncc(canvas, ref_blur, box)
    for _ in range(3):
        improved = False
        for i in range(4):
            for val in LINE:
                trial = list(m)
                trial[i] = val
                cv, bx = _canvas(y, trial, ref)
                score = _ncc(cv, ref_blur, bx)
                if score > best + 1e-7:
                    best, m, improved = score, trial, True
        if not improved:
            break
    canvas, _ = _canvas(y, m, ref)
    return canvas, tuple(m), best


def _whiten(resid: np.ndarray, size: int = 9) -> np.ndarray:
    """Weight each in-band residual by 1 / its local noise power.

    After a screenshot, what is left once the reference is subtracted is
    mostly resampling and misalignment error, and it is very uneven across
    the band (strong near edges in the host, weak elsewhere). The mark itself
    is spread evenly, so dividing by the local power (the matched-filter
    weighting) stops a few noisy coefficients from swamping the score. The
    weights don't depend on the payload, so the decoy z-score stays valid.
    """
    inside = BAND.astype(np.float64)
    power = uniform_filter(resid * resid, size, mode="constant")
    power /= np.maximum(uniform_filter(inside, size, mode="constant"), 1e-9)
    return (resid / np.maximum(power, 1e-12))[BAND]


def match_array(rgb: np.ndarray, payload: int, ref: np.ndarray) -> dict:
    """Owner-side informed check of one suspect image against one registered mark."""
    y = luma(rgb)
    canvas, margins, ncc = align(y, ref)
    cs = dctn(canvas, norm="ortho")
    cr = dctn(ref.astype(np.float64), norm="ortho")
    env = _envelope(cr)
    # Undo brightness/contrast changes before subtracting the reference.
    xs, xr = cs[BAND], cr[BAND]
    gain = float(xs @ xr / (xr @ xr + 1e-9))
    resid = np.zeros_like(cs)
    resid[BAND] = (xs - gain * xr) / env[BAND]
    lay = wm_core.layout(LABEL, N_FEAT)
    z = wm_core.zscore(_whiten(resid), wm_core.signs_for(payload, lay), lay)
    return {
        "z": round(float(z), 2),
        "detected": bool(z >= wm_core.DETECT_Z),
        "alignment_ncc": round(ncc, 4),
        "crop_margins": margins,
    }


def decode_array(rgb: np.ndarray) -> tuple[int, float]:
    """Blind read of the payload. Unreliable at the default strength (see module doc)."""
    grid = to_grid(luma(rgb))
    c = dctn(grid, norm="ortho")
    lay = wm_core.layout(LABEL, N_FEAT)
    payload, conf = wm_core.decode((c / _envelope(c))[BAND], lay)
    return payload, float(np.mean(np.abs(conf)))
