"""P2-06 research: built-in audio mark vs Meta AudioSeal on IndieWard's test music.

    pip install audioseal            # MIT; weights (~93 MB) come from huggingface.co/facebook/audioseal
    TORCHDYNAMO_DISABLE=1 python scripts/research_audioseal.py [n_clips]

Research only; IndieWard doesn't use AudioSeal. Results: docs/research/neural-backends.md.
"""
import subprocess, sys, tempfile, time, warnings
from pathlib import Path
warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tests")]
import numpy as np, torch
import gamefixture as gf
from indieward import mediaio, wm_audio, payload as pl
from audioseal import AudioSeal
gen = AudioSeal.load_generator("audioseal_wm_16bits"); det = AudioSeal.load_detector("audioseal_detector_16bits")
SR = 44100; d = tempfile.mkdtemp()
def ff(src, dst, *args):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src, *args, dst], check=True)
def through(x, sr, ext, args):
    mediaio.write_audio(f"{d}/in.wav", x, sr); ff(f"{d}/in.wav", f"{d}/out{ext}", *args); return mediaio.read_audio(f"{d}/out{ext}", sr=sr)[0]
A = {"none": None, "MP3 128k": (".mp3", ["-b:a", "128k"]), "MP3 64k": (".mp3", ["-b:a", "64k"]),
     "Ogg q2": (".ogg", ["-c:a", "libvorbis", "-q:a", "2"]), "AAC 96k": (".m4a", ["-c:a", "aac", "-b:a", "96k"]),
     "tempo 1.05 (pitch kept)": (".wav", ["-af", "atempo=1.05"]), "tempo 0.95 (pitch kept)": (".wav", ["-af", "atempo=0.95"]),
     "speed 1.05 (pitch shifts)": (".wav", ["-af", f"asetrate={int(SR*1.05)},aresample={SR}"]),
     "trim first 3 s": "trim"}
def attack(x, k):
    a = A[k]
    if a is None: return x
    if a == "trim": return x[3*SR:]
    return through(x, SR, *a)
def as_detect(x):
    mono = torch.tensor(x.mean(1), dtype=torch.float32)[None, None]
    wav16 = torch.tensor(np.interp(np.arange(0, len(x), SR/16000), np.arange(len(x)), x.mean(1)), dtype=torch.float32)[None, None]
    p, msg = det.detect_watermark(wav16, 16000)
    return float(p), msg[0].round().int().tolist()
def as_embed(x, msg):
    m = x.mean(1)
    wav16 = torch.tensor(np.interp(np.arange(0, len(m), SR/16000), np.arange(len(m)), m), dtype=torch.float32)[None, None]
    with torch.no_grad(): wm = gen.get_watermark(wav16, 16000, message=torch.tensor([msg]))
    wm44 = np.interp(np.arange(len(m)) * 16000 / SR, np.arange(wav16.shape[-1]), wm[0, 0].numpy())
    return x + wm44[:, None]
N = int(sys.argv[1]) if len(sys.argv) > 1 else 4
key = b"k" * 32
okb = dict.fromkeys(A, 0); oka = dict.fromkeys(A, 0); okm = dict.fromkeys(A, 0); acc = {k: [] for k in A}
snr_b, snr_a, fa, t_emb = [], [], 0, []
as_embed(gf._music(1, seconds=2.0), [0] * 16)  # warm-up
#; snr_b, snr_a = [], []; fa = 0; t_emb = []
for s in range(N):
    x = gf._music(10 + s, seconds=12.0)
    if s % 2: x = 0.7 * x + 0.05 * np.random.default_rng(s).standard_normal(x.shape)  # odd clips: music + noise bed
    p = pl.make(key, pl.new_record_id()); msg = [int(b) for b in format(p >> 48, "016b")]
    xb = wm_audio.embed_array(x, SR, p); ref = wm_audio.reference(x, SR)
    t = time.time(); xa = as_embed(x, msg); t_emb.append(time.time() - t)
    snr_b.append(10*np.log10(np.sum(x**2)/np.sum((xb-x)**2))); snr_a.append(10*np.log10(np.sum(x**2)/np.sum((xa-x)**2)))
    pr, _ = as_detect(x); fa += pr > 0.5
    for k in A:
        okb[k] += wm_audio.match_array(attack(xb, k), SR, p, ref)["detected"]
        pr, m = as_detect(attack(xa, k)); oka[k] += pr > 0.5; okm[k] += (pr > 0.5 and m == msg); acc[k].append(np.mean(np.array(m) == np.array(msg)))
print(f"SNR built-in {np.mean(snr_b):.1f} dB, AudioSeal {np.mean(snr_a):.1f} dB; AudioSeal embed {np.mean(t_emb):.2f} s per 12 s clip (CPU); unmarked flagged by AudioSeal: {fa}/{N}")
print("| Edit | Built-in (informed, 64 bits) | AudioSeal detected | AudioSeal 16-bit message exact | AudioSeal bit accuracy |\n| --- | --- | --- | --- | --- |")
for k in A: print(f"| {k} | {okb[k]}/{N} | {oka[k]}/{N} | {okm[k]}/{N} | {100*np.mean(acc[k]):.0f}% |")
