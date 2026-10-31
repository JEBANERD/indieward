"""Release workflow guardrails (P3-02): publish only from v* tags, PyPI gated, versions and changelog checked."""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("release_notes", ROOT / "scripts" / "release_notes.py")
rn = importlib.util.module_from_spec(spec)
sys.modules["release_notes"] = rn
spec.loader.exec_module(rn)
WF = yaml.safe_load((ROOT / ".github" / "workflows" / "release.yml").read_text("utf-8"))
TAG_ONLY = "github.event_name == 'push' && startsWith(github.ref, 'refs/tags/v')"


def test_triggers_are_tags_and_manual_only():
    on = WF.get("on", WF.get(True))  # PyYAML reads a bare `on:` key as True
    assert set(on) == {"push", "workflow_dispatch"}
    assert on["push"] == {"tags": ["v*"]}  # no branches: a branch push never runs this workflow
    assert WF["permissions"] == {"contents": "read"}


def test_release_and_publish_only_from_a_pushed_tag():
    jobs = WF["jobs"]
    assert "if" not in jobs["build"]  # the dry run builds and tests everywhere
    assert "permissions" not in jobs["build"]  # read-only, from the top level
    for name in ("github-release", "pypi"):
        assert jobs[name]["if"].startswith(TAG_ONLY), name
    assert "vars.PYPI_PUBLISH == 'true'" in jobs["pypi"]["if"]
    assert jobs["pypi"]["needs"] == "github-release" and jobs["github-release"]["needs"] == "build"


def test_publish_uses_trusted_publishing_and_signing():
    jobs = WF["jobs"]
    pypi = jobs["pypi"]
    assert pypi["permissions"] == {"id-token": "write"}
    publish = next(s for s in pypi["steps"] if "pypa/gh-action-pypi-publish" in s.get("uses", ""))
    assert "with" not in publish or not {"password", "user"} & set(publish["with"])  # no stored token
    rel_steps = " ".join(str(s) for s in jobs["github-release"]["steps"])
    assert "actions/attest-build-provenance" in rel_steps and "--verify-tag" in rel_steps
    assert "cdx.json" in " ".join(str(s) for s in jobs["build"]["steps"])


def test_version_agrees_everywhere():
    py = re.search(r'(?m)^version\s*=\s*"([^"]+)"', (ROOT / "pyproject.toml").read_text()).group(1)
    assert rn.version() == py


def test_changelog_section():
    text = "# Changelog\n\n## [Unreleased]\n\n## [0.2.0] - 2026-11-01\n### Added\n- Thing.\n\n## [0.1.0]\n- Old.\n"
    assert rn.section("0.2.0", text) == "### Added\n- Thing.\n"
    assert rn.section("0.1.0", text) == "- Old.\n"
    with pytest.raises(SystemExit, match="no '## \\[0.3.0\\]'"):
        rn.section("0.3.0", text)
    with pytest.raises(SystemExit):
        rn.section("1.0.0", "## [1.0.0]\n\n## [0.9.0]\n- x\n")  # an empty section is refused too


def test_changelog_has_unreleased_and_release_steps():
    text = (ROOT / "CHANGELOG.md").read_text("utf-8")
    assert "## [Unreleased]" in text and "git tag v" in text
