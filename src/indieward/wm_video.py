"""Built-in invisible video watermark (IW-Mark v1, video profile).

Each frame carries the image-profile pattern (low/mid DCT coefficients of
luminance on a fixed 256x256 grid), switched on and off over time by a slow
pseudo-random sequence (0.3 s slots, a prime-length period of 61 slots). The
detector decodes the suspect at 10 frames per second, projects every frame
onto the payload pattern, and searches all offsets of the time sequence.
Static backgrounds and UI cancel out in that correlation; what's left is the
mark plus noise that averages away over seconds of footage. No reference file
is needed, so this check also works on clips cut from a longer video.

Survives: H.264/H.265/VP9 re-encodes, downscaling to 240p or larger (tested
720p to 480p, 360p and 240p), frame-rate changes, trimming, platform
transcodes. Defeated by: very small copies that are also heavily compressed
(320x180 at H.264 CRF 28 lost it; 320x180 at CRF 18 kept it), cropping
more than a few percent, mirroring, heavy overlays, speed changes, screen
recording at an angle, AI re-generation, and targeted removal. Meta's Video
Seal was tested as an alternative; it isn't proven on game footage yet
(docs/research/neural-backends.md).

Visible burn-in marks (``burn_in``) are a deterrent, not protection: they can
be painted out, but they make casual reposts traceable.
"""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy.fft import dctn, idctn

from . import mediaio, wm_core, wm_image

LABEL = "video"
SLOT_S, N_SLOTS, RATE = 0.3, 61, 10.0
ALPHA = 0.06
DETECT_Z = 7.0
REFRESH_S = 0.5  # recompute the content-adaptive pattern this often


def _video_band() -> np.ndarray:
    # Same band as stills. Tested lower bands do worse: the host picture has more
    # energy there, and blind detection has no reference to subtract it.
    return wm_image.BAND.copy()


BAND = _video_band()
N_FEAT = int(BAND.sum())


def _pattern(y: np.ndarray, signs: np.ndarray, alpha: float) -> np.ndarray:
    h, w = y.shape
    grid = wm_image.to_grid(y)
    c = dctn(grid, norm="ortho")
    env = wm_image._envelope(c)
    delta_c = np.zeros_like(c)
    delta_c[BAND] = alpha * env[BAND] * signs
    delta = wm_image._resize_f(idctn(delta_c, norm="ortho"), w, h, Image.Resampling.BICUBIC)
    return delta * wm_image._activity_mask(y)


def embed_file(src, dst, payload: int, alpha: float = ALPHA, crf: int = 18) -> dict:
    info = mediaio.video_info(src)
    lay = wm_core.layout(LABEL, N_FEAT)
    signs = wm_core.signs_for(payload, lay)
    writer = mediaio.FrameWriter(dst, info["width"], info["height"], info["fps"],
                                 audio_src=src if info["has_audio"] else None, crf=crf)
    delta = None
    next_refresh = 0.0
    n = 0
    for i, frame in enumerate(mediaio.iter_frames(src)):
        t = i / info["fps"]
        if delta is None or t >= next_refresh:
            delta = _pattern(wm_image.luma(frame), signs, alpha)
            next_refresh = t + REFRESH_S
        chip = float(wm_core.temporal_chip(LABEL, np.array([t]), SLOT_S, N_SLOTS)[0])
        writer.write(frame + (chip * delta)[..., None])
        n += 1
    writer.close()
    return {"frames": n, "fps": round(info["fps"], 3), "width": info["width"], "height": info["height"]}


def _series(path, payload: int):
    lay = wm_core.layout(LABEL, N_FEAT)
    signs = wm_core.signs_for(payload, lay)
    feats = []
    for g in mediaio.iter_frames(path, size=(wm_image.GRID, wm_image.GRID), gray=True, fps=RATE):
        c = dctn(g, norm="ortho")
        f = (c / wm_image._envelope(c))[BAND]
        feats.append((f - f.mean()).astype(np.float32))
    if not feats:
        return np.zeros(0), np.zeros((wm_core.N_DECOYS, 0))
    F = np.stack(feats)
    # Remove slow changes in the picture (pans, fades): subtract a 1-second moving average.
    k = int(RATE)
    pad = np.pad(F, ((k // 2, k // 2), (0, 0)), mode="edge")
    cs = np.cumsum(pad, axis=0, dtype=np.float64)
    cs = np.vstack([np.zeros((1, F.shape[1])), cs])
    F = F - ((cs[k:] - cs[:-k]) / k)[: F.shape[0]]
    return F @ signs, (F @ lay.decoys.T).T


def match_file(path, payload: int) -> dict:
    sig, dec = _series(path, payload)
    if len(sig) < RATE * 3:
        return {"z": 0.0, "detected": False, "note": "clip shorter than 3 seconds"}
    times = np.arange(len(sig)) / RATE
    z, offset = wm_core.offset_zscore(times, sig, dec, LABEL, SLOT_S, N_SLOTS, RATE)
    return {"z": round(float(z), 2), "detected": bool(z >= DETECT_Z), "seconds_checked": round(len(sig) / RATE, 1)}


def burn_in(src, dst, text: str, opacity: float = 0.55, crf: int = 18) -> dict:
    """Burn a visible corner mark (e.g. '@studio · IW 3f9a') into every frame."""
    info = mediaio.video_info(src)
    w, h = info["width"], info["height"]
    size = max(12, h // 28)
    try:
        font = ImageFont.load_default(size=size)
    except TypeError:  # Pillow < 10.1
        font = ImageFont.load_default()
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    box = draw.textbbox((0, 0), text, font=font)
    tw, th = box[2] - box[0], box[3] - box[1]
    x, y = w - tw - size, h - th - size
    draw.rectangle((x - size // 3, y - size // 3, x + tw + size // 3, y + th + size // 2), fill=(0, 0, 0, int(110 * opacity)))
    draw.text((x, y), text, font=font, fill=(255, 255, 255, int(255 * opacity)))
    ov = np.asarray(layer, dtype=np.float64)
    a = ov[..., 3:4] / 255.0
    writer = mediaio.FrameWriter(dst, w, h, info["fps"], audio_src=src if info["has_audio"] else None, crf=crf)
    n = 0
    for frame in mediaio.iter_frames(src):
        writer.write(frame * (1 - a) + ov[..., :3] * a)
        n += 1
    writer.close()
    return {"frames": n, "text": text}


def preview(src, dst, max_height: int = 720, crf: int = 26) -> None:
    """Lower-resolution public preview (the masters stay private)."""
    mediaio.transcode(src, dst, ["-vf", f"scale=-2:'min({max_height},ih)'", "-c:v", "libx264",
                                 "-preset", "veryfast", "-crf", str(crf), "-c:a", "aac", "-b:a", "128k"])
