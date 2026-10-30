"""Vectorized image matching (P2-07): same numbers as fp_image.similarity, fast enough for big builds."""
from __future__ import annotations

import time

import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageOps

import gamefixture as gf
from indieward import check, fp_image


def _fixture_fps():
    arts = [gf._art(s) for s in range(6)]
    edits = [gf._recolor(arts[0]), ImageOps.mirror(arts[1]), arts[2].resize((180, 180)),
             arts[3].rotate(3), gf._art(99, palette=None)]
    plain = [Image.new("RGB", (64, 64), (255, 0, 0)), Image.new("RGB", (128, 128), (10, 200, 30))]
    scene = Image.new("RGB", (256, 256), (180, 200, 220))
    ImageDraw.Draw(scene).rectangle((0, 160, 256, 256), fill=(40, 60, 20))
    reg = [fp_image.fingerprint_image(im) for im in arts + plain[:1]]
    sus = [fp_image.fingerprint_image(im) for im in edits + arts[4:] + plain[1:] + [scene]]
    return reg, sus


def test_similarity_matrix_matches_pairwise():
    reg, sus = _fixture_fps()
    m = fp_image.similarity_matrix(reg, sus)
    assert m.shape == (len(reg), len(sus))
    for i, fa in enumerate(reg):
        for j, fb in enumerate(sus):
            assert abs(m[i, j] - fp_image.similarity(fa, fb)) <= 1e-6
    assert m.max() > 0.5  # the fixture includes real copies, so this is not all zeros


def test_similarity_matrix_empty_inputs():
    reg, _ = _fixture_fps()
    assert fp_image.similarity_matrix([], reg).shape == (0, len(reg))
    assert fp_image.similarity_matrix(reg, []).shape == (len(reg), 0)


def test_image_category_matches_old_double_loop():
    reg, sus = _fixture_fps()
    rows = [{"name": f"r{i}"} for i in range(len(reg))]
    imgs = [(f"s{j}", None) for j in range(len(sus))]
    score, pairs, extra = check._image_category(rows, reg, imgs, sus)
    old = np.array([[fp_image.similarity(fa, fb) for fb in sus] for fa in reg])
    assert np.abs(extra["sim"] - old).max() <= 1e-6
    assert pairs and all(p["similarity"] >= 0.5 for p in pairs)


def _random_fps(n, rng, min_detail=0.0):
    hx = lambda: f"{int(rng.integers(0, 2**63)) * 2 + int(rng.integers(0, 2)):016x}"
    out = []
    for _ in range(n):
        t = rng.standard_normal(fp_image.THUMB ** 2)
        t /= np.linalg.norm(t)
        fp = {k: hx() for k in ("ph", "dh", "eh", "m_ph", "m_dh", "m_eh")}
        fp.update(thumb=[round(float(x), 4) for x in t], detail=float(rng.uniform(min_detail, 0.5)))
        out.append(fp)
    return out


def test_random_fingerprints_match_pairwise():
    rng = np.random.default_rng(7)
    a, b = _random_fps(40, rng), _random_fps(30, rng)
    b[:5] = [dict(x) for x in a[:5]]  # identical pairs
    m = fp_image.similarity_matrix(a, b)
    old = np.array([[fp_image.similarity(fa, fb) for fb in b] for fa in a])
    assert np.abs(m - old).max() <= 1e-6


@pytest.mark.slow
def test_benchmark_2000_by_2000_under_10s():
    rng = np.random.default_rng(1)
    # every image detailed enough to compare: the worst case
    a, b = _random_fps(2000, rng, 0.1), _random_fps(2000, rng, 0.1)
    t0 = time.perf_counter()
    m = fp_image.similarity_matrix(a, b)
    took = time.perf_counter() - t0
    assert m.shape == (2000, 2000)
    assert took < 10.0, f"2,000 x 2,000 took {took:.1f} s"
