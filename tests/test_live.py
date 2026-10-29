"""Live checks against the real outside services IndieWard depends on.

Skipped unless INDIEWARD_LIVE=1 (the weekly `live` workflow sets it). Each test
makes one or two polite read-only requests. If one fails, the service changed
or is down: the fix belongs in timestamp.py, verify.py or stores.py.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import urllib.request

import pytest

from indieward import timestamp, verify

pytestmark = [pytest.mark.live,
              pytest.mark.skipif(os.environ.get("INDIEWARD_LIVE") != "1", reason="set INDIEWARD_LIVE=1")]

ITCH_URL = os.environ.get("INDIEWARD_LIVE_ITCH_URL", "https://leafo.itch.io/x-moon")
STEAM_APP = os.environ.get("INDIEWARD_LIVE_STEAM_APP", "440")
ROBLOX_PLACE = os.environ.get("INDIEWARD_LIVE_ROBLOX_PLACE", "1818")
DIGEST = hashlib.sha256(b"IndieWard live test").hexdigest()


def test_freetsa_stamp_and_verify(tmp_path):
    r = timestamp.rfc3161(DIGEST, tmp_path / "t.tsr")
    assert r["status"] == "stamped", r
    ca = tmp_path / "cacert.pem"
    with urllib.request.urlopen("https://freetsa.org/files/cacert.pem", timeout=30) as resp:
        ca.write_bytes(resp.read())
    res = timestamp.check_token((tmp_path / "t.tsr").read_bytes(), DIGEST, ca)
    assert res == "verified against TSA certificate", res


def test_opentimestamps_calendar_and_official_client(tmp_path):
    out = tmp_path / "t.ots"
    r = timestamp.opentimestamps(DIGEST, out)
    assert r["status"] == "pending-bitcoin", r
    ots = shutil.which("ots")
    if not ots:
        pytest.skip("install opentimestamps-client to check the .ots file format")
    info = subprocess.run([ots, "info", str(out)], capture_output=True, text=True)
    assert info.returncode == 0, info.stderr
    assert DIGEST in info.stdout, info.stdout


def test_steam_store_api_shape():
    s, body = verify.http_get(f"https://store.steampowered.com/api/appdetails?appids={STEAM_APP}&l=english")
    assert s == 200
    d = json.loads(body)[STEAM_APP]["data"]
    for k in ("name", "short_description", "about_the_game"):
        assert k in d


def test_roblox_public_api_shape():
    s, body = verify.http_get(f"https://apis.roblox.com/universes/v1/places/{ROBLOX_PLACE}/universe")
    assert s == 200
    uni = json.loads(body)["universeId"]
    s, body = verify.http_get(f"https://games.roblox.com/v1/games?universeIds={uni}")
    assert s == 200
    assert "description" in json.loads(body)["data"][0]


def test_itch_description_block_found():
    s, body = verify.http_get(ITCH_URL)
    assert s == 200
    desc = verify._itch_description(body.decode("utf-8", "replace"))
    assert len(desc.strip()) > 20
    assert "community_post" not in desc
