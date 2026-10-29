"""The local vault: one folder per game project, on the creator's own machine.

Layout of ``<project>/.indieward/``::

    vault.db            SQLite: project, verifications, assets, builds, traps, checks, docs, takedowns
    keys/signing.pem    Ed25519 private key (certificates). BACK THIS UP.
    keys/mac.key        32-byte watermark MAC key. BACK THIS UP.
    refs/               small references used for informed watermark checks
    fp/                 fingerprints of registered work (private)
    traps/              generated trap snippets per build
    certs/ checks/ packages/ docs/ evidence/

Nothing in here is uploaded anywhere by IndieWard. Only hashes leave the
machine, for timestamping.
"""
from __future__ import annotations

import json
import os
import secrets
import sqlite3
import stat
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from . import util

VAULT_DIR = ".indieward"

SCHEMA = """
CREATE TABLE IF NOT EXISTS project (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, creator TEXT NOT NULL, contact_email TEXT,
    created_at TEXT NOT NULL, public_key TEXT NOT NULL, verify_code TEXT NOT NULL,
    first_published TEXT
);
CREATE TABLE IF NOT EXISTS verifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT, store TEXT NOT NULL, url TEXT NOT NULL, method TEXT NOT NULL,
    status TEXT NOT NULL, detail TEXT, evidence_sha256 TEXT, verified_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS assets (
    id INTEGER PRIMARY KEY AUTOINCREMENT, record_id INTEGER NOT NULL UNIQUE, kind TEXT NOT NULL,
    category TEXT NOT NULL, name TEXT NOT NULL, source_path TEXT, sha256 TEXT NOT NULL, size INTEGER,
    registered_at TEXT NOT NULL, wm_payload TEXT, wm_backend TEXT, wm_info TEXT, wm_output TEXT,
    wm_output_sha256 TEXT, ref_path TEXT, fp_path TEXT, note TEXT
);
CREATE TABLE IF NOT EXISTS builds (
    id TEXT PRIMARY KEY, label TEXT NOT NULL, registered_at TEXT NOT NULL, engine TEXT,
    manifest_sha256 TEXT, trap_commitment TEXT NOT NULL, trap_salt TEXT NOT NULL, verified_at TEXT,
    verify_result TEXT, fp_path TEXT, snippet_files TEXT
);
CREATE TABLE IF NOT EXISTS traps (
    id INTEGER PRIMARY KEY AUTOINCREMENT, build_id TEXT NOT NULL, tier TEXT NOT NULL, kind TEXT NOT NULL,
    label TEXT NOT NULL, value TEXT NOT NULL, salt TEXT
);
CREATE TABLE IF NOT EXISTS checks (
    id TEXT PRIMARY KEY, created_at TEXT NOT NULL, suspect TEXT NOT NULL, overall INTEGER,
    recommendation TEXT, report_path TEXT
);
CREATE TABLE IF NOT EXISTS docs (
    id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, title TEXT NOT NULL, path TEXT NOT NULL,
    sha256 TEXT NOT NULL, added_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS takedowns (
    id INTEGER PRIMARY KEY AUTOINCREMENT, check_id TEXT NOT NULL, store TEXT NOT NULL, created_at TEXT NOT NULL,
    status TEXT NOT NULL, package_path TEXT, sent_at TEXT, note TEXT
);
CREATE TABLE IF NOT EXISTS timestamps (
    id INTEGER PRIMARY KEY AUTOINCREMENT, subject TEXT NOT NULL, digest TEXT NOT NULL, kind TEXT NOT NULL,
    status TEXT NOT NULL, service TEXT, token_path TEXT, stamped_time TEXT, requested_at TEXT NOT NULL,
    error TEXT
);
"""


class NotVerified(PermissionError):
    """Raised when an unverified project tries to register work or build a package."""


class VaultMissing(FileNotFoundError):
    pass


def _private(path: Path) -> None:
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:  # Windows: rely on the user profile's ACLs
        pass


def verify_code_for(public_key_raw: bytes) -> str:
    """Short code the creator pastes into their store page to prove control of it."""
    import base64
    import hashlib

    digest = hashlib.sha256(b"IndieWard verify|" + public_key_raw).digest()
    code = base64.b32encode(digest[:10]).decode().rstrip("=")
    return f"IW-{code[:4]}-{code[4:8]}-{code[8:12]}-{code[12:16]}"


class Vault:
    def __init__(self, root):
        self.project_root = Path(root).resolve()
        self.dir = self.project_root / VAULT_DIR
        if not (self.dir / "vault.db").exists():
            raise VaultMissing(f"No IndieWard vault in {self.project_root}. Run `indieward init` there first.")
        self.db = sqlite3.connect(self.dir / "vault.db")
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)

    # --- creation ------------------------------------------------------------
    @classmethod
    def init(cls, root, name: str, creator: str, contact_email: str | None = None,
             passphrase: str | None = None) -> "Vault":
        root = Path(root).resolve()
        d = root / VAULT_DIR
        if (d / "vault.db").exists():
            raise FileExistsError(f"A vault already exists in {root}")
        for sub in ("keys", "refs", "fp", "traps", "certs", "checks", "packages", "docs", "evidence", "assets"):
            (d / sub).mkdir(parents=True, exist_ok=True)
        key = Ed25519PrivateKey.generate()
        enc = (serialization.BestAvailableEncryption(passphrase.encode()) if passphrase
               else serialization.NoEncryption())
        pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, enc)
        (d / "keys" / "signing.pem").write_bytes(pem)
        (d / "keys" / "mac.key").write_bytes(secrets.token_bytes(32))
        for p in (d / "keys" / "signing.pem", d / "keys" / "mac.key"):
            _private(p)
        (d / ".gitignore").write_text("*\n")  # never commit the vault by accident
        pub = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        db = sqlite3.connect(d / "vault.db")
        db.executescript(SCHEMA)
        db.execute(
            "INSERT INTO project VALUES (?,?,?,?,?,?,?,?)",
            (secrets.token_hex(8), name, creator, contact_email, util.now_iso(), util.b64(pub),
             verify_code_for(pub), None),
        )
        db.commit()
        db.close()
        v = cls(root)
        v._passphrase = passphrase
        return v

    # --- keys ----------------------------------------------------------------
    _passphrase: str | None = None

    def signing_key(self, passphrase: str | None = None) -> Ed25519PrivateKey:
        pw = passphrase or self._passphrase or os.environ.get("INDIEWARD_PASSPHRASE")
        data = (self.dir / "keys" / "signing.pem").read_bytes()
        return serialization.load_pem_private_key(data, password=pw.encode() if pw else None)

    def public_key(self) -> Ed25519PublicKey:
        return Ed25519PublicKey.from_public_bytes(util.unb64(self.project()["public_key"]))

    def mac_key(self) -> bytes:
        return (self.dir / "keys" / "mac.key").read_bytes()

    # --- project ---------------------------------------------------------------
    def project(self) -> sqlite3.Row:
        return self.db.execute("SELECT * FROM project").fetchone()

    def set_first_published(self, date: str) -> None:
        self.db.execute("UPDATE project SET first_published=?", (date,))
        self.db.commit()

    # --- verification gate -----------------------------------------------------
    def verifications(self) -> list[sqlite3.Row]:
        return self.db.execute("SELECT * FROM verifications ORDER BY id").fetchall()

    def is_verified(self) -> bool:
        return any(r["status"] == "verified" for r in self.verifications())

    def require_verified(self, action: str = "register assets") -> None:
        if not self.is_verified():
            raise NotVerified(
                f"This project isn't verified yet, so IndieWard won't {action}. Prove you control the game's "
                f"store page first: `indieward verify page --store itch --url <your game page>` (or steam/roblox). "
                f"This stops anyone from registering someone else's game and filing takedowns against its real "
                f"creator."
            )

    def add_verification(self, store, url, method, status, detail: dict, evidence_sha256: str | None) -> int:
        cur = self.db.execute(
            "INSERT INTO verifications (store,url,method,status,detail,evidence_sha256,verified_at) VALUES (?,?,?,?,?,?,?)",
            (store, url, method, status, json.dumps(detail), evidence_sha256, util.now_iso()),
        )
        self.db.commit()
        return cur.lastrowid

    # --- generic helpers -------------------------------------------------------
    def path(self, *parts) -> Path:
        return self.dir.joinpath(*parts)

    def rel(self, p) -> str:
        return str(Path(p).resolve().relative_to(self.dir))

    def close(self) -> None:
        self.db.close()


def find_vault(start=".") -> Vault:
    """Find the nearest vault at or above ``start`` (like git does)."""
    p = Path(start).resolve()
    for cand in [p, *p.parents]:
        if (cand / VAULT_DIR / "vault.db").exists():
            return Vault(cand)
    raise VaultMissing(f"No IndieWard vault found at or above {p}. Run `indieward init` in your game project.")
