"""Claude Code / Cowork hook commands shipped with the IndieWard plugin.

``indieward-hook block-send``  (PreToolUse): tries to stop Claude from sending
a takedown or DMCA notice for you, by email, shell or browser form, and from
running ``--override-weak``. It's a best-effort guardrail, not a guarantee.
IndieWard's rule is that the creator reviews and sends notices from their own
account. Unrelated email is left alone.

``indieward-hook session-status`` (SessionStart): if the working folder has
an IndieWard vault, prints a short status line (verification, pending
timestamps, copyright-window deadline) for Claude's context.

Both read the hook's JSON from stdin and never touch the network.
"""
from __future__ import annotations

import json
import re
import sys

TAKEDOWN = re.compile(r"(?i)(dmca|takedown|copyright infringement|512\(c\)|trademark complaint|_draft\.eml|"
                      r"steamcommunity\.com/dmca|copyright_agent@|trademark_agent@|support@itch\.io)")
# Tools that only read, search or make drafts are fine even with notice text in them.
SAFE_TOOL = re.compile(r"(?i)(draft|read|get|search|list|find|fetch|query|screenshot|indieward)")
SHELL_TOOLS = {"Bash", "PowerShell"}
SHELL_SENDS = re.compile(r"(?i)\b(sendmail|smtplib|swaks|msmtp|mutt|mailx?|Send-MailMessage|curl|wget|"
                         r"Invoke-WebRequest|Invoke-RestMethod|python3?|py|node|deno|powershell|pwsh)\b")
OVERRIDE = re.compile(r"--override-weak")


def block_send(event: dict) -> tuple[int, str]:
    """Best effort, not a guarantee: a user can always disable the hook."""
    tool = event.get("tool_name", "")
    inp = event.get("tool_input", {}) or {}
    blob = json.dumps(inp, ensure_ascii=False)
    if tool in SHELL_TOOLS:
        cmd = str(inp.get("command", ""))
        if OVERRIDE.search(cmd):
            return 2, ("IndieWard: --override-weak is the creator's own decision, made at their keyboard. Don't run "
                       "it for them.")
        if TAKEDOWN.search(cmd) and SHELL_SENDS.search(cmd):
            return 2, ("IndieWard: takedown notices are never sent by Claude. Open the .eml draft in your mail app "
                       "and send it yourself after reviewing BEFORE_YOU_SEND.md.")
        return 0, ""
    if tool.startswith("mcp__") and TAKEDOWN.search(blob):
        action = tool.split("__")[-1]
        if not SAFE_TOOL.search(action):
            return 2, ("IndieWard: don't send, post or submit takedown notices (including filling store web "
                       "forms) for the user. Create a draft at most, then hand it to them to review and send.")
    return 0, ""


def session_status(event: dict) -> str:
    from .cli import status
    from .vault import VaultMissing, find_vault

    try:
        v = find_vault(event.get("cwd") or ".")
    except VaultMissing:
        return ""
    s = status(v)
    bits = [f"IndieWard vault for '{s['project']}':", "verified" if s["verified"] else "NOT verified",
            f"{s['assets']} assets, {s['builds']} builds"]
    if s["pending_timestamps"]:
        bits.append(f"{s['pending_timestamps']} pending timestamps (run retry_timestamps)")
    bits.append(s["copyright_window"])
    return " | ".join(bits)


def main(argv=None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    try:
        event = json.loads(sys.stdin.read() or "{}")
    except json.JSONDecodeError:
        event = {}
    if argv and argv[0] == "block-send":
        code, msg = block_send(event)
        if msg:
            print(msg, file=sys.stderr)
        return code
    if argv and argv[0] == "session-status":
        try:
            out = session_status(event)
        except Exception:
            out = ""
        if out:
            print(out)
        return 0
    print("usage: indieward-hook block-send|session-status", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
