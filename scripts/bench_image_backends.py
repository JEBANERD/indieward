"""Compare the built-in image watermark with the optional TrustMark backend.

    pip install -e ".[trustmark]"
    python scripts/bench_image_backends.py [n_images]

Marks synthetic test art (tests/gamefixture.py) with both backends, applies
common edits, and prints a Markdown table of how often each mark is still
found: built-in with its informed check, TrustMark with a blind read plus the
MAC check. Also counts unmarked images that TrustMark + MAC wrongly accept.
Runs offline after TrustMark's weights are downloaded once.
"""
from __future__ import annotations

import io
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tests")]

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

import gamefixture as gf  # noqa: E402
from indieward import payload as pl, wm_image, wm_trustmark  # noqa: E402


def _jpeg(im, q):
    b = io.BytesIO()
    im.save(b, "JPEG", quality=q)
    return Image.open(io.BytesIO(b.getvalue())).convert("RGB")


def _crop(im, f):
    w, h = im.size
    dx, dy = int(w * f), int(h * f)
    return im.crop((dx, dy, w - dx, h - dy))


def _half(im):
    return im.resize((im.width // 2, im.height // 2), Image.Resampling.LANCZOS)


EDITS = {
    "none": lambda i: i,
    "JPEG 90": lambda i: _jpeg(i, 90),
    "JPEG 75": lambda i: _jpeg(i, 75),
    "JPEG 50": lambda i: _jpeg(i, 50),
    "half size": _half,
    "half size + JPEG 75": lambda i: _jpeg(_half(i), 75),
    "crop 5% per side": lambda i: _crop(i, 0.05),
    "crop 10% per side": lambda i: _crop(i, 0.10),
    "rotate 2°": lambda i: i.rotate(2, Image.Resampling.BICUBIC),
}


def main(n: int = 12) -> None:
    key = b"bench-key".ljust(32, b"\0")
    ok_b, ok_t = dict.fromkeys(EDITS, 0), dict.fromkeys(EDITS, 0)
    psnr_b, psnr_t, false_t = [], [], 0
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        for s in range(n):
            orig = gf._art(200 + s, size=512).convert("RGB")
            orig.save(d / "src.png")
            p = pl.make(key, pl.new_record_id())
            info_b, ref = wm_image.embed_file(d / "src.png", d / "b.png", p)
            info_t = wm_trustmark.embed_file(d / "src.png", d / "t.png", p)
            psnr_b.append(info_b["psnr_db"])
            psnr_t.append(info_t["psnr_db"])
            b, t = Image.open(d / "b.png").convert("RGB"), Image.open(d / "t.png").convert("RGB")
            for name, edit in EDITS.items():
                ok_b[name] += wm_image.match_array(np.asarray(edit(b), dtype=np.float64), p, ref)["detected"]
                got = wm_trustmark.read(edit(t), key)
                ok_t[name] += bool(got and got["genuine"] and int(got["payload"], 16) == p)
            got = wm_trustmark.read(orig, key)
            false_t += bool(got and got["genuine"])
    print(f"PSNR: built-in {np.mean(psnr_b):.1f} dB, TrustMark {np.mean(psnr_t):.1f} dB ({n} images, 512x512)\n")
    print("| Edit | Built-in (informed) | TrustMark (blind + MAC) |\n| --- | --- | --- |")
    for name in EDITS:
        print(f"| {name} | {ok_b[name]}/{n} | {ok_t[name]}/{n} |")
    print(f"\nUnmarked images accepted by TrustMark + MAC: {false_t}/{n}")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 12)
