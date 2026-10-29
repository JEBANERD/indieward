"""Video fingerprints: perceptual hashes of one frame per second.

Matches re-uploads and re-encodes of your trailers and gameplay clips, and
suspect store-page videos that reuse your footage. Doesn't match a new
recording of a remade game.
"""
from __future__ import annotations

import numpy as np
from PIL import Image

from . import fp_image, mediaio


def fingerprint_file(path, fps: float = 1.0, max_frames: int = 600) -> dict:
    frames = []
    for i, f in enumerate(mediaio.iter_frames(path, size=(160, 90), fps=fps)):
        if i >= max_frames:
            break
        frames.append(fp_image.fingerprint_image(Image.fromarray(f.astype(np.uint8))))
    return {"fps": fps, "frames": frames}


def compare(fa: dict, fb: dict) -> dict:
    """Share of the suspect's sampled frames that match some frame of ours."""
    if not fa["frames"] or not fb["frames"]:
        return {"confidence": 0.0, "matched_frames": 0, "of": len(fb["frames"])}
    hits = []
    for j, s in enumerate(fb["frames"]):
        best = max(fp_image.similarity(o, s) for o in fa["frames"])
        if best >= 0.5:
            hits.append((j, best))
    frac = len(hits) / len(fb["frames"])
    return {"confidence": round(float(min(1.0, frac * 1.25)), 3), "matched_frames": len(hits),
            "of": len(fb["frames"]), "example_seconds": [j for j, _ in hits[:5]]}
