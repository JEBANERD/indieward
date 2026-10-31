"""`indieward doctor`: is this machine ready to run IndieWard?

Checks Python, FFmpeg, OpenSSL (with `openssl ts`), the optional OpenTimestamps
client, MCP package and TrustMark image backend, and that the vault folder is writable. Each problem
comes with one command to fix it for this OS. Nothing is installed for you.
"""
from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from .vault import VAULT_DIR

# Where Git for Windows keeps openssl.exe; it's often not on PATH.
GIT_OPENSSL = (r"C:\Program Files\Git\mingw64\bin", r"C:\Program Files\Git\usr\bin")

FIXES = {
    "python": {"win32": "winget install Python.Python.3.12  (then open a new terminal)",
               "darwin": "brew install python@3.12",
               "linux": "sudo apt install python3  (or your distro's Python 3.10+ package)"},
    "ffmpeg": {"win32": "winget install Gyan.FFmpeg  (then open a new terminal)",
               "darwin": "brew install ffmpeg",
               "linux": "sudo apt install ffmpeg"},
    "openssl": {"win32": "winget install Git.Git  (Git for Windows ships openssl), then add "
                         r"C:\Program Files\Git\mingw64\bin to your PATH",
                "darwin": "brew install openssl",
                "linux": "sudo apt install openssl"},
    "ots": {"any": "pipx inject --include-apps indieward opentimestamps-client  (or: pip install opentimestamps-client)"},
    "mcp": {"any": "pipx install --force \"indieward[mcp]\"  (or: pip install \"indieward[mcp]\")"},
    "trustmark": {"any": "pipx inject indieward trustmark  (or: pip install \"indieward[trustmark]\"; pulls in PyTorch)"},
}


def _platform() -> str:
    return "win32" if sys.platform.startswith("win") else "darwin" if sys.platform == "darwin" else "linux"


def _fix(name: str) -> str:
    f = FIXES[name]
    return f.get("any") or f[_platform()]


def _item(name, ok, detail, needed=True, fix=None) -> dict:
    return {"name": name, "ok": ok, "needed": needed, "detail": detail,
            "fix": None if ok else (fix or _fix(name))}


def check_python() -> dict:
    v = sys.version_info
    return _item("python", v >= (3, 10), f"Python {v.major}.{v.minor}.{v.micro} at {sys.executable}")


def check_ffmpeg() -> list[dict]:
    out = []
    for tool in ("ffmpeg", "ffprobe"):
        p = shutil.which(tool)
        out.append(_item(tool, bool(p), p or "not found (needed for audio and video)", fix=_fix("ffmpeg")))
    return out


def check_openssl() -> dict:
    p = shutil.which("openssl")
    if not p:
        if _platform() == "win32":
            for d in GIT_OPENSSL:
                if Path(d, "openssl.exe").exists():
                    return _item("openssl", False, f"found in {d} but that folder isn't on PATH",
                                 fix=f"add {d} to your PATH, then open a new terminal")
        return _item("openssl", False, "not found (needed for RFC 3161 timestamps)")
    with tempfile.TemporaryDirectory() as td:
        try:
            r = subprocess.run([p, "ts", "-query", "-digest", "00" * 32, "-sha256", "-cert",
                                "-out", str(Path(td) / "q.tsq")], capture_output=True, text=True, timeout=30)
            ok = r.returncode == 0
        except (OSError, subprocess.SubprocessError):
            ok = False
    if ok:
        return _item("openssl", True, f"{p} (ts supported)")
    return _item("openssl", False, f"{p} can't build timestamp requests (`openssl ts` failed)")


def check_ots() -> dict:
    p = shutil.which("ots")
    return _item("ots", bool(p), p or "not found (optional: upgrades OpenTimestamps proofs)", needed=False)


def check_mcp() -> dict:
    ok = importlib.util.find_spec("mcp") is not None
    return _item("mcp", ok, "installed" if ok else "not installed (optional: the Claude plugin needs it)",
                 needed=False)


def check_trustmark() -> dict:
    """Optional image backend. Looks for the package and its model files without importing PyTorch."""
    from .wm_trustmark import MODEL_TYPE

    spec = importlib.util.find_spec("trustmark")
    if spec is None:
        return _item("trustmark", False, "not installed (optional: `register --backend trustmark`)", needed=False)
    locs = list(getattr(spec, "submodule_search_locations", None) or [])
    models = Path(locs[0], "models") if locs else None
    have = models is not None and all((models / f"{part}_{MODEL_TYPE}.ckpt").is_file() for part in ("encoder", "decoder"))
    detail = ("installed, models downloaded" if have else
              "installed; models download once from cai-watermark.adobe.net on first use")
    return _item("trustmark", True, detail, needed=False)


def check_vault(project=".") -> dict:
    root = Path(project).resolve()
    vault = next((c / VAULT_DIR for c in (root, *root.parents) if (c / VAULT_DIR / "vault.db").exists()), None)
    target = vault or root
    what = f"vault {vault}" if vault else f"{root} (no vault yet; `indieward init` will create one here)"
    try:
        fd, tmp = tempfile.mkstemp(prefix=".iw_doctor_", dir=target)
        os.close(fd)
        os.remove(tmp)
        return _item("vault", True, f"{what} is writable")
    except OSError as e:
        return _item("vault", False, f"{what} is not writable ({e.strerror or e})",
                     fix="run IndieWard from a folder you own (not Program Files or a read-only drive), "
                         "or fix that folder's permissions")


def run(project=".") -> dict:
    checks = [check_python(), *check_ffmpeg(), check_openssl(), check_ots(), check_mcp(), check_trustmark(),
              check_vault(project)]
    return {"ok": all(c["ok"] for c in checks if c["needed"]), "platform": _platform(), "checks": checks}


def format_report(res: dict) -> str:
    lines = []
    for c in res["checks"]:
        tag = "ok  " if c["ok"] else ("FIX " if c["needed"] else "opt ")
        lines.append(f"{tag} {c['name']:<9} {c['detail']}")
        if c["fix"]:
            lines.append(f"     -> {c['fix']}")
    lines.append("")
    lines.append("Ready." if res["ok"] else "Fix the FIX lines above, then run `indieward doctor` again.")
    return "\n".join(lines)
