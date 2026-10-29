"""indieward doctor: tool checks with monkeypatched shutil.which; prints fixes, installs nothing."""
import asyncio
import subprocess

from indieward import cli, doctor


def _which(present):
    return lambda name: f"/fake/{name}" if name in present else None


def _patch(monkeypatch, present, plat="linux", ts=True):
    monkeypatch.setattr(doctor.shutil, "which", _which(present))
    monkeypatch.setattr(doctor, "_platform", lambda: plat)
    monkeypatch.setattr(doctor, "_openssl_ts", lambda path: ts)


def _by_name(rep):
    return {c["name"]: c for c in rep["checks"]}


def test_all_present(monkeypatch, tmp_path):
    _patch(monkeypatch, {"ffmpeg", "ffprobe", "openssl", "ots"})
    rep = doctor.run_doctor(str(tmp_path))
    assert rep["ok"] and not any(c["fix"] for c in rep["checks"] if c["name"] in ("ffmpeg", "openssl", "ots"))


def test_missing_tools_give_platform_fixes(monkeypatch, tmp_path):
    _patch(monkeypatch, set(), plat="windows")
    rep = doctor.run_doctor(str(tmp_path))
    c = _by_name(rep)
    assert not rep["ok"]
    assert "winget install Gyan.FFmpeg" in c["ffmpeg"]["fix"]
    assert "Git" in c["openssl"]["fix"]
    assert not c["ots"]["ok"] and not c["ots"]["required"]
    _patch(monkeypatch, set(), plat="macos")
    assert "brew install ffmpeg" in _by_name(doctor.run_doctor(str(tmp_path)))["ffmpeg"]["fix"]
    _patch(monkeypatch, set(), plat="linux")
    assert "apt install ffmpeg" in _by_name(doctor.run_doctor(str(tmp_path)))["ffmpeg"]["fix"]


def test_openssl_without_ts_fails(monkeypatch, tmp_path):
    _patch(monkeypatch, {"ffmpeg", "ffprobe", "openssl"}, ts=False)
    rep = doctor.run_doctor(str(tmp_path))
    assert not rep["ok"] and not _by_name(rep)["openssl"]["ok"]


def test_optional_missing_still_ok(monkeypatch, tmp_path):
    _patch(monkeypatch, {"ffmpeg", "ffprobe", "openssl"})
    assert doctor.run_doctor(str(tmp_path))["ok"]


def test_unwritable_folder(monkeypatch, tmp_path):
    _patch(monkeypatch, {"ffmpeg", "ffprobe", "openssl"})
    def boom(*a, **k):
        raise PermissionError("denied")
    monkeypatch.setattr(doctor.tempfile, "NamedTemporaryFile", boom)
    rep = doctor.run_doctor(str(tmp_path))
    assert not rep["ok"] and not _by_name(rep)["vault-write"]["ok"]


def test_doctor_creates_no_vault_and_runs_nothing_to_install(monkeypatch, tmp_path):
    _patch(monkeypatch, set())
    def no_run(*a, **k):
        raise AssertionError("doctor must not run commands")
    monkeypatch.setattr(subprocess, "run", no_run)
    doctor.run_doctor(str(tmp_path))
    assert not (tmp_path / ".indieward").exists() and list(tmp_path.iterdir()) == []


def test_cli_exit_codes_and_json(monkeypatch, tmp_path, capsys):
    _patch(monkeypatch, set())
    assert cli.main(["-C", str(tmp_path), "--json", "doctor"]) == 1
    assert '"fixes"' in capsys.readouterr().out
    _patch(monkeypatch, {"ffmpeg", "ffprobe", "openssl"})
    assert cli.main(["-C", str(tmp_path), "doctor"]) == 0
    assert "All required checks passed" in capsys.readouterr().out


def test_mcp_doctor_tool(monkeypatch, tmp_path):
    from indieward.mcp_server import mcp
    _patch(monkeypatch, {"ffmpeg", "ffprobe", "openssl"})
    names = {t.name for t in asyncio.run(mcp.list_tools())}
    assert "doctor" in names
    res = asyncio.run(mcp.call_tool("doctor", {"project_dir": str(tmp_path)}))
    assert "platform" in str(res)
