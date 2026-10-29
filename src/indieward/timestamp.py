"""Independent timestamps for certificates and registrations.

Two anchors, so proof of "I had this by date X" doesn't rest on IndieWard or
any single company:

1. RFC 3161 timestamp authority (default FreeTSA). The request is built and
   the reply parsed with the ``openssl ts`` command, which ships with Git for
   Windows, macOS and Linux.
2. OpenTimestamps calendars, anchored in Bitcoin. IndieWard stores the
   calendar's pending proof as a standard .ots file; upgrade and verify it
   later with the official client (``pip install opentimestamps-client``,
   then ``ots upgrade`` / ``ots verify``).

Only a SHA-256 digest leaves the machine. If you're offline, the timestamp is
recorded as pending and ``indieward stamp --retry`` finishes it later.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import urllib.request
from pathlib import Path

from . import util
from .vault import Vault

TSA_URL = "https://freetsa.org/tsr"
OTS_CALENDARS = ("https://a.pool.opentimestamps.org", "https://b.pool.opentimestamps.org")
OTS_MAGIC = b"\x00OpenTimestamps\x00\x00Proof\x00\xbf\x89\xe2\xe8\x84\xe8\x92\x94"


def http_post(url: str, data: bytes, content_type: str, timeout: float = 30.0) -> bytes:
    """Replaced in tests."""
    req = urllib.request.Request(url, data=data, headers={"Content-Type": content_type,
                                                          "User-Agent": "IndieWard/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _openssl() -> str | None:
    return shutil.which("openssl")


def rfc3161(digest_hex: str, out_path: Path, tsa_url: str = TSA_URL) -> dict:
    ossl = _openssl()
    if not ossl:
        return {"status": "pending", "error": "openssl not found"}
    with tempfile.TemporaryDirectory() as td:
        tsq = Path(td) / "req.tsq"
        subprocess.run([ossl, "ts", "-query", "-digest", digest_hex, "-sha256", "-cert", "-out", str(tsq)],
                       check=True, capture_output=True)
        try:
            reply = http_post(tsa_url, tsq.read_bytes(), "application/timestamp-query")
        except Exception as e:  # offline, blocked, TSA down
            return {"status": "pending", "error": f"{type(e).__name__}: {e}"}
        out_path.write_bytes(reply)
        txt = subprocess.run([ossl, "ts", "-reply", "-in", str(out_path), "-text"],
                             capture_output=True, text=True)
        if txt.returncode != 0 or "Status: Granted" not in txt.stdout:
            return {"status": "failed", "error": (txt.stdout + txt.stderr)[-400:]}
        m = re.search(r"Time stamp:\s*(.+)", txt.stdout)
        # The reply's message imprint must be our digest.
        hexes = ""
        for line in re.findall(r"^\s+[0-9a-f]{4} - (.{47})", txt.stdout, re.M):
            hexes += re.sub(r"[^0-9a-f]", "", line)
        ok_digest = digest_hex.lower() == hexes.lower()
        return {"status": "stamped" if ok_digest else "failed", "service": tsa_url,
                "time": m.group(1).strip() if m else None, "token": out_path.name}


def check_token(token: bytes, digest_hex: str, tsa_ca=None) -> str:
    """Re-check an RFC 3161 token: its imprint must be this digest; with the TSA's CA file, its signature too."""
    ossl = _openssl()
    if not ossl:
        return "not checked (openssl missing)"
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "t.tsr"
        p.write_bytes(token)
        txt = subprocess.run([ossl, "ts", "-reply", "-in", str(p), "-text"], capture_output=True, text=True).stdout
        hexes = "".join(re.sub(r"[^0-9a-f]", "", l) for l in re.findall(r"^\s+[0-9a-f]{4} - (.{47})", txt, re.M))
        if hexes.lower() != digest_hex.lower():
            return "INVALID: token is for a different digest"
        if not tsa_ca:
            return "imprint matches (pass the TSA's CA certificate to also check its signature)"
        v = subprocess.run([ossl, "ts", "-verify", "-digest", digest_hex, "-in", str(p), "-CAfile", str(tsa_ca)],
                           capture_output=True, text=True)
        return "verified against TSA certificate" if "Verification: OK" in v.stdout else "INVALID: TSA signature check failed"


def opentimestamps(digest_hex: str, out_path: Path, calendars=OTS_CALENDARS) -> dict:
    digest = bytes.fromhex(digest_hex)
    errors = []
    for cal in calendars:
        try:
            resp = http_post(cal.rstrip("/") + "/digest", digest, "application/octet-stream")
        except Exception as e:
            errors.append(f"{cal}: {type(e).__name__}")
            continue
        # .ots file: magic, version 1, file-hash op (0x08 = sha256), the digest,
        # then the calendar's serialized (pending) timestamp for that digest.
        out_path.write_bytes(OTS_MAGIC + b"\x01" + b"\x08" + digest + resp)
        return {"status": "pending-bitcoin", "service": cal, "token": out_path.name,
                "note": "Calendar commitment received; run `ots upgrade` after a few hours to complete it."}
    return {"status": "pending", "error": "; ".join(errors) or "no calendar reachable"}


def stamp(vault: Vault, subject: str, digest_hex: str) -> dict:
    """Request both timestamps for a digest; record results in the vault."""
    tsdir = vault.path("certs", "timestamps")
    tsdir.mkdir(parents=True, exist_ok=True)
    results = {}
    for kind, fn, ext in (("rfc3161", rfc3161, ".tsr"), ("opentimestamps", opentimestamps, ".ots")):
        out = tsdir / f"{digest_hex[:16]}{ext}"
        r = fn(digest_hex, out)
        vault.db.execute(
            "INSERT INTO timestamps (subject,digest,kind,status,service,token_path,stamped_time,requested_at,error)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (subject, digest_hex, kind, r["status"], r.get("service"), r.get("token"), r.get("time"),
             util.now_iso(), r.get("error")),
        )
        results[kind] = r
    vault.db.commit()
    return results


def _ots_upgrade(path: Path) -> dict:
    """Complete a pending OpenTimestamps proof with the official client, if installed."""
    ots = shutil.which("ots")
    if not ots:
        return {"status": "pending-bitcoin", "token": path.name,
                "note": "Install the official client (pip install opentimestamps-client) to upgrade: ots upgrade "
                        f"{path}"}
    r = subprocess.run([ots, "upgrade", str(path)], capture_output=True, text=True)
    ok = r.returncode == 0 and "Success" in (r.stdout + r.stderr)
    return {"status": "anchored" if ok else "pending-bitcoin", "token": path.name,
            "note": (r.stdout + r.stderr)[-300:]}


def retry_pending(vault: Vault) -> list[dict]:
    rows = vault.db.execute(
        "SELECT * FROM timestamps WHERE status IN ('pending','failed','pending-bitcoin') ORDER BY id").fetchall()
    done = []
    seen = set()
    for r in rows:
        key = (r["digest"], r["kind"])
        if key in seen:
            continue
        seen.add(key)
        tsdir = vault.path("certs", "timestamps")
        if r["status"] == "pending-bitcoin":
            res = _ots_upgrade(tsdir / r["token_path"]) if r["token_path"] else {"status": "pending"}
            if res["status"] == "pending-bitcoin":
                done.append({"subject": r["subject"], "kind": r["kind"], **res})
                continue
        elif r["kind"] == "rfc3161":
            res = rfc3161(r["digest"], tsdir / f"{r['digest'][:16]}.tsr")
        else:
            res = opentimestamps(r["digest"], tsdir / f"{r['digest'][:16]}.ots")
        vault.db.execute("UPDATE timestamps SET status=?, service=?, token_path=?, stamped_time=?, error=? WHERE id=?",
                         (res["status"], res.get("service"), res.get("token"), res.get("time"), res.get("error"),
                          r["id"]))
        done.append({"subject": r["subject"], "kind": r["kind"], **res})
    vault.db.commit()
    return done
