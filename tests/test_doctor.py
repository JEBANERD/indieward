"""`indieward doctor`: one check per tool, one fix per problem, nothing installed."""
from __future__ import annotations

import asyncio
import collections
import json
import sys
from types import SimpleNamespace

import pytest

from indieward import cli, doctor


def _env(monkeypatch, missing=(), platform="linux", ts_ok=True, mcp=True):
    monkeypatch.setattr(doctor.shutil, "which", lambda n: None if n in missing else f"/bin/{n}")
    monkeypatch.setattr(doctor, "_platform", lambda: platform)
    monkeypatch.setattr(doctor.subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=0 if ts_ok else 1))
    monkeypatch.setattr(doctor.importlib.util, "find_spec", lambda n: object() if mcp else None)


def _by_name(res):
    return {c["name"]: c for c in res["checks"]}


def test_all_present_is_ready(tmp_path, monkeypatch):
    _env(monkeypatch)
    res = doctor.run(tmp_path)
    assert res["ok"]
    assert all(c["fix"] is None for c in res["checks"])
    assert "Ready." in doctor.format_report(res)


@pytest.mark.parametrize("platform, fix", [("win32", "winget install Gyan.FFmpeg"),
                                           ("darwin", "brew install ffmpeg"),
                                           ("linux", "sudo apt install ffmpeg")])
def test_missing_ffmpeg_gets_platform_fix(tmp_path, monkeypatch, platform, fix):
    _env(monkeypatch, missing=("ffmpeg", "ffprobe"), platform=platform)
    res = doctor.run(tmp_path)
    assert not res["ok"]
    c = _by_name(res)
    assert fix in c["ffmpeg"]["fix"] and fix in c["ffprobe"]["fix"]
    report = doctor.format_report(res)
    assert "FIX  ffmpeg" in report and fix in report


def test_windows_openssl_in_git_but_not_on_path(tmp_path, monkeypatch):
    _env(monkeypatch, missing=("openssl",), platform="win32")
    (tmp_path / "openssl.exe").write_bytes(b"")
    monkeypatch.setattr(doctor, "GIT_OPENSSL", (str(tmp_path),))
    c = _by_name(doctor.run(tmp_path))["openssl"]
    assert not c["ok"] and "isn't on PATH" in c["detail"] and str(tmp_path) in c["fix"]


def test_windows_openssl_missing_points_to_git(tmp_path, monkeypatch):
    _env(monkeypatch, missing=("openssl",), platform="win32")
    monkeypatch.setattr(doctor, "GIT_OPENSSL", (str(tmp_path / "nope"),))
    assert "winget install Git.Git" in _by_name(doctor.run(tmp_path))["openssl"]["fix"]


def test_openssl_without_ts_is_a_problem(tmp_path, monkeypatch):
    _env(monkeypatch, ts_ok=False)
    res = doctor.run(tmp_path)
    assert not res["ok"] and "openssl ts" in _by_name(res)["openssl"]["detail"]


def test_optional_tools_dont_block(tmp_path, monkeypatch):
    _env(monkeypatch, missing=("ots",), mcp=False)
    res = doctor.run(tmp_path)
    c = _by_name(res)
    assert res["ok"]
    assert not c["ots"]["ok"] and "opentimestamps-client" in c["ots"]["fix"]
    assert not c["mcp"]["ok"] and "indieward[mcp]" in c["mcp"]["fix"]
    assert "opt  ots" in doctor.format_report(res)


def test_old_python(tmp_path, monkeypatch):
    _env(monkeypatch, platform="win32")
    V = collections.namedtuple("V", "major minor micro")
    monkeypatch.setattr(sys, "version_info", V(3, 9, 7))
    c = _by_name(doctor.run(tmp_path))["python"]
    assert not c["ok"] and "winget install Python.Python.3.12" in c["fix"]


def test_unwritable_vault_folder(tmp_path, monkeypatch):
    _env(monkeypatch)

    def deny(**kw):
        raise PermissionError(13, "Permission denied")
    monkeypatch.setattr(doctor.tempfile, "mkstemp", deny)
    res = doctor.run(tmp_path)
    assert not res["ok"] and "not writable" in _by_name(res)["vault"]["detail"]


def test_finds_vault_above_project(tmp_path, monkeypatch):
    from indieward.vault import Vault

    _env(monkeypatch)
    Vault.init(tmp_path, "Game", "Someone")
    sub = tmp_path / "art"
    sub.mkdir()
    assert ".indieward" in _by_name(doctor.run(sub))["vault"]["detail"]


def test_cli_exit_code_and_json(tmp_path, monkeypatch, capsys):
    _env(monkeypatch)
    assert cli.main(["-C", str(tmp_path), "doctor"]) == 0
    _env(monkeypatch, missing=("ffmpeg",))
    assert cli.main(["--json", "-C", str(tmp_path), "doctor"]) == 1
    out = capsys.readouterr().out
    assert json.loads(out[out.index("{"):])["ok"] is False


def test_mcp_doctor_tool(tmp_path):
    from indieward.mcp_server import mcp

    assert "doctor" in {t.name for t in asyncio.run(mcp.list_tools())}
    res = asyncio.run(mcp.call_tool("doctor", {"project_dir": str(tmp_path)}))
    text = str(res)
    assert "checks" in text and "platform" in text


def test_doctor_never_installs(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(doctor.subprocess, "run", lambda cmd, **k: calls.append(cmd) or SimpleNamespace(returncode=0))
    doctor.run(tmp_path)
    assert all(c[1:2] == ["ts"] for c in calls)  # the only command run is the `openssl ts` probe
