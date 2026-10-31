"""P2-17: MCP tools for watch and traps inject: plan (no side effects), then apply/run with the plan's confirm code."""
from __future__ import annotations

import asyncio
import json

import pytest

from indieward import mcp_server as ms
from indieward import notice, traps, verify, watch
from indieward.vault import Vault

URL = "https://enginetest.itch.io/trap-check"


@pytest.fixture
def game(tmp_path, monkeypatch):
    proj = tmp_path / "game"
    v = Vault.init(proj, "Lantern Moth", "Test Studio", "dev@teststudio.example")
    code = v.project()["verify_code"]
    page = f'<div class="formatted_description">{code}</div><div class="game_comments_widget"></div>'
    monkeypatch.setattr(verify, "http_get", lambda url, timeout=20.0: (200, page.encode()))
    verify.verify_page(v, "itch", URL)
    b = traps.generate(v, "v1", "godot")["build_id"]
    notice.generate(v)
    return v, proj, b


@pytest.fixture
def no_network(monkeypatch):
    calls = []

    def fake(url, headers=None, timeout=20.0):
        calls.append((url, headers or {}))
        if url.startswith("https://archive.softwareheritage.org/"):
            return 404, {"x-ratelimit-remaining": "100"}, {"exception": "NotFoundExc"}
        if url.startswith("https://api.github.com/"):
            return 200, {}, {"total_count": 0, "items": []}
        return 200, {}, {"objects": []}

    monkeypatch.setattr(watch, "http_get_json", fake)
    return calls


def _strings(v, tier=None):
    return [t["value"] for t in traps.records(v) if t["kind"] == "string" and (tier is None or t["tier"] == tier)]


# --- inject ---------------------------------------------------------------------------

def test_inject_plan_writes_nothing_and_apply_needs_its_code(game):
    v, proj, b = game
    f = proj / "fr.csv"
    f.write_bytes(b"keys,en,fr\nMENU_START,Start,Commencer\n")
    before = f.read_bytes()
    plan = ms.trap_inject_plan(str(proj), b, str(f))
    assert "error" not in plan and plan["diff"] and plan["confirm_code"] and f.read_bytes() == before
    assert "error" in ms.trap_inject_apply(str(proj), b, str(f), "wrong")
    assert f.read_bytes() == before
    r = ms.trap_inject_apply(str(proj), b, str(f), plan["confirm_code"])
    assert r["applied"] and all(k in f.read_text() for k in plan["keys"])


def test_inject_code_goes_stale_when_the_file_changes(game):
    v, proj, b = game
    f = proj / "fr.csv"
    f.write_bytes(b"keys,en,fr\nMENU_START,Start,Commencer\n")
    plan = ms.trap_inject_plan(str(proj), b, str(f))
    f.write_bytes(b"keys,en,fr\nMENU_START,Start,Commencer\nMENU_QUIT,Quit,Quitter\n")  # edited after the plan
    assert "error" in ms.trap_inject_apply(str(proj), b, str(f), plan["confirm_code"])
    assert b"trap" not in f.read_bytes() and not any(s.encode() in f.read_bytes() for s in _strings(v))


# --- watch ----------------------------------------------------------------------------

def test_watch_plan_sends_nothing_and_shows_what_would_go(game, no_network):
    v, proj, _ = game
    plan = ms.watch_plan(str(proj), ["swh", "github", "npm"])
    assert no_network == [] and plan["confirm_code"] and plan["disclosure"]
    assert all(x["sends"].endswith("hash only") for x in plan["will_send"]["swh"])
    sent = {x["sends"] for x in plan["will_send"]["github"]}
    assert set(_strings(v, "build")) <= sent and not (set(_strings(v, "core")) & sent)  # core only on request
    assert ms.watch_plan(str(proj), ["swh"])["disclosure"] is None


def test_watch_run_needs_the_matching_code(game, no_network):
    v, proj, _ = game
    swh_plan = ms.watch_plan(str(proj), ["swh"])
    # a code for a hash-only plan can't authorise text searches
    assert "error" in ms.watch_run(str(proj), ["swh", "github"], swh_plan["confirm_code"])
    assert "error" in ms.watch_run(str(proj), ["swh"], "wrong")
    assert no_network == []
    r = ms.watch_run(str(proj), ["swh"], swh_plan["confirm_code"])
    assert r["sources"]["swh"]["queries"] == len(swh_plan["will_send"]["swh"])
    assert all(u.startswith("https://archive.softwareheritage.org/") for u, _ in no_network)
    assert isinstance(ms.watch_leads(str(proj)), list)


def test_watch_run_reads_the_token_from_the_environment_only(game, no_network, monkeypatch):
    v, proj, _ = game
    schema = next(t for t in asyncio.run(ms.mcp.list_tools()) if t.name == "watch_run")
    params = json.dumps(getattr(schema, "inputSchema", None) or getattr(schema, "input_schema"))
    assert "token" not in params.lower()
    plan = ms.watch_plan(str(proj), ["github"])
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    assert "GITHUB_TOKEN" in ms.watch_run(str(proj), ["github"], plan["confirm_code"])["error"]
    monkeypatch.setenv("GITHUB_TOKEN", "env-tok")
    ms.watch_run(str(proj), ["github"], plan["confirm_code"])
    assert no_network and all(h.get("Authorization") == "Bearer env-tok" for _, h in no_network)


def test_tool_names_stay_clear_of_send_words():
    names = {t.name for t in asyncio.run(ms.mcp.list_tools())}
    assert {"trap_inject_plan", "trap_inject_apply", "watch_plan", "watch_run", "watch_leads"} <= names
    assert not any(w in n for n in names for w in ("send", "submit", "email"))
