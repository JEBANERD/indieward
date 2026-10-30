"""Plugin pieces: MCP server tools, guardrail hooks, manifests."""
from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_mcp_server_has_no_send_or_override_tool():
    from indieward.mcp_server import mcp

    tools = asyncio.run(mcp.list_tools())
    names = {t.name for t in tools}
    assert {"check_suspect", "build_takedown_package", "register_assets", "verify_store_page"} <= names
    assert not any(w in n for n in names for w in ("send", "submit", "email", "file_notice"))
    pkg = next(t for t in tools if t.name == "build_takedown_package")
    schema = getattr(pkg, "inputSchema", None) or getattr(pkg, "input_schema")
    assert "override_weak" not in json.dumps(schema)


def test_mcp_tool_refuses_unverified(tmp_path):
    from indieward.mcp_server import mcp
    from indieward.vault import Vault

    Vault.init(tmp_path, "Game", "Someone")
    res = asyncio.run(mcp.call_tool("register_assets", {"project_dir": str(tmp_path), "paths": [str(tmp_path)]}))
    text = json.dumps(res, default=str)
    assert "NotVerified" in text


def _hook(args, event):
    p = subprocess.run([sys.executable, "-m", "indieward.hooks", *args], input=json.dumps(event),
                       capture_output=True, text=True, cwd=ROOT, env={"PYTHONPATH": str(ROOT / "src")})
    return p.returncode, p.stdout, p.stderr


def test_hook_blocks_sending_takedown_email():
    code, _, err = _hook(["block-send"], {"tool_name": "mcp__Gmail__send_message",
                                          "tool_input": {"to": "support@itch.io", "subject": "DMCA notice: Lantern Moth"}})
    assert code == 2 and ("never sent" in err or "don't send" in err)
    code, _, _ = _hook(["block-send"], {"tool_name": "Bash",
                                        "tool_input": {"command": "swaks --to support@itch.io --attach itch_copyright_draft.eml"}})
    assert code == 2


def test_hook_blocks_browser_forms_and_override():
    assert _hook(["block-send"], {"tool_name": "mcp__claude-in-chrome__form_input",
                                  "tool_input": {"value": "notice of copyright infringement"}})[0] == 2
    assert _hook(["block-send"], {"tool_name": "PowerShell",
                                  "tool_input": {"command": "Send-MailMessage -To support@itch.io"}})[0] == 2
    assert _hook(["block-send"], {"tool_name": "Bash",
                                  "tool_input": {"command": "indieward package --check c1 --override-weak"}})[0] == 2


def test_hook_allows_drafts_and_unrelated_email():
    assert _hook(["block-send"], {"tool_name": "mcp__Gmail__create_draft",
                                  "tool_input": {"subject": "DMCA notice"}})[0] == 0
    assert _hook(["block-send"], {"tool_name": "mcp__Gmail__send_message",
                                  "tool_input": {"subject": "Lunch on Friday?"}})[0] == 0
    assert _hook(["block-send"], {"tool_name": "Bash", "tool_input": {"command": "ls -la"}})[0] == 0


def test_session_hook_quiet_outside_vault(tmp_path):
    code, out, _ = _hook(["session-status"], {"cwd": str(tmp_path)})
    assert code == 0 and out == ""


def test_manifests_valid_json():
    for f in (ROOT / ".claude-plugin" / "marketplace.json", ROOT / "plugin" / ".claude-plugin" / "plugin.json",
              ROOT / "plugin" / ".mcp.json", ROOT / "plugin" / "hooks" / "hooks.json"):
        json.loads(f.read_text())
    hooks = (ROOT / "plugin" / "hooks" / "hooks.json").read_text()
    assert "indieward-hook protect-vault" in hooks
    for s in (ROOT / "plugin" / "skills").glob("*/SKILL.md"):
        head = s.read_text().split("---")[1]
        assert "name:" in head and "description:" in head


@pytest.mark.parametrize("tool,cmd", [
    ("Bash", "rm -rf .indieward/keys"),
    ("Bash", "rm .indieward/vault.db"),
    ("Bash", "rm -rf .indieward"),
    ("Bash", "git clean -n && rm -rf ./.indieward/"),
    ("Bash", "cd game/.indieward && rm -rf certs"),
    ("Bash", "find .indieward/certs -name '*.json' -delete"),
    ("Bash", "ls .indieward/keys/* | xargs rm"),
    ("Bash", "mv .indieward/keys /tmp/old"),
    ("Bash", "echo junk > .indieward/keys/mac.key"),
    ("Bash", "cp other.db .indieward/vault.db"),
    ("Bash", "cp -t .indieward/keys replacement.pem"),
    ("Bash", "cp --target-directory=.indieward/keys replacement.pem"),
    ("Bash", "cd .indieward && printf junk > vault.db"),
    ("PowerShell", "Copy-Item -Destination .indieward\\keys\\signing.pem -Path new.pem"),
    ("Bash", "sqlite3 .indieward/vault.db 'DELETE FROM checks'"),
    ("Bash", "sed -i 's/a/b/' .indieward/certs/cert.json"),
    ("Bash", "bash -c \"rm -f .indieward/vault.db-wal\""),
    ("Bash", "python -c \"import shutil; shutil.rmtree('.indieward/keys')\""),
    ("PowerShell", "del .indieward\\vault.db"),
    ("PowerShell", "Remove-Item -Recurse -Force .indieward\\keys"),
    ("PowerShell", "Remove-Item C:\\Games\\Moth\\.indieward -Recurse"),
    ("PowerShell", "Set-Content -Path .indieward\\certs\\cert.json -Value '{}'"),
    ("PowerShell", "cmd /c rd /s /q .indieward\\certs"),
])
def test_vault_hook_blocks_shell_changes(tool, cmd):
    code, _, err = _hook(["protect-vault"], {"tool_name": tool, "tool_input": {"command": cmd}})
    assert code == 2 and "vault" in err


@pytest.mark.parametrize("tool,path", [
    ("Edit", "/home/me/game/.indieward/vault.db"),
    ("Write", ".indieward/keys/signing.pem"),
    ("Write", "C:\\Games\\Moth\\.indieward\\certs\\cert_1.json"),
    ("MultiEdit", "game/.indieward/certs/cert_1.json"),
])
def test_vault_hook_blocks_edit_and_write(tool, path):
    assert _hook(["protect-vault"], {"tool_name": tool, "tool_input": {"file_path": path}})[0] == 2


@pytest.mark.parametrize("tool,inp", [
    ("Bash", {"command": "cat .indieward/certs/cert_1.json"}),
    ("Bash", {"command": "ls -la .indieward/keys"}),
    ("Bash", {"command": "sqlite3 .indieward/vault.db 'SELECT * FROM checks'"}),
    ("Bash", {"command": "cp .indieward/keys/signing.pem ~/backup/"}),
    ("Bash", {"command": "cd .indieward && cat vault.db > ~/backup/vault.db"}),
    ("Bash", {"command": "rm -rf build/ && rm notes.txt"}),
    ("Bash", {"command": "rm .indieward/packages/old.zip"}),
    ("Bash", {"command": "indieward register --paths art/"}),
    ("PowerShell", {"command": "Get-Content .indieward\\certs\\cert_1.json"}),
    ("PowerShell", {"command": "Remove-Item .\\Temp -Recurse"}),
    ("Edit", {"file_path": "/home/me/game/src/player.gd"}),
    ("Write", {"file_path": ".indieward-notes.md"}),
    ("Write", {"file_path": "docs/keys/readme.md"}),
    ("Read", {"file_path": ".indieward/vault.db"}),
    ("mcp__indieward__register_assets", {"project_dir": ".", "paths": [".indieward/keys"]}),
])
def test_vault_hook_allows_reads_own_tools_and_other_edits(tool, inp):
    assert _hook(["protect-vault"], {"tool_name": tool, "tool_input": inp})[0] == 0


@pytest.fixture
def repo_with_vault(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / "game" / ".indieward").mkdir(parents=True)
    return tmp_path


@pytest.mark.parametrize("tool,cmd", [
    ("Bash", "git clean -fdx"),
    ("Bash", "git clean -xdf"),
    ("Bash", "git clean -fdX"),
    ("Bash", "git clean -f -d -x"),
    ("Bash", "git stash --all"),
    ("Bash", "git stash push -a"),
    ("Bash", "git stash save --all 'wip'"),
    ("Bash", "git -C game clean -fdx"),
    ("Bash", "npm run build && git clean -fdx"),
    ("Bash", "git clean -fdX -e .indieward"),  # with -X, -e adds an ignore rule: still wipes the vault
    ("PowerShell", "git clean -fdx"),
    ("PowerShell", "git.exe clean -xfd"),
])
def test_vault_hook_blocks_git_wiping_ignored_files(repo_with_vault, tool, cmd):
    code, _, err = _hook(["protect-vault"], {"tool_name": tool, "tool_input": {"command": cmd},
                                              "cwd": str(repo_with_vault)})
    assert code == 2 and "gitignored" in err


@pytest.mark.parametrize("cmd", [
    "git clean -fd",
    "git clean -ndx",
    "git clean -fdx --dry-run",
    "git clean -fdx -e .indieward",
    "git clean -fdx --exclude=.indieward/",
    "git stash",
    "git stash -u",
    "git stash push -m 'fix -a flag'",
    "git stash list",
    "git status --ignored",
    "git log --all",
])
def test_vault_hook_allows_safe_git(repo_with_vault, cmd):
    assert _hook(["protect-vault"], {"tool_name": "Bash", "tool_input": {"command": cmd},
                                     "cwd": str(repo_with_vault)})[0] == 0


def test_vault_hook_git_clean_fine_without_a_vault(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / "src").mkdir()
    assert _hook(["protect-vault"], {"tool_name": "Bash", "tool_input": {"command": "git clean -fdx"},
                                     "cwd": str(tmp_path)})[0] == 0


def test_vault_hook_git_clean_from_subfolder_sees_vault_elsewhere_in_repo(repo_with_vault):
    sub = repo_with_vault / "tools"
    sub.mkdir()
    assert _hook(["protect-vault"], {"tool_name": "Bash", "tool_input": {"command": "git clean -fdx"},
                                     "cwd": str(sub)})[0] == 2
