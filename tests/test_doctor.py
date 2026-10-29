"""indieward doctor: monkeypatched tool lookups, no real installs."""
from __future__ import annotations

import asyncio

from indieward import doctor


def _names(rep, status):
    return {c["name"] for c in rep["checks"] if c["status"] == status}


def test_all_missing_gives_one_fix_each(monkeypatch, tmp_path):
    monkeypatch.setattr(doctor.shutil, "which", lambda n: None)
    monkeypatch.setattr(doctor, "_os", lambda: "windows")
    rep = doctor.run_doctor(tmp_path)
    assert not rep["ok"]
    assert {"ffmpeg", "ffprobe", "openssl"} <= _names(rep, "problem")
    assert "ots" in _names(rep, "optional")
    fixes = {c["name"]: c["fix"] for c in rep["checks"]}
    assert "winget install Gyan.FFmpeg" in fixes["ffmpeg"]
    assert "Git" in fixes["openssl"]
    assert all(c["fix"] for c in rep["checks"] if c["status"] != "ok")


def test_platform_specific_fixes(monkeypatch, tmp_path):
    monkeypatch.setattr(doctor.shutil, "which", lambda n: None)
    for osname, expect in (("macos", "brew install ffmpeg"), ("linux", "apt install ffmpeg")):
        monkeypatch.setattr(doctor, "_os", lambda o=osname: o)
        fix = next(c["fix"] for c in doctor.run_doctor(tmp_path)["checks"] if c["name"] == "ffmpeg")
        assert expect in fix


def test_all_present_is_ok(monkeypatch, tmp_path):
    monkeypatch.setattr(doctor.shutil, "which", lambda n: f"/fake/{n}")
    monkeypatch.setattr(doctor, "_openssl_has_ts", lambda p: True)
    rep = doctor.run_doctor(tmp_path)
    assert rep["ok"] and rep["problems"] == 0
    assert "All required checks passed" in doctor.format_report(rep)


def test_openssl_without_ts_is_a_problem(monkeypatch, tmp_path):
    monkeypatch.setattr(doctor.shutil, "which", lambda n: f"/fake/{n}")
    monkeypatch.setattr(doctor, "_openssl_has_ts", lambda p: False)
    assert "openssl" in _names(doctor.run_doctor(tmp_path), "problem")


def test_old_python_is_a_problem(monkeypatch, tmp_path):
    monkeypatch.setattr(doctor, "MIN_PYTHON", (99, 0))
    assert "python" in _names(doctor.run_doctor(tmp_path), "problem")


def test_cli_exit_code(monkeypatch, capsys):
    from indieward import cli

    monkeypatch.setattr(doctor.shutil, "which", lambda n: None)
    assert cli.main(["doctor"]) == 1
    assert "fix:" in capsys.readouterr().out


def test_mcp_doctor_tool(monkeypatch, tmp_path):
    from indieward.mcp_server import mcp

    monkeypatch.setattr(doctor.shutil, "which", lambda n: None)
    res = asyncio.run(mcp.call_tool("doctor", {"project_dir": str(tmp_path)}))
    assert "ffmpeg" in str(res)
