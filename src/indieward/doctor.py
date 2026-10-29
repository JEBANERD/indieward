"""``indieward doctor``: check the tools IndieWard relies on and print one fix per problem.

Fixes are printed as text only. Nothing is installed or changed on the machine.
"""
from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from .vault import VAULT_DIR

MIN_PYTHON = (3, 10)


def _platform() -> str:
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    return "linux"


FIXES = {
    "ffmpeg": {
        "windows": "winget install Gyan.FFmpeg   (then open a new terminal so PATH refreshes)",
        "macos": "brew install ffmpeg",
        "linux": "sudo apt install ffmpeg",
    },
    "openssl": {
        "windows": "winget install Git.Git   (Git for Windows ships openssl; add C:\\Program Files\\Git\\mingw64\\bin to PATH)",
        "macos": "brew install openssl   (then put $(brew --prefix openssl)/bin first on PATH)",
        "linux": "sudo apt install openssl",
    },
}


def _check(name: str, ok: bool, detail: str, fix: str | None = None, required: bool = True) -> dict:
    return {"name": name, "ok": ok, "required": required, "detail": detail, "fix": None if ok else fix}


def _openssl_ts(path: str) -> bool:
    try:
        r = subprocess.run([path, "ts", "-help"], capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return False
    out = (r.stdout + r.stderr).lower()
    return "invalid command" not in out and "unknown command" not in out and ("-query" in out or r.returncode == 0)


def _writable(project: Path) -> tuple[bool, str, str]:
    """Can IndieWard write its vault? Uses an existing vault, else the project folder. Creates no vault."""
    p = project.resolve()
    target = next((c / VAULT_DIR for c in [p, *p.parents] if (c / VAULT_DIR / "vault.db").exists()), None)
    where = target if target else p
    try:
        with tempfile.NamedTemporaryFile(dir=where, prefix=".iw-doctor-"):
            pass
    except OSError as e:
        return False, f"cannot write to {where}: {e}", str(where)
    return True, f"{'vault' if target else 'project folder (no vault yet)'} {where} is writable", str(where)


def run_doctor(project: str = ".") -> dict:
    plat = _platform()
    checks = []

    ok = sys.version_info >= MIN_PYTHON
    checks.append(_check("python", ok, f"Python {sys.version.split()[0]}",
                         f"IndieWard needs Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+. Install a newer Python from https://www.python.org/downloads/"))

    ff, fp = shutil.which("ffmpeg"), shutil.which("ffprobe")
    missing = [n for n, w in (("ffmpeg", ff), ("ffprobe", fp)) if not w]
    checks.append(_check("ffmpeg", not missing, "ffmpeg and ffprobe found" if not missing else f"not found: {', '.join(missing)}",
                         FIXES["ffmpeg"][plat] + "   (only audio and video need it)"))

    ossl = shutil.which("openssl")
    if not ossl:
        checks.append(_check("openssl", False, "openssl not found", FIXES["openssl"][plat]))
    else:
        ts = _openssl_ts(ossl)
        checks.append(_check("openssl", ts, f"{ossl}" + ("" if ts else " has no `openssl ts` support"),
                             FIXES["openssl"][plat]))

    ots = shutil.which("ots")
    checks.append(_check("ots", bool(ots), ots or "not found (optional: completes OpenTimestamps proofs)",
                         "pip install opentimestamps-client", required=False))

    has_mcp = importlib.util.find_spec("mcp") is not None
    checks.append(_check("mcp", has_mcp, "mcp package found" if has_mcp else "mcp package not installed (optional: Claude plugin)",
                         'pip install "indieward[mcp]"', required=False))

    w_ok, w_detail, _ = _writable(Path(project))
    checks.append(_check("vault-write", w_ok, w_detail,
                         "Pick a folder you can write to (not a read-only or synced-and-locked folder), or fix its permissions."))

    problems = [c for c in checks if not c["ok"]]
    return {
        "platform": plat,
        "ok": not any(c["required"] for c in problems),
        "checks": checks,
        "fixes": [f"{c['name']}: {c['fix']}" for c in problems],
        "note": "Printed commands only: nothing was installed or changed.",
    }


def format_report(rep: dict) -> str:
    lines = []
    for c in rep["checks"]:
        mark = "ok  " if c["ok"] else ("FAIL" if c["required"] else "warn")
        lines.append(f"[{mark}] {c['name']}: {c['detail']}")
        if c["fix"]:
            lines.append(f"       fix: {c['fix']}")
    lines.append("")
    lines.append("All required checks passed." if rep["ok"] else "Some required checks failed; see the fixes above.")
    lines.append(rep["note"])
    return "\n".join(lines)
