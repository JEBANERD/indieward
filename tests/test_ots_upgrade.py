"""retry_pending upgrades OpenTimestamps proofs through the official `ots` client."""
from __future__ import annotations

import hashlib
import shutil
import subprocess

import pytest

from indieward import timestamp, util
from indieward.vault import Vault

DIGEST = hashlib.sha256(b"IndieWard ots upgrade test").hexdigest()
# A calendar reply that only holds a pending attestation pointing at a local, closed port.
_URI = b"http://127.0.0.1:9"
PENDING_REPLY = b"\x00" + b"\x83\xdf\xe3\x0d\x2e\xf9\x0c\x8e" + bytes([len(_URI) + 1, len(_URI)]) + _URI


def _vault_with_pending_ots(tmp_path):
    v = Vault.init(tmp_path, "Lantern Moth", "Test Studio")
    tsdir = v.path("certs", "timestamps")
    tsdir.mkdir(parents=True, exist_ok=True)
    out = tsdir / f"{DIGEST[:16]}.ots"
    out.write_bytes(timestamp.OTS_MAGIC + b"\x01\x08" + bytes.fromhex(DIGEST) + PENDING_REPLY)
    v.db.execute("INSERT INTO timestamps (subject,digest,kind,status,service,token_path,requested_at)"
                 " VALUES (?,?,?,?,?,?,?)",
                 ("test", DIGEST, "opentimestamps", "pending-bitcoin", "cal", out.name, util.now_iso()))
    v.db.commit()
    return v, out


def test_retry_marks_anchored_when_client_reports_success(tmp_path, monkeypatch):
    v, out = _vault_with_pending_ots(tmp_path)
    monkeypatch.setattr(timestamp.shutil, "which", lambda name: "/fake/ots")
    monkeypatch.setattr(timestamp.subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(
        a[0], 0, stdout="Success! Timestamp complete\n", stderr=""))
    res = timestamp.retry_pending(v)
    assert res[0]["status"] == "anchored"
    assert v.db.execute("SELECT status FROM timestamps").fetchone()[0] == "anchored"


def test_retry_stays_pending_without_client(tmp_path, monkeypatch):
    v, _ = _vault_with_pending_ots(tmp_path)
    monkeypatch.setattr(timestamp.shutil, "which", lambda name: None)
    res = timestamp.retry_pending(v)
    assert res[0]["status"] == "pending-bitcoin" and "pip install opentimestamps-client" in res[0]["note"]
    assert v.db.execute("SELECT status FROM timestamps").fetchone()[0] == "pending-bitcoin"


@pytest.mark.skipif(not shutil.which("ots"), reason="install opentimestamps-client to run the real client")
def test_real_ots_client_reads_our_file_and_proof_stays_pending(tmp_path):
    v, out = _vault_with_pending_ots(tmp_path)
    info = subprocess.run([shutil.which("ots"), "info", str(out)], capture_output=True, text=True)
    assert info.returncode == 0 and DIGEST in info.stdout, info.stderr
    res = timestamp.retry_pending(v)
    assert res[0]["status"] == "pending-bitcoin"
    assert v.db.execute("SELECT status FROM timestamps").fetchone()[0] == "pending-bitcoin"
