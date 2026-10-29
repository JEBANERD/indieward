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
    for s in (ROOT / "plugin" / "skills").glob("*/SKILL.md"):
        head = s.read_text().split("---")[1]
        assert "name:" in head and "description:" in head
