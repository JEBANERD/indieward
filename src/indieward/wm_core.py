"""Spread-spectrum core shared by the built-in image, audio and video watermarks.

IW-Mark v1 spreads a 64-bit payload over a vector of host features (DCT
coefficients for images and video frames, log-spectrum bands for audio).
The layout (which feature carries which bit, and its +/-1 chip) is derived
from a PUBLIC format seed, so anyone can read the payload. Only the creator's
MAC key can tell whether a payload is genuine (see payload.py).

Two detectors:
- ``match``: owner-side. Correlates against the full pattern of a known
  payload. Uses every feature, so it is far more robust than blind decoding.
  The score is normalised against random decoy patterns (an empirical z-score),
  which keeps false positives low even when the host signal is not white.
- ``decode``: blind. Recovers each bit from its own subset of features. Works
  on lightly processed copies; use ``match`` for evidence.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

import numpy as np

FORMAT_SEED = b"IndieWard IW-Mark v1"
NBITS = 64
N_DECOYS = 256


def rng_for(label: str) -> np.random.Generator:
    digest = hashlib.sha256(FORMAT_SEED + b"|" + label.encode()).digest()
    return np.random.default_rng(int.from_bytes(digest[:8], "big"))


@dataclass
class Layout:
    n: int
    bit_of: np.ndarray  # (n,) which payload bit each feature carries
    chips: np.ndarray  # (n,) public +/-1 chip per feature
    decoys: np.ndarray  # (N_DECOYS, n) random +/-1 patterns for z-normalisation


_LAYOUTS: dict[tuple[str, int], Layout] = {}


def layout(label: str, n: int) -> Layout:
    key = (label, n)
    if key not in _LAYOUTS:
        rng = rng_for(f"{label}:{n}")
        perm = rng.permutation(n)
        bit_of = np.empty(n, dtype=np.int64)
        bit_of[perm] = np.arange(n) % NBITS
        chips = rng.choice(np.array([-1.0, 1.0]), size=n)
        decoys = rng_for(f"{label}:{n}:decoys").choice(np.array([-1.0, 1.0]), size=(N_DECOYS, n))
        _LAYOUTS[key] = Layout(n, bit_of, chips, decoys)
    return _LAYOUTS[key]


def bits_from_int(value: int) -> np.ndarray:
    return np.array([(value >> (NBITS - 1 - i)) & 1 for i in range(NBITS)], dtype=np.int64)


def int_from_bits(bits) -> int:
    out = 0
    for b in bits:
        out = (out << 1) | int(b)
    return out


def signs_for(payload: int, lay: Layout) -> np.ndarray:
    bits = bits_from_int(payload)
    return lay.chips * (2.0 * bits[lay.bit_of] - 1.0)


def zscore(features: np.ndarray, signs: np.ndarray, lay: Layout) -> float:
    """Empirical z-score of the payload pattern against random decoys."""
    f = features - features.mean()
    score = float(signs @ f)
    dec = lay.decoys @ f
    sd = float(dec.std()) or 1e-9
    return (score - float(dec.mean())) / sd


def decode(features: np.ndarray, lay: Layout) -> tuple[int, np.ndarray]:
    f = features - features.mean()
    per_bit = np.bincount(lay.bit_of, weights=lay.chips * f, minlength=NBITS)
    counts = np.bincount(lay.bit_of, minlength=NBITS).astype(float)
    norm = np.sqrt(np.bincount(lay.bit_of, weights=f * f, minlength=NBITS)) + 1e-9
    conf = per_bit / norm  # roughly N(0,1) per bit under no watermark
    bits = (per_bit > 0).astype(np.int64)
    _ = counts
    return int_from_bits(bits), conf


# A match counts as "detected" above this z. With the decoy normalisation the
# false-positive rate per test is roughly that of a normal tail at 6 sigma
# (about 1e-9), so even thousands of registered marks keep the chance of a
# false hit negligible.
DETECT_Z = 6.0


# --- temporal chips for audio and video --------------------------------------

def temporal_chip(label: str, times: np.ndarray, slot_s: float, n_slots: int) -> np.ndarray:
    """Smooth pseudo-random +/-1 sequence over time, periodic every slot_s*n_slots.

    The period is a prime number of slots so it doesn't line up with musical
    tempos or game loops, which would otherwise leak into the detector.
    """
    seq = rng_for(f"{label}:temporal:{n_slots}").choice(np.array([-1.0, 1.0]), size=n_slots)
    pos = (times / slot_s) % n_slots
    i0 = np.floor(pos).astype(np.int64) % n_slots
    frac = pos - np.floor(pos)
    nxt = seq[(i0 + 1) % n_slots]
    cur = seq[i0]
    # raised-cosine ramp in the last 20% of each slot
    ramp = np.clip((frac - 0.8) / 0.2, 0, 1)
    w = 0.5 - 0.5 * np.cos(np.pi * ramp)
    return cur * (1 - w) + nxt * w


def offset_zscore(times: np.ndarray, series_sig: np.ndarray, series_dec: np.ndarray, label: str,
                  slot_s: float, n_slots: int, rate: float) -> tuple[float, float]:
    """Best-offset correlation of projected time series with the periodic chip.

    ``series_sig`` (T,) is the payload pattern's projection at each frame time;
    ``series_dec`` (D, T) the decoys'. The series are resampled to ``rate`` Hz,
    folded onto one chip period, and circularly correlated with the chip, so a
    clip trimmed at any point is still aligned. The payload's best score is
    compared with the decoys' best scores, which accounts for the offset search.
    Returns (z, best offset in seconds).
    """
    period_n = int(round(slot_s * n_slots * rate))
    grid = np.arange(times[0], times[-1], 1.0 / rate)
    if len(grid) < period_n // 4:
        return 0.0, 0.0
    sig = np.interp(grid, times, series_sig)
    dec = np.stack([np.interp(grid, times, d) for d in series_dec])
    idx = np.arange(len(grid)) % period_n
    chip = temporal_chip(label, np.arange(period_n) / rate, slot_s, n_slots)
    fc = np.conj(np.fft.rfft(chip))

    def fold(x):
        x = x - x.mean(axis=-1, keepdims=True)
        out = np.zeros(x.shape[:-1] + (period_n,))
        if x.ndim == 1:
            np.add.at(out, idx, x)
        else:
            for k in range(x.shape[0]):
                out[k] = np.bincount(idx, weights=x[k], minlength=period_n)
        return out

    def corr(x):
        return np.fft.irfft(np.fft.rfft(fold(x), axis=-1) * fc, period_n, axis=-1)

    cs = corr(sig)
    k = int(np.argmax(cs))
    best_sig = float(cs[k])
    best_dec = corr(dec).max(axis=-1)
    z = (best_sig - float(best_dec.mean())) / (float(best_dec.std()) or 1e-9)
    # chip index k aligns with grid index 0, i.e. the clip starts k samples into a period
    return z, ((-k) % period_n) / rate
