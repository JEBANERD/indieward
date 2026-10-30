"""UE5: a Shipping-style folder (exe with UTF-16 TEXT() literals, encrypted pak) passes the trap check."""
from __future__ import annotations

import os
import re
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "engines"))
from helpers import verified_vault  # noqa: E402

from indieward import registry, traps  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def _fake_shipping_build(v, build_id: str, dest: Path) -> None:
    """What MSVC leaves of the generated .cpp: wide string literals and the doubles, no symbol names."""
    cpp = next(v.path("traps", build_id, "Source").glob("*.cpp")).read_text()
    lits = re.findall(r'TEXT\("([^"]+)"\)', cpp)
    nums = [float(x) for x in re.findall(r"volatile double \w+ = ([-0-9.e]+);", cpp)]
    assert len(lits) == 4 and len(nums) == 2
    blob = os.urandom(4096)
    for s in lits:
        blob += (s + "\0").encode("utf-16-le") + os.urandom(64)
    for f in nums:
        blob += struct.pack("<d", f) + os.urandom(32)
    win = dest / "Windows" / "MyGame" / "Binaries" / "Win64"
    win.mkdir(parents=True)
    (win / "MyGame-Win64-Shipping.exe").write_bytes(b"MZ" + blob)
    paks = dest / "Windows" / "MyGame" / "Content" / "Paks"
    paks.mkdir(parents=True)
    (paks / "MyGame-Windows.pak").write_bytes(os.urandom(8192))  # encrypted: unreadable


def test_ue5_shipping_exe_is_enough(tmp_path, monkeypatch):
    v = verified_vault(tmp_path / "vault", monkeypatch)
    t = traps.generate(v, "ue5 test", "ue5")
    build = tmp_path / "archive"
    _fake_shipping_build(v, t["build_id"], build)
    res = registry.register_build(v, t["build_id"], build)
    assert res["ok"], res
    missing = {m["label"] for m in res["missing"]}
    assert missing <= {"dead_function", "hidden_asset", "hidden_asset_hash"}


def test_ue5_check_script_is_local_and_gated():
    ps = (ROOT / "scripts" / "ue5_check.ps1").read_text()
    for bad in ("Invoke-WebRequest", "Invoke-RestMethod", "WebClient", "Send-MailMessage", "Net.Http", "Start-BitsTransfer"):
        assert bad not in ps
    # a verified store link is checked before anything is copied in or packaged
    gate0 = ps.index('"status")')
    assert "if (-not $st.verified)" in ps
    assert gate0 < ps.index("Copy-Item") and gate0 < ps.index("& $RunUAT")
    # the only write into the project is the guarded copy
    assert ps.count("Copy-Item") == 1
    gate = ps.index("if (-not $Apply)")
    assert gate < ps.index("Copy-Item")
    for word in ("BuildCookRun", "build\", \"register", "-clientconfig=$Config"):
        assert word in ps
    assert (ROOT / "docs" / "engines" / "ue5.md").exists()
