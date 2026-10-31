"""P2-08: the built-in common-material index (bundled libraries, licence texts)."""
from __future__ import annotations

import json
import os
import random
from pathlib import Path

import pytest

from indieward import common_index, fp_code, fp_text

LIBS = {"three", "phaser", "pixi.js", "howler", "matter-js", "lodash",
        "babylonjs", "react", "react-dom", "vue", "jquery", "kaboom", "excalibur"}


def _fake_js(seed: int, n: int = 400) -> str:
    """Varied JS-like code whose normalized token stream doesn't repeat, so it yields many fingerprints."""
    rng = random.Random(seed)
    ops = ["+", "-", "*", "/", "%", "<", ">", "==", "!=", "&&", "||", "&", "|", "^"]
    kws = ["if", "while", "return", "new", "typeof", "this", "null", "true", "false", "const", "let"]
    out = []
    for i in range(n):
        a = [rng.choice(["x", "1", "'s'", rng.choice(kws)]) + rng.choice(ops) for _ in range(rng.randint(2, 6))]
        out.append(f"function f{i}(a){{ {rng.choice(kws)} ({''.join(a)}y) {{ return [a, {i}, '{i}']; }} }}")
    return "\n".join(out)


def _fps(*texts: str) -> dict:
    return fp_code.fingerprint_text_blobs({f"f{i}.js": t for i, t in enumerate(texts)})


def test_shipped_index_has_fingerprints_and_licences_only():
    assert common_index.DATA.stat().st_size < 4 * 1024 * 1024  # size budget (P2-18)
    raw = json.loads(common_index.DATA.read_text(encoding="utf-8"))
    assert {lib["name"] for lib in raw["libraries"]} == LIBS
    for lib in raw["libraries"]:
        assert set(lib) == {"name", "version", "license", "tarball", "integrity", "files", "count", "fingerprints"}
        assert lib["integrity"].startswith("sha512-") and lib["count"] > 1000
    assert {x["id"] for x in raw["licences"]} == {"MIT", "Apache-2.0", "BSD-3-Clause", "CC-BY-4.0", "OFL-1.1"}
    # fingerprints only: no library source text anywhere in the file
    libs_text = json.dumps(raw["libraries"])
    assert "function" not in libs_text and "prototype" not in libs_text
    loaded = common_index.load()
    assert all(len(lib["fingerprints"]) == next(x["count"] for x in raw["libraries"] if x["name"] == lib["name"])
               for lib in loaded["libraries"])
    # licence texts are split into lines the same way registered text files are
    assert any(x.startswith("permission is hereby granted free of charge") for x in common_index.licence_lines())


def test_bundled_library_is_excluded_only_when_present(monkeypatch):
    lib_text = _fake_js(1)
    lib = _fps(lib_text)["fingerprints"]
    monkeypatch.setattr(common_index, "load", lambda: {"libraries": [
        {"name": "fakelib", "version": "1.0.0", "fingerprints": frozenset(lib)}], "lines": frozenset()})
    vault_build = _fps(lib_text, _fake_js(2, 60))  # creator's game bundles the library
    suspect = _fps(lib_text, _fake_js(3, 60))  # an unrelated game bundling the same library
    assert fp_code.compare(vault_build, suspect)["score"] >= 60  # without the index it looks like copying
    names, exclude = common_index.detect(suspect["fingerprints"])
    assert names == ["fakelib@1.0.0"]
    r = fp_code.compare(vault_build, suspect, exclude)
    assert r["score"] == 0 and r["excluded_common"] > 0
    # a real copy that also bundles the library still scores high
    copy = _fps(lib_text, _fake_js(2, 60))
    assert fp_code.compare(vault_build, copy, common_index.detect(copy["fingerprints"])[1])["score"] >= 60
    # code that doesn't bundle it isn't touched
    assert common_index.detect(_fps(_fake_js(4, 60))["fingerprints"]) == ([], set())


def _two_libs_sharing_generic_code(monkeypatch):
    """Libraries A and B that share a big block of generic code, as big JS libraries do."""
    shared, a_own, b_own = _fake_js(10, 300), _fake_js(11, 300), _fake_js(12, 300)
    libs = [{"name": "liba", "version": "1.0.0", "fingerprints": frozenset(_fps(a_own, shared)["fingerprints"])},
            {"name": "libb", "version": "2.0.0", "fingerprints": frozenset(_fps(b_own, shared)["fingerprints"])}]
    common_index._add_unique(libs)
    monkeypatch.setattr(common_index, "load", lambda: {"libraries": libs, "lines": frozenset()})
    return libs, shared, a_own, b_own


def test_generic_overlap_no_longer_counts_as_bundling_another_library(monkeypatch):
    (liba, libb), shared, a_own, _ = _two_libs_sharing_generic_code(monkeypatch)
    bundle_a = set(_fps(a_own, shared)["fingerprints"])
    # under the old rule (all of B's fingerprints) A's bundle passes for B too
    n_old = len(bundle_a & libb["fingerprints"])
    assert n_old >= common_index.MIN_SHARED and n_old >= common_index.MIN_SHARE * len(libb["fingerprints"])
    # on B's unique fingerprints it doesn't
    names, exclude = common_index.detect(bundle_a)
    assert names == ["liba@1.0.0"]
    assert exclude == set(liba["fingerprints"])  # a detected library still drops all its fingerprints


def test_real_bundles_still_detect_with_shared_code(monkeypatch):
    (liba, libb), shared, a_own, b_own = _two_libs_sharing_generic_code(monkeypatch)
    assert common_index.detect(_fps(b_own, shared)["fingerprints"])[0] == ["libb@2.0.0"]
    both = common_index.detect(_fps(a_own, b_own, shared)["fingerprints"])
    assert both[0] == ["liba@1.0.0", "libb@2.0.0"] and both[1] == set(liba["fingerprints"]) | set(libb["fingerprints"])
    # an unrelated game bundling B scores 0 against a creator's build bundling B; a real copy still scores high
    vault_build = _fps(b_own, shared, _fake_js(20, 60))
    unrelated = _fps(b_own, shared, _fake_js(21, 60))
    assert fp_code.compare(vault_build, unrelated, common_index.detect(unrelated["fingerprints"])[1])["score"] == 0
    copy = _fps(b_own, shared, _fake_js(20, 60))
    assert fp_code.compare(vault_build, copy, common_index.detect(copy["fingerprints"])[1])["score"] >= 60


def test_shipped_libraries_each_keep_a_large_unique_set():
    for lib in common_index.load()["libraries"]:
        assert len(lib["unique"]) >= 0.4 * len(lib["fingerprints"]), lib["name"]


@pytest.mark.skipif(not os.environ.get("INDIEWARD_THREE_JS"), reason="set INDIEWARD_THREE_JS to a three.module.js")
def test_suspect_bundling_three_scores_zero_against_vault_bundling_it():
    three = Path(os.environ["INDIEWARD_THREE_JS"]).read_text("utf-8", errors="replace")
    src = Path(__file__).resolve().parents[1] / "src" / "indieward"
    vault_build = _fps(three, (src / "hooks.py").read_text("utf-8"))  # two unrelated games, both bundling three.js
    suspect = _fps(three, (src / "stores.py").read_text("utf-8"))
    assert fp_code.compare(vault_build, suspect)["score"] >= 60
    names, exclude = common_index.detect(suspect["fingerprints"])
    assert any(n.startswith("three@") for n in names)
    assert fp_code.compare(vault_build, suspect, exclude)["score"] == 0


def test_tokens_with_lines_counts_lines_like_before():
    text = "a = 1\n\n/* x\ny */ b = 'q'\n-- c\nreturn d"
    assert fp_code.tokens_with_lines(text) == [("V", 1), ("=", 1), ("N", 1), ("V", 4), ("=", 4), ("S", 4),
                                               ("return", 6), ("V", 6)]
