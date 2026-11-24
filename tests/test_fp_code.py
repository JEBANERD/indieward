"""Code tokenizer: comment rules follow the file's language, and strings are never mistaken for comments."""
from __future__ import annotations

import time

from indieward import fp_code
from indieward.fp_code import fingerprint_text_blobs, tokens_with_lines

PRETTY = '''// Player movement (c) Moth Studio
function step(player, input) {
  /* decay speed every frame */
  for (var i = player.trail.length; i--;) {
    player.trail[i].alpha -= 0.05;   // fade out
  }
  player.tint = input.hurt ? "#ff3355" : "#ffffff";
  player.url = "https://example.com/a//b";
  return player.speed * input.axis + player.boost;
}
function reset(player) { player.speed = 0; player.boost = 1; player.trail = []; return player; }
'''
MINIFIED = ('function step(player,input){for(var i=player.trail.length;i--;){player.trail[i].alpha-=0.05;}'
            'player.tint=input.hurt?"#ff3355":"#ffffff";player.url="https://example.com/a//b";'
            'return player.speed*input.axis+player.boost;}function reset(player){player.speed=0;player.boost=1;'
            'player.trail=[];return player;}')


def _toks(text, name):
    return [t for t, _ in tokens_with_lines(text, name)]


def test_minified_js_keeps_every_token():
    # `i--` used to start a Lua comment and "#ff3355" a Python one, each eating the rest of the line.
    pretty, mini = _toks(PRETTY, "player.js"), _toks(MINIFIED, "player.min.js")
    assert len(mini) > 80 and mini == pretty  # only whitespace and comments differ


def test_minified_copy_matches_pretty_original():
    a = fingerprint_text_blobs({"player.js": PRETTY * 3})
    b = fingerprint_text_blobs({"bundle.min.js": MINIFIED * 3})
    shared = set(a["fingerprints"]) & set(b["fingerprints"])
    assert shared == set(a["fingerprints"]) and shared


def test_comment_markers_inside_strings_are_text():
    assert _toks('u = "http://x.y/z"; v = 1', "a.js") == ["V", "=", "S", ";", "V", "=", "N"]
    assert _toks('c = "#fff"  # colour\nd = 2', "a.py") == ["V", "=", "S", "V", "=", "N"]
    assert _toks('s = "--not a comment" -- real one\nt = 3', "a.lua") == ["V", "=", "S", "V", "=", "N"]


def test_each_language_keeps_its_own_comments():
    assert _toks("a = 1 -- note\nb = 2", "m.lua") == ["V", "=", "N", "V", "=", "N"]
    assert _toks("a = 1\n--[==[ long\ncomment ]==]\nb = 2", "m.luau") == ["V", "=", "N", "V", "=", "N"]
    assert _toks("var a = 1 # note\nvar b = 2", "p.gd") == ["var", "V", "=", "N", "var", "V", "=", "N"]
    # C-family: `--` and `#` are code, `#include` survives anyway
    assert _toks("i--; x = y--;", "a.cs") == ["V", "-", "-", ";", "V", "=", "V", "-", "-", ";"]


def test_unknown_extension_keeps_all_rules():
    # Decompiled or extracted text with no telling extension: every comment style is dropped, as before.
    assert _toks("a = 1 -- lua\nb = 2 // c\nc = 3 # py\n", "dump.txt") == ["V", "=", "N"] * 3


def test_line_numbers_survive_block_comments():
    toks = tokens_with_lines("a = 1\n/* x\ny\nz */\nb = 2\n", "a.js")
    assert [ln for t, ln in toks if t == "V"] == [1, 5]


def test_one_line_bundle_is_linear_time():
    big = MINIFIED * 2500  # ~1 MB on a single line
    t0 = time.perf_counter()
    toks = tokens_with_lines(big, "bundle.min.js")
    assert len(toks) > 200_000
    assert time.perf_counter() - t0 < 10


def test_family_lookup():
    assert fp_code.comment_family("Game.Min.JS") == "c"
    assert fp_code.comment_family("init.client.luau") == "lua"
    assert fp_code.comment_family("player.gd") == "hash"
    assert fp_code.comment_family("dump") is None


# --- golden outputs and fingerprint versions (P2-24) -------------------------------------------

import json  # noqa: E402

import pytest  # noqa: E402

from golden_fp_code import GOLDEN  # noqa: E402
from golden_samples import SAMPLES  # noqa: E402


@pytest.mark.parametrize("key", sorted(SAMPLES))
def test_golden_tokens_and_fingerprints(key):
    name, text = SAMPLES[key]
    tokens, hashes = GOLDEN[key]
    assert " ".join(_toks(text, name)) == tokens
    assert sorted(fingerprint_text_blobs({name: text})["fingerprints"]) == hashes
    assert fp_code.FP_CODE_VERSION == 2  # a tokenizer change must bump this and regenerate the golden file


def test_fingerprints_carry_the_version(tmp_path):
    (tmp_path / "a.lua").write_text(SAMPLES["lua"][1])
    assert fp_code.fingerprint_files([tmp_path / "a.lua"])["version"] == fp_code.FP_CODE_VERSION
    assert fingerprint_text_blobs({"a.lua": SAMPLES["lua"][1]})["version"] == fp_code.FP_CODE_VERSION
