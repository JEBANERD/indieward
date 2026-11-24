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


def _use_index(monkeypatch, **libs) -> None:
    """Replace the shipped index with these libraries (name -> list of build files' source texts)."""
    entries = [{"name": name, "version": "1.0.0", "fingerprints": frozenset(_fps(*texts)["fingerprints"]),
                "files": [frozenset(_fps(t)["fingerprints"]) for t in texts]}
               for name, texts in libs.items()]
    common_index._add_unique(entries)
    monkeypatch.setattr(common_index, "load", lambda: {"libraries": entries, "lines": frozenset()})


def _old_rule_trips(suspect_fps, lib_fps) -> bool:
    """P2-18's rule: share of *all* the library's fingerprints."""
    n = len(set(suspect_fps) & lib_fps)
    return n >= common_index.MIN_SHARED and n >= common_index.MIN_SHARE * len(lib_fps)


def test_shipped_index_has_fingerprints_and_licences_only():
    assert common_index.DATA.stat().st_size < 4 * 1024 * 1024  # size budget (P2-18)
    raw = json.loads(common_index.DATA.read_text(encoding="utf-8"))
    assert raw["format"] == 2
    assert {lib["name"] for lib in raw["libraries"]} == LIBS
    for lib in raw["libraries"]:
        assert set(lib) == {"name", "version", "license", "tarball", "integrity", "files", "count", "fingerprints"}
        assert all(set(f) == {"name", "count", "indices"} for f in lib["files"])
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
    _use_index(monkeypatch, fakelib=[lib_text])
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


def test_generic_code_shared_between_libraries_does_not_trip_the_other(monkeypatch):
    # Like three.js and excalibur: both contain the same generic maths/WebGL-style code.
    generic, a_own, b_own = _fake_js(10, 150), _fake_js(11), _fake_js(12)
    _use_index(monkeypatch, liba=[generic, a_own], libb=[generic, b_own])
    lib_b = common_index.load()["libraries"][1]["fingerprints"]
    vault_build = _fps(generic, a_own, _fake_js(2, 60))  # creator's game bundles liba
    suspect = _fps(generic, a_own, _fake_js(3, 60))  # an unrelated game bundling liba
    assert _old_rule_trips(suspect["fingerprints"], lib_b)  # the old rule named libb too
    names, exclude = common_index.detect(suspect["fingerprints"])
    assert names == ["liba@1.0.0"]
    assert fp_code.compare(vault_build, suspect, exclude)["score"] == 0  # the shared code is still excluded
    copy = _fps(generic, a_own, _fake_js(2, 60))
    assert fp_code.compare(vault_build, copy, common_index.detect(copy["fingerprints"])[1])["score"] >= 60


def test_real_bundles_still_detect(monkeypatch):
    # Like Phaser shipping Matter's physics: "inner" is entirely inside "outer", so it has no unique fingerprints.
    inner, outer_own, other_own = _fake_js(20), _fake_js(21), _fake_js(22)
    _use_index(monkeypatch, inner=[inner], outer=[inner, outer_own], other=[other_own])
    by_name = {lib["name"]: lib for lib in common_index.load()["libraries"]}
    assert by_name["inner"]["detect"] == by_name["inner"]["fingerprints"]  # falls back to all its fingerprints
    assert len(by_name["outer"]["detect"]) < len(by_name["outer"]["fingerprints"])
    # a game shipping both outer and other: both detected
    both = _fps(inner, outer_own, other_own, _fake_js(3, 60))["fingerprints"]
    assert set(common_index.detect(both)[0]) >= {"outer@1.0.0", "other@1.0.0"}
    # two unrelated games that each ship inner on its own: no code score
    vault_build, suspect = _fps(inner, _fake_js(2, 60)), _fps(inner, _fake_js(3, 60))
    names, exclude = common_index.detect(suspect["fingerprints"])
    assert "inner@1.0.0" in names and "other@1.0.0" not in names
    assert fp_code.compare(vault_build, suspect, exclude)["score"] == 0


def test_library_detected_from_a_small_build_that_the_old_rule_missed(monkeypatch):
    # Like Vue: a big development build and a small production build with little in common.
    big, small = _fake_js(30, 5000), _fake_js(31, 300)
    _use_index(monkeypatch, vue=[big, small], other=[_fake_js(32)])
    lib = common_index.load()["libraries"][0]
    assert len(lib["detect_files"]) == 2
    suspect = _fps(small, _fake_js(3, 60))  # a game shipping only the small build
    assert not _old_rule_trips(suspect["fingerprints"], lib["detect"])
    names, exclude = common_index.detect(suspect["fingerprints"])
    assert names == ["vue@1.0.0"] and exclude == lib["fingerprints"]  # all of the library is excluded
    vault_build = _fps(small, _fake_js(2, 60))
    assert fp_code.compare(vault_build, suspect, exclude)["score"] == 0
    copy = _fps(small, _fake_js(2, 60))
    assert fp_code.compare(vault_build, copy, common_index.detect(copy["fingerprints"])[1])["score"] >= 60
    # a thin entry file (under MIN_SHARED fingerprints) can't detect the library on its own
    thin = _fps(_fake_js(33, 10))["fingerprints"]
    assert len(thin) < common_index.MIN_SHARED and common_index.detect(thin) == ([], set())


def test_each_shipped_file_detects_only_its_library():
    thin = 0
    for lib in common_index.load()["libraries"]:
        for fps in lib["files"]:
            names = common_index.detect(fps)[0]
            assert names in ([], [f"{lib['name']}@{lib['version']}"]), lib["name"]
            if not names:
                thin += 1
                assert len(fps & lib["detect"]) < common_index.MIN_SHARED  # only thin entry files are missed
    assert thin <= 2  # three.cjs and react-dom.production.js


def test_each_shipped_library_detects_only_itself():
    libs = common_index.load()["libraries"]
    for lib in libs:
        assert common_index.detect(lib["fingerprints"])[0] == [f"{lib['name']}@{lib['version']}"], lib["name"]


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
