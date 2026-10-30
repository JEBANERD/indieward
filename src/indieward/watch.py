"""Canary monitoring: look for your trap markers and notice in public code, using official APIs only.

Opt-in. Sources:
- GitHub code search (REST API, authenticated with the creator's own token). It ignores quotes, so hits are
  kept only when a returned fragment holds the exact string.
- npm registry search. Matches package names, descriptions and keywords only, not file contents.
- Software Heritage content lookup by hash. Only hashes of your trap files and hidden asset are sent.

Searching GitHub or npm sends the searched string to that provider. That discloses the marker to them,
so text searches use build traps and the public notice line by default; core traps (shared by every
build) are searched only when the creator asks. Hash lookups disclose nothing readable.

Hits are written to the vault as leads for the creator to review. Nothing is ever filed or sent.
"""
from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request

from . import notice, traps, util
from .vault import Vault

SOURCES = ("github", "npm", "swh")
TEXT_SOURCES = ("github", "npm")
UA = "IndieWard-watch (+https://github.com/JEBANERD/indieward)"
# GitHub allows 10 code-search requests a minute; Software Heritage 120 an hour without a token.
PACE = {"github": 6.5, "npm": 1.0, "swh": 1.0}
MIN_TEXT = 8  # shorter strings match too much to be useful leads

DISCLOSURE = ("Searching GitHub or npm sends each searched string to that company. Anyone with access to their "
              "logs could learn your markers. Hash lookups (Software Heritage) send only hashes.")

LEADS_SQL = """CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT, found_at TEXT NOT NULL, source TEXT NOT NULL, needle TEXT NOT NULL,
    url TEXT NOT NULL, detail TEXT, status TEXT NOT NULL DEFAULT 'new', UNIQUE (source, needle, url))"""


def http_get_json(url: str, headers: dict | None = None, timeout: float = 20.0) -> tuple[int, dict, object]:
    """One HTTPS GET returning (status, headers, parsed JSON or None). Replaced in tests."""
    if not url.startswith("https://"):
        raise ValueError("watch only uses HTTPS")
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            status, hdrs, body = r.status, dict(r.headers), r.read(5_000_000)
    except urllib.error.HTTPError as e:
        status, hdrs, body = e.code, dict(e.headers or {}), e.read() if hasattr(e, "read") else b""
    try:
        data = json.loads(body) if body else None
    except ValueError:
        data = None
    return status, {k.lower(): v for k, v in hdrs.items()}, data


def text_needles(vault: Vault, include_core: bool = False) -> list[dict]:
    """Strings to search for: build-tier trap strings, optionally core ones, and the public notice line."""
    out, seen = [], set()
    for t in traps.records(vault):
        if t["kind"] != "string" or len(t["value"]) < MIN_TEXT or t["value"] in seen:
            continue
        if t["tier"] == "core" and not include_core:
            continue
        seen.add(t["value"])
        out.append({"label": f"trap {t['id']} ({t['tier']} {t['label']}, build {t['build_id']})", "value": t["value"]})
    note = notice.recorded(vault)
    if note:
        out.append({"label": "copyright notice", "value": note["credits"], "notice": True})
    return out


def hash_needles(vault: Vault) -> list[dict]:
    """sha1 of every stored trap snippet file and sha256 of each hidden asset. Only the hash leaves the machine."""
    out, seen = [], set()
    for b in vault.db.execute("SELECT id FROM builds ORDER BY registered_at").fetchall():
        root = vault.path("traps", b["id"])
        if not root.exists():
            continue
        for f in sorted(root.rglob("*")):
            if f.is_file() and not f.name.startswith("README_"):
                h = hashlib.sha1(f.read_bytes()).hexdigest()
                if h not in seen:
                    seen.add(h)
                    out.append({"label": f"trap file {f.name} (build {b['id']})", "algo": "sha1", "hash": h})
    for t in traps.records(vault):
        if t["kind"] == "asset_sha256" and t["value"] not in seen:
            seen.add(t["value"])
            out.append({"label": f"trap {t['id']} (hidden asset, build {t['build_id']})", "algo": "sha256",
                        "hash": t["value"]})
    return out


def _github(needle: dict, token: str) -> tuple[str, list[dict]]:
    # Code search ignores quotes and punctuation, so a hit only means every word is somewhere in the file.
    # Ask for the matched fragments and keep only files where the exact string appears.
    q = urllib.parse.quote(f'"{needle["value"]}"')
    st, hdrs, data = http_get_json(f"https://api.github.com/search/code?q={q}&per_page=30", {
        "Authorization": f"Bearer {token}", "Accept": "application/vnd.github.text-match+json",
        "X-GitHub-Api-Version": "2022-11-28"})
    msg = str(data.get("message", "")).lower() if isinstance(data, dict) else ""
    if st == 429 or (st == 403 and (hdrs.get("x-ratelimit-remaining") == "0" or "rate limit" in msg)):
        return "rate_limited", []
    if st in (401, 403):
        return "auth_error", []  # bad or under-scoped GITHUB_TOKEN
    if st != 200 or not isinstance(data, dict):
        return f"http_{st}", []
    v = needle["value"].lower()
    return "ok", [{"url": i["html_url"], "detail": {"repository": i.get("repository", {}).get("full_name"),
                                                     "path": i.get("path")}}
                  for i in data.get("items", []) if i.get("html_url")
                  and any(v in (m.get("fragment") or "").lower() for m in i.get("text_matches") or [])]


def _npm(needle: dict) -> tuple[str, list[dict]]:
    q = urllib.parse.quote(needle["value"])
    st, _, data = http_get_json(f"https://registry.npmjs.org/-/v1/search?text={q}&size=20")
    if st == 429:
        return "rate_limited", []
    if st != 200 or not isinstance(data, dict):
        return f"http_{st}", []
    v = needle["value"].lower()
    hits = []
    for o in data.get("objects", []):
        p = o.get("package", {})
        text = " ".join([p.get("name", ""), p.get("description") or "", *p.get("keywords", [])]).lower()
        if v in text:  # npm search is fuzzy; keep exact matches only
            hits.append({"url": p.get("links", {}).get("npm") or f"https://www.npmjs.com/package/{p.get('name')}",
                         "detail": {"package": p.get("name"), "version": p.get("version")}})
    return "ok", hits


def _swh(needle: dict) -> tuple[str, list[dict]]:
    st, hdrs, data = http_get_json(
        f"https://archive.softwareheritage.org/api/1/content/{needle['algo']}:{needle['hash']}/")
    if st == 429:
        return "rate_limited", []
    if st not in (200, 404) or (st == 200 and not isinstance(data, dict)):
        return f"http_{st}", []
    hits = [] if st == 404 else [{
        "url": f"https://archive.softwareheritage.org/browse/content/{needle['algo']}:{needle['hash']}/",
        "detail": {"length": data.get("length"), "status": data.get("status")}}]
    # out of quota: keep this answer, stop before the next request
    return ("rate_limited" if hdrs.get("x-ratelimit-remaining") == "0" else "ok"), hits


def run(vault: Vault, sources, token: str | None = None, include_core: bool = False,
        accept_disclosure: bool = False, sleep=time.sleep) -> dict:
    """Search the chosen sources and store new leads. Returns a per-source summary."""
    vault.require_verified("watch for copies")
    sources = list(dict.fromkeys(sources))
    bad = [s for s in sources if s not in SOURCES]
    if bad or not sources:
        raise ValueError(f"choose sources from {', '.join(SOURCES)}")
    if any(s in TEXT_SOURCES for s in sources) and not accept_disclosure:
        raise ValueError(f"{DISCLOSURE} Pass --accept-disclosure to search GitHub or npm.")
    if "github" in sources and not token:
        raise ValueError("GitHub code search needs your own token: set GITHUB_TOKEN.")
    vault.db.execute(LEADS_SQL)
    texts, hashes = text_needles(vault, include_core), hash_needles(vault)
    summary = {}
    for src in sources:
        needles = hashes if src == "swh" else [n for n in texts if src == "github" or not n.get("notice")]
        s = {"queries": 0, "hits": 0, "new_leads": 0, "status": "ok"}
        for k, n in enumerate(needles):
            if k:
                sleep(PACE[src])
            st, hits = _github(n, token) if src == "github" else _npm(n) if src == "npm" else _swh(n)
            s["queries"] += 1
            for h in hits:
                s["hits"] += 1
                cur = vault.db.execute(
                    "INSERT OR IGNORE INTO leads (found_at,source,needle,url,detail) VALUES (?,?,?,?,?)",
                    (util.now_iso(), src, n["label"], h["url"], json.dumps(h["detail"])))
                s["new_leads"] += cur.rowcount
            if st != "ok":
                s["status"] = st
                break  # stop this source on a rate limit or error rather than hammer it
        vault.db.commit()
        summary[src] = s
    return {"sources": summary, "note": "Leads are for you to review. Nothing was filed or sent.",
            "disclosure": DISCLOSURE if any(s in TEXT_SOURCES for s in sources) else None}


def leads(vault: Vault) -> list[dict]:
    vault.db.execute(LEADS_SQL)
    return [dict(r) for r in vault.db.execute("SELECT * FROM leads ORDER BY id")]
