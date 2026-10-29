"""Ownership verification: prove you control the game's store presence.

Required before any asset can be registered or any takedown package built.
Methods, strongest first:

- ``steam-key``: a Steamworks *publisher* Web API key. IndieWard calls
  ISteamApps/GetPartnerAppListForWebAPIKey once and checks the app is listed.
  The key is used once and never stored.
- ``itch-key``: an itch.io API key from your account settings. IndieWard calls
  the server-side API (my-games) once and checks the game is yours. Never stored.
- ``page``: put your project's verification code (``indieward status`` shows
  it) anywhere in the game's public store description, then IndieWard reads that
  one public page (or, for Roblox, the official public games API) and checks
  the code is there. A store's trust team can check the same code themselves,
  which makes this the easiest method for them to trust.

Only creator-controlled text is searched: the itch.io description block (not
comments), Steam's store API description fields, Roblox's games API
description.

What it proves: control of the store page or developer account at that time.
It does not prove authorship. Since the code is open source, someone can patch
the check out of their own copy; certificates therefore record the method,
the URL and a hash of what was seen, so a store can re-check.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request

from . import util
from .vault import Vault

UA = "IndieWard/0.1 (+https://github.com/indieward/indieward; ownership check, single request)"


def http_get(url: str, timeout: float = 20.0) -> tuple[int, bytes]:
    """One polite GET. Replaced in tests."""
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read(5_000_000)
    except urllib.error.HTTPError as e:
        return e.code, e.read() if hasattr(e, "read") else b""


class VerifyError(ValueError):
    pass


def parse_store_url(store: str, url: str) -> dict:
    u = urllib.parse.urlparse(url)
    host = (u.hostname or "").lower()
    if u.scheme != "https":
        raise VerifyError("Use the https:// address of the store page.")
    if store == "steam":
        m = re.match(r"^/app/(\d+)", u.path)
        if host != "store.steampowered.com" or not m:
            raise VerifyError("Steam URLs look like https://store.steampowered.com/app/<appid>/...")
        return {"store": "steam", "app_id": m.group(1)}
    if store == "itch":
        m = re.match(r"^([a-z0-9-]+)\.itch\.io$", host)
        slug = u.path.strip("/").split("/")[0] if u.path.strip("/") else ""
        if not m or not slug:
            raise VerifyError("itch.io URLs look like https://<you>.itch.io/<game>")
        return {"store": "itch", "user": m.group(1), "slug": slug}
    if store == "roblox":
        m = re.match(r"^/games/(\d+)", u.path)
        if host not in ("www.roblox.com", "roblox.com") or not m:
            raise VerifyError("Roblox URLs look like https://www.roblox.com/games/<placeId>/...")
        return {"store": "roblox", "place_id": m.group(1)}
    raise VerifyError("store must be one of: steam, itch, roblox")


def _code_in(text: str, code: str) -> int:
    norm = re.sub(r"[\s​]+", "", text)
    return norm.upper().find(code.replace(" ", "").upper())


def _page_text_for(info: dict, url: str) -> tuple[str, str]:
    """Return (text to search, source url actually read)."""
    if info["store"] == "roblox":
        # Official public APIs rather than scraping the website.
        s, body = http_get(f"https://apis.roblox.com/universes/v1/places/{info['place_id']}/universe")
        if s != 200:
            raise VerifyError(f"Roblox universe lookup failed (HTTP {s}).")
        uni = json.loads(body)["universeId"]
        src = f"https://games.roblox.com/v1/games?universeIds={uni}"
        s, body = http_get(src)
        if s != 200:
            raise VerifyError(f"Roblox games API failed (HTTP {s}).")
        data = json.loads(body)["data"][0]
        return json.dumps({"name": data.get("name"), "description": data.get("description"),
                           "creator": data.get("creator")}), src
    if info["store"] == "steam":
        src = f"https://store.steampowered.com/api/appdetails?appids={info['app_id']}&l=english"
        s, body = http_get(src)
        if s != 200:
            raise VerifyError(f"Steam store API failed (HTTP {s}).")
        d = json.loads(body).get(info["app_id"], {}).get("data", {})
        return json.dumps({k: d.get(k) for k in ("name", "short_description", "about_the_game", "developers")}), src
    s, body = http_get(url)
    if s != 200:
        raise VerifyError(f"Couldn't read the page (HTTP {s}).")
    return _itch_description(body.decode("utf-8", "replace")), url


def _itch_description(page: str) -> str:
    """Only the creator-written description, never comments or other user content.

    Anyone can post a comment on an itch.io page, so searching the whole page
    would let an impostor "verify" someone else's game.
    """
    m = re.search(r'<div[^>]+class="[^"]*\bformatted_description\b[^"]*"[^>]*>', page)
    if not m:
        raise VerifyError("Couldn't find the game's description on that itch.io page. Use "
                          "`indieward verify itch-key` instead.")
    rest = page[m.end():]
    # The description ends where the next page section begins.
    stop = re.search(r'class="[^"]*\b(more_information_toggle|game_comments_widget|community_post|'
                     r'game_info_panel_widget|purchase_banner|comment)', rest)
    return rest[: stop.start()] if stop else rest[:200_000]


def verify_page(vault: Vault, store: str, url: str) -> dict:
    info = parse_store_url(store, url)
    code = vault.project()["verify_code"]
    text, src = _page_text_for(info, url)
    pos = _code_in(text, code)
    evidence = util.sha256_bytes(text.encode("utf-8"))
    if pos < 0:
        vault.add_verification(store, url, "page", "failed", {"read": src, "code": code}, evidence)
        raise VerifyError(
            f"Code {code} wasn't found on {src}. Paste it into the game's public description, save, and try "
            f"again. You can remove it after verification (the certificate keeps a hash of what was seen)."
        )
    detail = {"read": src, "code": code, **info}
    vault.add_verification(store, url, "page", "verified", detail, evidence)
    return {"status": "verified", "method": "page", "store": store, "url": url, "read": src,
            "evidence_sha256": evidence}


def verify_itch_key(vault: Vault, url: str, api_key: str) -> dict:
    info = parse_store_url("itch", url)
    s, body = http_get(f"https://itch.io/api/1/{urllib.parse.quote(api_key)}/my-games")
    if s != 200:
        raise VerifyError(f"itch.io API refused the key (HTTP {s}).")
    games = json.loads(body).get("games", [])
    want = f"https://{info['user']}.itch.io/{info['slug']}".lower()
    hit = next((g for g in games if str(g.get("url", "")).lower().rstrip("/") == want), None)
    evidence = util.sha256_bytes(body)
    if not hit:
        vault.add_verification("itch", url, "itch-key", "failed", {"games_listed": len(games)}, evidence)
        raise VerifyError("That game isn't in the API key owner's game list.")
    vault.add_verification("itch", url, "itch-key", "verified", {"game_id": hit.get("id"), **info}, evidence)
    return {"status": "verified", "method": "itch-key", "store": "itch", "url": url, "evidence_sha256": evidence}


def verify_steam_key(vault: Vault, url: str, publisher_key: str) -> dict:
    info = parse_store_url("steam", url)
    s, body = http_get("https://partner.steam-api.com/ISteamApps/GetPartnerAppListForWebAPIKey/v2/?key="
                       + urllib.parse.quote(publisher_key))
    if s != 200:
        raise VerifyError(f"Steamworks API refused the key (HTTP {s}). It must be a publisher Web API key.")
    apps = json.loads(body).get("applist", {}).get("apps", {}).get("app", [])
    ids = {str(a.get("appid")) for a in apps}
    evidence = util.sha256_bytes(body)
    if info["app_id"] not in ids:
        vault.add_verification("steam", url, "steam-key", "failed", {"apps_listed": len(ids)}, evidence)
        raise VerifyError("That app isn't owned by the publisher key's account.")
    vault.add_verification("steam", url, "steam-key", "verified", info, evidence)
    return {"status": "verified", "method": "steam-key", "store": "steam", "url": url, "evidence_sha256": evidence}
