"""Binary Roblox places: trap strings are found inside a real Rojo-built .rbxl (no Rojo needed).

Built with Rojo 7.7.1: `rojo build tests/fixtures/rojo_place --output tests/fixtures/rojo_place.rbxl`.
Its marker strings are made up for this test; they aren't trap values from any vault.
"""
from __future__ import annotations

from pathlib import Path

from indieward import traps

FIX = Path(__file__).resolve().parent / "fixtures"
RBXL = FIX / "rojo_place.rbxl"
MARKERS = {"loc_key": "kabodifu_zetamolu_rinasevo", "meta_value": "tuvemaso pirakedu lonafiza",
           "function_return": "sefumora_dikavelu", "build_tag": "nibozate_kurafeso_vamilido"}


def _rows():
    rows = [{"id": i, "build_id": "bfixture", "tier": "build" if lab == "build_tag" else "core", "kind": "string",
             "label": lab, "value": val} for i, (lab, val) in enumerate(MARKERS.items(), 1)]
    rows.append({"id": 9, "build_id": "bfixture", "tier": "core", "kind": "float", "label": "constant",
                 "value": "0.7316209843117291"})
    return rows


def test_fixture_is_a_small_binary_place():
    data = RBXL.read_bytes()
    assert data[:8] == b"<roblox!" and data[8:9] == b"\x89"
    assert len(data) < 50_000


def test_all_markers_found_in_rojo_rbxl():
    res = traps.scan(RBXL, _rows())
    found = {f["label"] for f in res["found"]}
    assert found == {*MARKERS, "constant"}, res
    assert all(any(h["file"].endswith("!/decompressed") for h in f["found_in"]) for f in res["found"])


def test_compressed_chunks_need_decoding():
    """The repeated marker is back-referenced by the compressor, so the raw file alone doesn't show all copies."""
    raw = RBXL.read_bytes()
    plain = traps._rbxl_chunks(raw)
    m = MARKERS["loc_key"].encode()
    assert plain.count(m) > raw.count(m)
    assert b"FixtureTable" in plain and b"FixtureServer" in plain
