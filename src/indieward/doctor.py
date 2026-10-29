"""`indieward doctor`: check the local setup and print one fix per problem.

Read-only. It never installs anything; fixes are printed as commands for the
creator to run themselves.
"""
from __future__ import annotations

import importlib.util
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

MIN_PYTHON = (3, 10)


def _os() -> str:
    s = platform.system()
    return {"Windows": "windows", "Darwin": "macos"}.get(s, "linux")


_FIX = {
    "python": {
        "windows": "Install Python 3.10+ from https://www.python.org/downloads/ (tick 'Add python.exe to PATH').",
        "macos": "brew install python@3.12",
        "linux": "sudo apt install python3 python3-pip   (or your distro's equivalent; need 3.10+)",
    },
    "ffmpeg": {
        "windows": "winget install Gyan.FFmpeg   (then open a new terminal so PATH refreshes)",
        "macos": "brew install ffmpeg",
        "linux": "sudo apt install ffmpeg",
    },
    "openssl": {
        "windows": "winget install Git.Git   (Git for Windows includes openssl; add C:\\Program Files\\Git\\mingw64\\bin to PATH)",
        "macos": "brew install openssl   (macOS's built-in LibreSSL has no `openssl ts`; put brew's openssl first on PATH)",
        "linux": "sudo apt install openssl",
    },
    "ots": {
        "windows": "py -m pip install --user opentimestamps-client",
        "macos": "pipx install opentimestamps-client",
        "linux": "pipx install opentimestamps-client",
    },
    "mcp": {
        "windows": 'pipx install "indieward[mcp]" --force   (or: py -m pip install --user "indieward[mcp]")',
        "macos": 'pipx install "indieward[mcp]" --force',
        "linux": 'pipx install "indieward[mcp]" --force',
    },
}


def _item(name, status, detail, fix=None):
    return {"name": name, "status": status, "detail": detail, "fix": fix}


def _openssl_has_ts(path: str) -> bool:
    try:
        r = subprocess.run([path, "ts", "-help"], capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return False
    text = (r.stdout + r.stderr).lower()
    return not any(w in text for w in ("invalid command", "unknown command", "not a known command"))


def _vault_check(project_dir) -> dict:
    p = Path(project_dir).resolve()
    for cand in [p, *p.parents]:
        d = cand / ".indieward"
        if (d / "vault.db").exists():
            ok = os.access(d, os.W_OK) and os.access(d / "vault.db", os.W_OK)
            return _item("vault", "ok" if ok else "problem", f"vault at {d}" + ("" if ok else " is not writable"),
                         None if ok else f"Fix permissions on {d} (it must be writable by your user).")
    ok = os.access(p, os.W_OK)
    if ok:
        return _item("vault", "ok", f"no vault yet in {p}; folder is writable (run `indieward init` to create one)")
    return _item("vault", "problem", f"no vault, and {p} is not writable",
                 "Run indieward from a game project folder you can write to.")


def run_doctor(project_dir=".") -> dict:
    which = _os()
    items = []

    v = sys.version_info
    ok = (v.major, v.minor) >= MIN_PYTHON
    items.append(_item("python", "ok" if ok else "problem", f"Python {v.major}.{v.minor}.{v.micro}",
                       None if ok else _FIX["python"][which]))

    for tool in ("ffmpeg", "ffprobe"):
        found = shutil.which(tool)
        items.append(_item(tool, "ok" if found else "problem", found or "not found on PATH (needed for audio and video)",
                           None if found else _FIX["ffmpeg"][which]))

    ossl = shutil.which("openssl")
    if not ossl:
        items.append(_item("openssl", "problem", "not found on PATH (needed for RFC 3161 timestamps)", _FIX["openssl"][which]))
    elif not _openssl_has_ts(ossl):
        items.append(_item("openssl", "problem", f"{ossl} has no `openssl ts` support", _FIX["openssl"][which]))
    else:
        items.append(_item("openssl", "ok", f"{ossl} (supports `openssl ts`)"))

    ots = shutil.which("ots")
    items.append(_item("ots", "ok" if ots else "optional", ots or "not installed (optional: completes OpenTimestamps proofs)",
                       None if ots else _FIX["ots"][which]))

    has_mcp = importlib.util.find_spec("mcp") is not None
    items.append(_item("mcp", "ok" if has_mcp else "optional",
                       "mcp package installed" if has_mcp else "not installed (optional: needed for the Claude plugin)",
                       None if has_mcp else _FIX["mcp"][which]))

    items.append(_vault_check(project_dir))

    problems = [i for i in items if i["status"] == "problem"]
    return {"platform": which, "ok": not problems, "problems": len(problems), "checks": items}


def format_report(rep: dict) -> str:
    mark = {"ok": "[ok]      ", "problem": "[PROBLEM] ", "optional": "[optional]"}
    lines = []
    for i in rep["checks"]:
        lines.append(f"{mark[i['status']]} {i['name']}: {i['detail']}")
        if i["fix"]:
            lines.append(f"           fix: {i['fix']}")
    lines.append("")
    lines.append("All required checks passed." if rep["ok"] else f"{rep['problems']} problem(s) to fix. Nothing was installed; run the fix commands yourself.")
    return "\n".join(lines)
