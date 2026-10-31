"""P2-06 research: built-in video mark vs Meta Video Seal 1.0 (256 bits) on IndieWard's test clips.

    pip install videoseal torchvision     # MIT; weights (228 MB) from dl.fbaipublicfiles.com/videoseal/
    TORCHDYNAMO_DISABLE=1 python scripts/research_videoseal.py WORKDIR [n_clips]

videoseal 1.0.1 from PyPI looks for videoseal/cards and configs/attenuation.yaml
relative to the current folder, so WORKDIR must contain videoseal/cards (a link
to the installed package's cards folder) and configs/attenuation.yaml (from the
official PyPI sdist). Weights download into WORKDIR/ckpts.

The 64-bit IW-Mark payload is repeated 4 times across the 256 bits; reading sums
the 4 soft copies. Research only; IndieWard doesn't use Video Seal.
Results: docs/research/neural-backends.md.
"""
import os, subprocess, sys, tempfile, time, warnings
from pathlib import Path
warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tests")]
os.chdir(sys.argv[1])
import numpy as np, torch
import gamefixture as gf
from indieward import mediaio, wm_video, payload as pl
import videoseal
torch.set_grad_enabled(False)
vs = videoseal.load("videoseal"); vs.eval()
d = tempfile.mkdtemp(); key = b"k" * 32
def ff(src, dst, *args): subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src, *args, dst], check=True)
def bits256(p): b = [int(c) for c in format(p, "064b")]; return torch.tensor([b * 4], dtype=torch.float32)
def vs_embed(src, dst, p):
    info = mediaio.video_info(src); fr = np.stack(list(mediaio.iter_frames(src)))
    x = torch.from_numpy(fr).permute(0, 3, 1, 2).float() / 255
    out = []
    for i in range(0, len(x), 32):
        out.append(vs.embed(x[i:i+32], msgs=bits256(p), is_video=True)["imgs_w"])
    y = (torch.cat(out).clamp(0, 1) * 255).permute(0, 2, 3, 1).numpy()
    w = mediaio.FrameWriter(dst, info["width"], info["height"], info["fps"], crf=18)
    for f in y: w.write(f)
    w.close()
    return 10 * np.log10(255**2 / np.mean((np.rint(y) - fr) ** 2))
def vs_read(path):
    fr = np.stack(list(mediaio.iter_frames(path)))
    x = torch.from_numpy(fr).permute(0, 3, 1, 2).float() / 255
    logits = torch.cat([vs.detect(x[i:i+32], is_video=True)["preds"][:, 1:] for i in range(0, len(x), 32)])
    while logits.dim() > 2: logits = logits.mean(-1)
    soft = logits.mean(0).reshape(4, 64).sum(0)
    return int("".join("1" if v > 0 else "0" for v in soft.tolist()), 2)
A = {"as encoded (CRF 18)": None, "H.264 CRF 28": ["-c:v", "libx264", "-crf", "28"], "H.264 CRF 35": ["-c:v", "libx264", "-crf", "35"],
     "half size + CRF 28": ["-vf", "scale=320:-2", "-c:v", "libx264", "-crf", "28"],
     "crop 10% per side": ["-vf", "crop=iw*0.8:ih*0.8", "-c:v", "libx264", "-crf", "23"],
     "15 fps": ["-r", "15", "-c:v", "libx264", "-crf", "23"], "trim first 3 s": ["-ss", "3", "-c:v", "libx264", "-crf", "23"]}
def attack(src, k):
    if A[k] is None: return src
    dst = f"{d}/att.mp4"; ff(src, dst, *A[k]); return dst
N = int(sys.argv[2]) if len(sys.argv) > 2 else 3
okb = dict.fromkeys(A, 0); okv = dict.fromkeys(A, 0); bacc = {k: [] for k in A}; ps = []; fpv = 0; te = []
for s in range(N):
    arts = [gf._art(300 + 4 * s + i, size=256) for i in range(4)]
    src = f"{d}/src.mp4"; gf._video(Path(src), arts, seconds=10)
    p = pl.make(key, pl.new_record_id())
    wm_video.embed_file(src, f"{d}/b.mp4", p)
    t = time.time(); ps.append(vs_embed(src, f"{d}/v.mp4", p)); te.append(time.time() - t)
    fpv += pl.is_genuine(key, vs_read(src))
    for k in A:
        okb[k] += wm_video.match_file(attack(f"{d}/b.mp4", k), p)["detected"]
        got = vs_read(attack(f"{d}/v.mp4", k))
        okv[k] += (got == p and pl.is_genuine(key, got))
        bacc[k].append(np.mean([a == b for a, b in zip(format(got, "064b"), format(p, "064b"))]))
    print("video", s, "done", flush=True)
print(f"Video Seal PSNR {np.mean(ps):.1f} dB (pre-encode); embed {np.mean(te):.0f} s per 10 s 640x360 clip (CPU); unmarked accepted (MAC): {fpv}/{N}")
print("| Edit | Built-in (blind z, 64 bits) | Video Seal 64-bit payload exact + MAC | Video Seal bit accuracy |\n| --- | --- | --- | --- |")
for k in A: print(f"| {k} | {okb[k]}/{N} | {okv[k]}/{N} | {100*np.mean(bacc[k]):.0f}% |")
