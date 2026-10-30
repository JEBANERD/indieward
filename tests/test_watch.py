"""`indieward watch` (P4-01): canary searches with recorded API responses; nothing goes over the network."""
from __future__ import annotations

import json
import urllib.parse
from pathlib import Path

import pytest

from indieward import notice, traps, verify, watch
from indieward.vault import NotVerified, Vault

FIX = Path(__file__).parent / "fixtures" / "watch"
URL = "https://enginetest.itch.io/trap-check"


def _fx(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


@pytest.fixture
def vault(tmp_path, monkeypatch):
    v = Vault.init(tmp_path / "game", "Lantern Moth", "Test Studio", "dev@teststudio.example")
    code = v.project()["verify_code"]
    page = f'<div class="formatted_description">{code}</div><div class="game_comments_widget"></div>'
    monkeypatch.setattr(verify, "http_get", lambda url, timeout=20.0: (200, page.encode()))
    verify.verify_page(v, "itch", URL)
    traps.generate(v, "v1", "godot")
    notice.generate(v)
    return v


class FakeAPI:
    """Routes by host to recorded responses; records every request."""

    def __init__(self, github=(200, None), npm=(200, None), swh=(404, None), swh_headers=None):
        self.calls = []
        self.github, self.npm, self.swh = github, npm, swh
        self.swh_headers = swh_headers or {"x-ratelimit-remaining": "119"}

    def __call__(self, url, headers=None, timeout=20.0):
        self.calls.append((url, headers or {}))
        if url.startswith("https://api.github.com/search/code"):
            st, data = self.github
            return st, {}, data if data is not None else {"total_count": 0, "items": []}
        if url.startswith("https://registry.npmjs.org/-/v1/search"):
            st, data = self.npm
            return st, {}, data if data is not None else {"objects": []}
        if url.startswith("https://archive.softwareheritage.org/api/1/content/"):
            st, data = self.swh
            return st, self.swh_headers, data
        raise AssertionError(f"unexpected URL {url}")


def _core_values(v):
    return [t["value"] for t in traps.records(v) if t["tier"] == "core" and t["kind"] == "string"]


def test_needles_default_to_build_traps_and_notice(vault):
    labels = [n["label"] for n in watch.text_needles(vault)]
    assert any("build build_tag" in x for x in labels) and "copyright notice" in labels
    assert not any(" core " in f" {x} " for x in labels)
    with_core = watch.text_needles(vault, include_core=True)
    assert {n["value"] for n in with_core} >= set(_core_values(vault))
    hashes = watch.hash_needles(vault)
    assert any(h["algo"] == "sha1" and h["label"].startswith("trap file") for h in hashes)
    assert any(h["algo"] == "sha256" and "hidden asset" in h["label"] for h in hashes)
    assert all(not h["label"].startswith("trap file README_") for h in hashes)


def test_text_sources_need_disclosure_and_token(vault):
    with pytest.raises(ValueError, match="accept-disclosure"):
        watch.run(vault, ["npm"])
    with pytest.raises(ValueError, match="GITHUB_TOKEN"):
        watch.run(vault, ["github"], accept_disclosure=True)
    with pytest.raises(ValueError, match="choose sources"):
        watch.run(vault, ["google"])


def test_unverified_vault_cannot_watch(tmp_path):
    v = Vault.init(tmp_path / "g", "G", "C")
    with pytest.raises(NotVerified):
        watch.run(v, ["swh"])


def test_github_exact_phrase_authenticated_and_paced(vault, monkeypatch):
    fake = FakeAPI(github=(200, _fx("github_search_code.json")))
    monkeypatch.setattr(watch, "http_get_json", fake)
    slept = []
    r = watch.run(vault, ["github"], token="tok123", accept_disclosure=True, sleep=slept.append)
    n = len(watch.text_needles(vault))
    assert r["sources"]["github"] == {"queries": n, "hits": n, "new_leads": n, "status": "ok"}
    assert slept == [watch.PACE["github"]] * (n - 1)
    for url, headers in fake.calls:
        q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["q"][0]
        assert q.startswith('"') and q.endswith('"')  # exact phrase
        assert headers["Authorization"] == "Bearer tok123"
        assert headers["X-GitHub-Api-Version"] == "2022-11-28"
    sent = " ".join(urllib.parse.unquote(u) for u, _ in fake.calls)
    assert not any(c in sent for c in _core_values(vault))  # core traps stay private by default
    leads = watch.leads(vault)
    assert leads[0]["url"] == "https://github.com/cloner/lantern-moths/blob/main/game/data_table.gd"
    assert json.loads(leads[0]["detail"])["repository"] == "cloner/lantern-moths"
    assert "tok123" not in json.dumps(leads)
    # second run finds the same files: no duplicate leads
    r2 = watch.run(vault, ["github"], token="tok123", accept_disclosure=True, sleep=lambda s: None)
    assert r2["sources"]["github"]["new_leads"] == 0 and len(watch.leads(vault)) == len(leads)


def test_github_rate_limit_stops_the_source(vault, monkeypatch):
    fake = FakeAPI(github=(403, {"message": "API rate limit exceeded"}))
    monkeypatch.setattr(watch, "http_get_json", fake)
    r = watch.run(vault, ["github"], token="t", accept_disclosure=True, sleep=lambda s: None)
    assert r["sources"]["github"]["status"] == "rate_limited" and len(fake.calls) == 1


def test_npm_keeps_exact_matches_only():
    data = _fx("npm_search_left-pad.json")
    fake = FakeAPI(npm=(200, data))
    orig = watch.http_get_json
    watch.http_get_json = fake
    try:
        st, hits = watch._npm({"label": "x", "value": "Fastest implementation"})
        assert st == "ok" and [h["detail"]["package"] for h in hits] == ["pad-left"]
        assert hits[0]["url"] == "https://www.npmjs.com/package/pad-left"
        assert watch._npm({"label": "x", "value": "nothing-like-this-anywhere"}) == ("ok", [])
    finally:
        watch.http_get_json = orig


def test_swh_hash_lookups_record_archived_files(vault, monkeypatch):
    fake = FakeAPI(swh=(200, _fx("swh_content_found.json")))
    monkeypatch.setattr(watch, "http_get_json", fake)
    r = watch.run(vault, ["swh"], sleep=lambda s: None)  # hash lookups need no disclosure flag
    n = len(watch.hash_needles(vault))
    assert r["sources"]["swh"]["queries"] == n and r["disclosure"] is None
    sent = " ".join(u for u, _ in fake.calls)
    assert not any(t["value"] in sent for t in traps.records(vault) if t["kind"] == "string")
    assert all(u.startswith("https://archive.softwareheritage.org/api/1/content/sha") for u, _ in fake.calls)
    assert watch.leads(vault)[0]["url"].startswith("https://archive.softwareheritage.org/browse/content/")


def test_swh_not_archived_and_quota(vault, monkeypatch):
    monkeypatch.setattr(watch, "http_get_json", FakeAPI(swh=(404, {"exception": "NotFoundExc"})))
    r = watch.run(vault, ["swh"], sleep=lambda s: None)
    assert r["sources"]["swh"]["new_leads"] == 0 and r["sources"]["swh"]["status"] == "ok"
    fake = FakeAPI(swh=(404, None), swh_headers={"x-ratelimit-remaining": "0"})
    monkeypatch.setattr(watch, "http_get_json", fake)
    r = watch.run(vault, ["swh"], sleep=lambda s: None)
    assert r["sources"]["swh"]["status"] == "rate_limited" and len(fake.calls) == 1


def test_only_https():
    with pytest.raises(ValueError, match="HTTPS"):
        watch.http_get_json("http://registry.npmjs.org/-/v1/search?text=x")
