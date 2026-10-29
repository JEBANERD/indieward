"""Story and dialogue fingerprints: line-level near-duplicate matching.

Each line (a dialogue line, a description sentence, an item text) becomes a
hashed character 4-gram vector plus its word set. A suspect line matches when
its combined similarity is high, which catches copied text and light
rewording (synonyms, reordered clauses). A full LLM paraphrase can slip under
it. Sentence-embedding models are an optional backend for that case.

Very short lines (under 4 words) are ignored: "Hello!" and "Game over" are
common to everything.
"""
from __future__ import annotations

import json
import re
import zlib
from pathlib import Path

import numpy as np

DIM = 4096
MIN_WORDS = 4
MATCH_AT = 0.55

_WORD = re.compile(r"[a-z0-9']+")


def normalize(s: str) -> str:
    return " ".join(_WORD.findall(s.lower()))


def split_lines(text: str) -> list[str]:
    out = []
    for raw in re.split(r"[\r\n]+", text):
        for part in re.split(r"(?<=[.!?])\s+(?=[A-Z\"'])", raw.strip()):
            if len(normalize(part).split()) >= MIN_WORDS:
                out.append(part.strip())
    return out


def lines_from_file(path) -> list[str]:
    p = Path(path)
    text = p.read_text("utf-8", errors="replace")
    if p.suffix.lower() == ".json":
        try:
            vals = []

            def walk(o):
                if isinstance(o, str):
                    vals.append(o)
                elif isinstance(o, dict):
                    for v in o.values():
                        walk(v)
                elif isinstance(o, list):
                    for v in o:
                        walk(v)

            walk(json.loads(text))
            text = "\n".join(vals)
        except json.JSONDecodeError:
            pass
    elif p.suffix.lower() == ".csv":
        text = "\n".join(c for row in text.splitlines() for c in row.split(","))
    return split_lines(text)


def _vec(line: str) -> np.ndarray:
    s = f" {normalize(line)} "
    v = np.zeros(DIM, dtype=np.float32)
    for i in range(len(s) - 3):
        v[zlib.crc32(s[i : i + 4].encode()) % DIM] += 1.0
    n = np.linalg.norm(v)
    return v / n if n else v


def _matrix(lines: list[str]) -> np.ndarray:
    return np.stack([_vec(x) for x in lines]) if lines else np.zeros((0, DIM), dtype=np.float32)


def compare(orig_lines: list[str], suspect_lines: list[str]) -> dict:
    if not orig_lines or not suspect_lines:
        return {"score": 0, "matched": 0, "of": len(orig_lines), "pairs": []}
    a, b = _matrix(orig_lines), _matrix(suspect_lines)
    sims = a @ b.T
    words_o = [set(normalize(x).split()) for x in orig_lines]
    words_s = [set(normalize(x).split()) for x in suspect_lines]
    pairs = []
    total = 0.0
    for i in range(len(orig_lines)):
        j = int(np.argmax(sims[i]))
        jac = len(words_o[i] & words_s[j]) / max(1, len(words_o[i] | words_s[j]))
        sim = 0.6 * float(sims[i, j]) + 0.4 * jac
        if sim >= MATCH_AT:
            conf = min(1.0, (sim - MATCH_AT) / 0.25 + 0.5)
            total += conf
            pairs.append({"original": orig_lines[i], "suspect": suspect_lines[j], "similarity": round(sim, 3)})
    cov_o = total / len(orig_lines)
    cov_s = total / len(suspect_lines)
    conf_n = min(1.0, len(pairs) / 5.0)
    score = int(round(100 * min(1.0, max(cov_o, cov_s)) * conf_n))
    pairs.sort(key=lambda p: -p["similarity"])
    return {"score": score, "matched": len(pairs), "of": len(orig_lines), "pairs": pairs[:12]}


def name_similarity(a: str, b: str) -> float:
    from difflib import SequenceMatcher

    na, nb = normalize(a), normalize(b)
    if not na or not nb:
        return 0.0
    r = SequenceMatcher(None, na, nb).ratio()
    short, long_ = sorted((na, nb), key=len)
    if len(short) >= 4 and re.search(r"\b" + re.escape(short) + r"s?\b", long_):
        r = max(r, 0.9)  # "Lantern Moth" as whole words inside "Lantern Moths: Night Flight"
    ta, tb = set(na.split()), set(nb.split())
    j = len(ta & tb) / max(1, len(ta | tb))
    return max(r, j)
