"""Release checks (P3-02): tag/version/changelog agreement and the workflow's safety gates."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("release_notes", ROOT / "scripts" / "release_notes.py")
rn = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rn)

CHANGELOG = """# Changelog

## [Unreleased]
- next thing

## [1.2.0] - 2026-11-02
### Added
- a feature

## [1.1.0] - 2026-10-01
- older
"""


def _repo(tmp_path, version="1.2.0", changelog=CHANGELOG):
    (tmp_path / "pyproject.toml").write_text(f'[project]\nname = "x"\nversion = "{version}"\n', encoding="utf-8")
    (tmp_path / "CHANGELOG.md").write_text(changelog, encoding="utf-8")
    return tmp_path


def test_notes_are_just_that_versions_section(tmp_path):
    notes = rn.notes_for("v1.2.0", _repo(tmp_path))
    assert notes == "### Added\n- a feature"


@pytest.mark.parametrize("tag", ["1.2.0", "v1.2", "v1.1.0", "v1.2.0-rc1"])
def test_tag_must_match_pyproject(tmp_path, tag):
    with pytest.raises(ValueError, match="doesn't match"):
        rn.notes_for(tag, _repo(tmp_path))


def test_missing_or_empty_section_stops_the_release(tmp_path):
    with pytest.raises(ValueError, match=r"no entries under '## \[1.3.0\]'"):
        rn.notes_for("v1.3.0", _repo(tmp_path, version="1.3.0"))
    with pytest.raises(ValueError, match="no entries"):
        rn.notes_for("v1.2.0", _repo(tmp_path, changelog="## [1.2.0] - 2026-11-02\n\n## [1.1.0]\n- x\n"))


def test_cli_exit_codes(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(rn, "ROOT", _repo(tmp_path))
    assert rn.main(["v1.2.0"]) == 0 and "a feature" in capsys.readouterr().out
    assert rn.main(["v9.9.9"]) == 1 and "doesn't match" in capsys.readouterr().err
    assert rn.main([]) == 2


def test_this_repo_is_releasable_at_its_current_version():
    version = rn.project_version((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert rn.notes_for(f"v{version}")


def test_workflow_publishes_only_from_tags_and_only_when_enabled():
    wf = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    on = wf.split("\npermissions:")[0]
    assert 'tags: ["v*"]' in on and "branches" not in on  # no publishing from branch pushes
    release = wf.split("\n  release:")[1].split("\n  pypi:")[0]
    pypi = wf.split("\n  pypi:")[1]
    assert "if: github.ref_type == 'tag'" in release
    assert "if: github.ref_type == 'tag' && vars.PYPI_PUBLISH == 'true'" in pypi
    assert "environment:" in pypi and "name: pypi" in pypi
    assert "password" not in pypi and "secrets." not in wf  # trusted publishing, no stored token
    assert "actions/attest-build-provenance" in release and "cyclonedx-py" in wf
