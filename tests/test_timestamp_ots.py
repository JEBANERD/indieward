"""`indieward stamp --retry` upgrades pending OpenTimestamps proofs with the official client."""
from __future__ import annotations

import hashlib
import shutil
import subprocess
from types import SimpleNamespace

import pytest

from indieward import timestamp
from indieward.vault import Vault

DIGEST = hashlib.sha256(b"IndieWard ots upgrade test").hexdigest()


def _pending_vault(tmp_path, local_tsa, monkeypatch):
    monkeypatch.setattr(timestamp, "http_post", local_tsa["post"])
    v = Vault.init(tmp_path, "OTS Test", "Tester")
    res = timestamp.stamp(v, "test", DIGEST)
    assert res["opentimestamps"]["status"] == "pending-bitcoin"
    return v


def _ots_row(v):
    return dict(v.db.execute("SELECT * FROM timestamps WHERE kind='opentimestamps'").fetchone())


def test_retry_marks_upgraded_proof_anchored(tmp_path, local_tsa, monkeypatch):
    v = _pending_vault(tmp_path, local_tsa, monkeypatch)
    calls = []
    monkeypatch.setattr(timestamp.shutil, "which", lambda name: "/fake/ots" if name == "ots" else shutil.which(name))
    monkeypatch.setattr(timestamp.subprocess, "run", lambda cmd, **kw: calls.append(cmd) or SimpleNamespace(
        returncode=0, stdout="", stderr="Success! Timestamp complete\n"))
    out = timestamp.retry_pending(v)
    assert calls and calls[0][:2] == ["/fake/ots", "upgrade"]
    assert [r["status"] for r in out if r["kind"] == "opentimestamps"] == ["anchored"]
    row = _ots_row(v)
    assert row["status"] == "anchored"
    assert row["service"] == "https://a.pool.opentimestamps.org"  # not wiped by the upgrade
    assert row["token_path"] == f"{DIGEST[:16]}.ots"


def test_retry_without_client_leaves_proof_pending(tmp_path, local_tsa, monkeypatch):
    v = _pending_vault(tmp_path, local_tsa, monkeypatch)
    monkeypatch.setattr(timestamp.shutil, "which", lambda name: None if name == "ots" else shutil.which(name))
    out = timestamp.retry_pending(v)
    ots = [r for r in out if r["kind"] == "opentimestamps"]
    assert ots[0]["status"] == "pending-bitcoin" and "opentimestamps-client" in ots[0]["note"]
    assert _ots_row(v)["status"] == "pending-bitcoin"


def test_real_client_reads_proof_and_keeps_it_pending(tmp_path, local_tsa, monkeypatch):
    """With the official client installed: `ots info` parses our file, and an upgrade that can't
    complete (the stub calendar isn't real) leaves the proof pending and the file intact."""
    ots = shutil.which("ots")
    if not ots:
        pytest.skip("install opentimestamps-client to run the official-client check")
    v = _pending_vault(tmp_path, local_tsa, monkeypatch)
    path = v.path("certs", "timestamps", f"{DIGEST[:16]}.ots")
    before = path.read_bytes()
    info = subprocess.run([ots, "info", str(path)], capture_output=True, text=True)
    assert info.returncode == 0, info.stderr
    assert DIGEST in info.stdout
    timestamp.retry_pending(v)
    assert _ots_row(v)["status"] == "pending-bitcoin"
    assert path.read_bytes() == before


WIN_CRASH = ('Traceback (most recent call last):\n  File "key.py", line 27, in <module>\n'
             "TypeError: argument of type 'NoneType' is not iterable\n")


def test_client_that_cannot_start_gets_plain_note(tmp_path, local_tsa, monkeypatch):
    v = _pending_vault(tmp_path, local_tsa, monkeypatch)
    proof = tmp_path / "x.ots"
    proof.write_bytes(b"proof")
    monkeypatch.setattr(timestamp.shutil, "which", lambda name: "/fake/ots")
    monkeypatch.setattr(timestamp.subprocess, "run", lambda cmd, **kw: SimpleNamespace(
        returncode=1, stdout="", stderr=WIN_CRASH))
    r = timestamp._ots_upgrade(proof)
    assert r["status"] == "pending-bitcoin" and "can't start" in r["note"] and "Traceback" not in r["note"]
    assert proof.read_bytes() == b"proof"
    assert [x["status"] for x in timestamp.retry_pending(v) if x["kind"] == "opentimestamps"] == ["pending-bitcoin"]


def test_pending_message_is_not_a_startup_failure():
    assert not timestamp.ots_failed_to_start(1, "Pending confirmation in Bitcoin blockchain")
    assert timestamp.ots_failed_to_start(1, WIN_CRASH)
