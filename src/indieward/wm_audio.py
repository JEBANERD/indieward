"""Built-in invisible audio watermark (IW-Mark v1, audio profile).

The payload pattern is a set of +/- gains on narrow frequency bands (40 Hz
wide, 200-7000 Hz), switched on and off in time by a slow pseudo-random
sequence (0.2 s slots, a prime-length period of 61 slots so it never lines up
with a musical tempo). The detector projects the suspect's log-spectrum onto
the payload pattern and searches all offsets of the time sequence, so a
trimmed clip is still found. Steady sounds and rhythm cancel out in that
correlation, which keeps music from fooling the detector. Bands are defined in Hz,
not FFT bins, so resampling doesn't matter.

Survives: MP3, AAC, Ogg re-encodes; resampling; volume changes; trimming;
mixing down to mono. Defeated by: speed or pitch changes, heavy noise, re-recording
or re-composing the music, and targeted removal. Meta's AudioSeal was tested as
an alternative and didn't do better (docs/research/neural-backends.md).
"""
from __future__ import annotations

import numpy as np
from math import gcd

from scipy.signal import istft, resample_poly, stft

from . import wm_core

LABEL = "audio"
F_LO, F_HI, BAND_HZ = 200.0, 7000.0, 40.0
N_BANDS = int((F_HI - F_LO) // BAND_HZ)
SLOT_S, N_SLOTS = 0.2, 61
AN_SR, AN_N, AN_HOP = 16000, 1024, 256  # fixed analysis setup so any input lines up
RATE = AN_SR / AN_HOP  # 62.5 analysis frames per second
ALPHA = 0.04  # log-gain in nepers (about 0.35 dB) while a slot is "on"
DETECT_Z = 7.0  # best-of-offsets scores have a heavier tail than a single test
MIN_SECONDS = 4.0


def _nperseg(sr: int) -> int:
    n = 1
    while n < 0.046 * sr:
        n <<= 1
    return n


def _band_index(freqs: np.ndarray) -> np.ndarray:
    idx = np.floor((freqs - F_LO) / BAND_HZ).astype(np.int64)
    idx[(freqs < F_LO) | (idx >= N_BANDS)] = -1
    return idx


def embed_array(data: np.ndarray, sr: int, payload: int, alpha: float = ALPHA) -> np.ndarray:
    if data.ndim == 1:
        data = data[:, None]
    if data.shape[0] < MIN_SECONDS * sr:
        raise ValueError(f"audio too short to watermark; minimum is {MIN_SECONDS:.0f} seconds")
    n = _nperseg(sr)
    lay = wm_core.layout(LABEL, N_BANDS)
    s = wm_core.signs_for(payload, lay)
    out = np.empty_like(data)
    for ch in range(data.shape[1]):
        f, t, z = stft(data[:, ch], fs=sr, nperseg=n, noverlap=3 * n // 4, window="hann")
        b = _band_index(f)
        pattern = np.where(b >= 0, s[np.maximum(b, 0)], 0.0)
        gain = np.exp(alpha * np.outer(pattern, wm_core.temporal_chip(LABEL, t, SLOT_S, N_SLOTS)))
        _, y = istft(z * gain, fs=sr, nperseg=n, noverlap=3 * n // 4, window="hann", boundary=True)
        out[:, ch] = y[: data.shape[0]] if len(y) >= data.shape[0] else np.pad(y, (0, data.shape[0] - len(y)))
    return out


def _bands(data: np.ndarray, sr: int) -> tuple[np.ndarray, np.ndarray]:
    mono = data.mean(axis=1) if data.ndim == 2 else data
    if sr != AN_SR:
        g = gcd(int(sr), AN_SR)
        mono = resample_poly(mono, AN_SR // g, int(sr) // g)
    f, t, z = stft(mono, fs=AN_SR, nperseg=AN_N, noverlap=AN_N - AN_HOP, window="hann")
    mag = np.abs(z)
    b = _band_index(f)
    valid = b >= 0
    counts = np.bincount(b[valid], minlength=N_BANDS).astype(float)
    power = np.zeros((N_BANDS, mag.shape[1]))
    np.add.at(power, b[valid], mag[valid] ** 2)
    power /= np.maximum(counts, 1)[:, None]
    # Floor at -45 dB below the loudest band so near-silence (which codecs zero out) can't dominate.
    floor = power.max() * 10 ** (-4.5) + 1e-12
    band = 0.5 * np.log(power + floor)
    band -= band.mean(axis=1, keepdims=True)  # static spectrum per band
    band -= band.mean(axis=0, keepdims=True)  # loudness changes common to all bands
    return t, band


def reference(data: np.ndarray, sr: int) -> np.ndarray:
    """Compact reference of the ORIGINAL audio for informed detection (bands x 20 Hz)."""
    return _bands(data, sr)[1].astype(np.float16)


def _on_grid(data, sr):
    return _bands(data, sr)[1]


def _best_lag(sus: np.ndarray, ref: np.ndarray) -> int:
    """Lag L (in grid samples) so that sus[:, t] lines up with ref[:, t + L]."""
    n = 1
    while n < sus.shape[1] + ref.shape[1]:
        n <<= 1
    fs = np.fft.rfft(sus, n, axis=1)
    fr = np.fft.rfft(ref, n, axis=1)
    corr = np.fft.irfft((np.conj(fs) * fr).sum(axis=0), n)
    lags = np.concatenate([np.arange(0, ref.shape[1]), np.arange(-sus.shape[1] + 1, 0)])
    vals = np.concatenate([corr[: ref.shape[1]], corr[n - sus.shape[1] + 1 :]])
    return int(lags[int(np.argmax(vals))])


def _decoy_chips(times: np.ndarray) -> np.ndarray:
    out = np.empty((wm_core.N_DECOYS, len(times)))
    for k in range(wm_core.N_DECOYS):
        c = wm_core.temporal_chip(f"{LABEL}:decoy{k}", times, SLOT_S, N_SLOTS)
        out[k] = c - c.mean()
    return out


def match_array(data: np.ndarray, sr: int, payload: int, ref: np.ndarray | None = None) -> dict:
    """Owner-side check. With the vault reference it is informed (strong);
    without it, a blind best-offset search (weak, short clips may miss)."""
    lay = wm_core.layout(LABEL, N_BANDS)
    s = wm_core.signs_for(payload, lay)
    if ref is None:
        t, band = _bands(data, sr)
        z, _ = wm_core.offset_zscore(t, s @ band, lay.decoys @ band, LABEL, SLOT_S, N_SLOTS, RATE)
        return {"z": round(float(z), 2), "detected": bool(z >= DETECT_Z), "mode": "blind"}
    ref = ref.astype(np.float64)
    sus = _on_grid(data, sr)
    lag = _best_lag(sus, ref)
    # overlap: suspect index i <-> reference index i + lag
    i0 = max(0, -lag)
    i1 = min(sus.shape[1], ref.shape[1] - lag)
    if i1 - i0 < RATE * 2:
        return {"z": 0.0, "detected": False, "mode": "informed", "note": "overlap under 2 s"}
    a = sus[:, i0:i1]
    b = ref[:, i0 + lag : i1 + lag]
    a = a - a.mean(axis=1, keepdims=True)
    b = b - b.mean(axis=1, keepdims=True)
    gain = float((a * b).sum() / ((b * b).sum() + 1e-9))
    resid = a - gain * b
    # Down-weight bands the codec disturbed most (estimated from the residual itself).
    resid = resid / (resid.std(axis=1, keepdims=True) + 1e-6)
    times = (np.arange(i0, i1) + lag) / RATE  # in the original's time base
    chip = wm_core.temporal_chip(LABEL, times, SLOT_S, N_SLOTS)
    chip = chip - chip.mean()
    sig = float((s @ resid) @ chip)
    # Decoys are random in both frequency and time, so a strong match is not
    # capped by the small number of bands.
    dchips = _decoy_chips(times)
    dec = np.einsum("dt,dt->d", lay.decoys @ resid, dchips)
    z = (sig - float(dec.mean())) / (float(dec.std()) or 1e-9)
    return {"z": round(float(z), 2), "detected": bool(z >= wm_core.DETECT_Z), "mode": "informed",
            "offset_s": round(lag / RATE, 2)}


def decode_array(data: np.ndarray, sr: int) -> int:
    """Blind read: aligns the time sequence by the strongest overall response, then reads each bit."""
    t, band = _bands(data, sr)
    best = (-1e18, 0.0)
    rate_t = t
    for off in np.arange(0, SLOT_S * N_SLOTS, 0.05):
        chip = wm_core.temporal_chip(LABEL, rate_t + off, SLOT_S, N_SLOTS)
        v = band @ chip
        e = float(np.abs(v).sum())
        if e > best[0]:
            best = (e, off)
    chip = wm_core.temporal_chip(LABEL, rate_t + best[1], SLOT_S, N_SLOTS)
    lay = wm_core.layout(LABEL, N_BANDS)
    payload, _ = wm_core.decode(band @ chip, lay)
    return payload
