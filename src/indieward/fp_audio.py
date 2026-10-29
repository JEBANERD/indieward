"""Audio fingerprints: spectral-peak landmarks (the approach behind Shazam).

Peaks in the spectrogram are paired into (f1, f2, dt) hashes with a time
offset. A copy shares many hashes at one consistent offset. Survives
re-encoding, volume changes, trimming and mild noise. Fails on re-recorded
or re-composed music, pitch shifts and speed changes. Chromaprint/AcoustID
(LGPL) is a mature alternative backend.
"""
from __future__ import annotations

from collections import Counter
from math import gcd

import numpy as np
from scipy.ndimage import maximum_filter
from scipy.signal import resample_poly, stft

SR = 8000
N_FFT, HOP = 512, 128
FAN_OUT = 6


def _peaks(x: np.ndarray) -> list[tuple[int, int]]:
    _, _, z = stft(x, fs=SR, nperseg=N_FFT, noverlap=N_FFT - HOP, window="hann")
    s = np.log(np.abs(z) + 1e-6)
    s[:4] = s.min()  # ignore DC/rumble
    loc = maximum_filter(s, size=(15, 9)) == s
    thr = np.percentile(s, 92)
    f, t = np.nonzero(loc & (s > thr))
    order = np.argsort(t)
    return list(zip(t[order].tolist(), f[order].tolist()))


def fingerprint_array(data: np.ndarray, sr: int) -> dict:
    mono = data.mean(axis=1) if data.ndim == 2 else data
    if sr != SR:
        g = gcd(int(sr), SR)
        mono = resample_poly(mono, SR // g, int(sr) // g)
    peaks = _peaks(mono)
    hashes = []
    for i, (t1, f1) in enumerate(peaks):
        n = 0
        for t2, f2 in peaks[i + 1 :]:
            dt = t2 - t1
            if dt < 1:
                continue
            if dt > 64 or n >= FAN_OUT:
                break
            hashes.append([(f1 << 16) | (f2 << 6) | dt, t1])
            n += 1
    return {"hashes": hashes, "seconds": round(len(mono) / SR, 2)}


def compare(fa: dict, fb: dict) -> dict:
    """How much of the shorter clip lines up with the other at one offset."""
    index: dict[int, list[int]] = {}
    for h, t in fa["hashes"]:
        index.setdefault(h, []).append(t)
    offsets = Counter()
    for h, t in fb["hashes"]:
        for ta in index.get(h, ()):
            offsets[ta - t] += 1
    if not offsets:
        return {"confidence": 0.0, "aligned_hashes": 0, "offset_s": 0.0}
    off, n = offsets.most_common(1)[0]
    shorter = max(1, min(len(fa["hashes"]), len(fb["hashes"])))
    frac = n / shorter
    conf = float(np.clip((frac - 0.03) / 0.17, 0, 1)) * min(1.0, n / 40.0)
    return {"confidence": round(conf, 3), "aligned_hashes": n, "offset_s": round(off * HOP / SR, 2)}
