"""Claude Code / Cowork hook commands shipped with the IndieWard plugin.

``indieward-hook block-send``  (PreToolUse): tries to stop Claude from sending
a takedown or DMCA notice for you, by email, shell or browser form, and from
running ``--override-weak``. It's a best-effort guardrail, not a guarantee.
IndieWard's rule is that the creator reviews and sends notices from their own
account. Unrelated email is left alone.

``indieward-hook protect-vault`` (PreToolUse): tries to stop Claude from editing,
moving or deleting the vault's evidence (``.indieward/keys``, ``.indieward/vault.db``,
``.indieward/certs``, or the whole ``.indieward`` folder) with Edit, Write or a
shell command, and from ``git clean -x``/``-X`` or ``git stash --all``, which
remove gitignored files and so the whole vault. Reading is allowed, and IndieWard's own MCP tools and CLI still
write there. Also best effort: it matches paths in commands, so a script that
builds the path itself can slip past it.

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


# The vault's evidence: keys, the database (plus its -journal/-wal files), certificates, or the folder itself.
VAULT_PATH = re.compile(r"(?i)\.indieward(?:[\\/]+(?:keys|certs|vault\.db)\b|[\\/]*\*?(?=$|[\s'\"`;|&),]))")
EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
SEGMENT = re.compile(r"&&|\|\||[;|\n]")
# Wrappers stripped from the front of each command: sudo, quotes, `bash -c`, `cmd /c`, `powershell -Command`.
WRAPPER = re.compile(r"(?i)^(?:sudo\s+|['\"(]\s*|(?:bash|sh|zsh|cmd|pwsh|powershell)(?:\.exe)?\s+(?:-\w+\s+)*?"
                     r"(?:-c|/c|-command)\s+)*")
# Commands that delete, move or rewrite whatever path they're given.
SHELL_MODIFY = re.compile(r"(?i)^(?:git\s+)?(?:rm|rmdir|unlink|shred|truncate|del|erase|rd|mv|move|ren|rename|"
                          r"remove-item|ri|move-item|mi|rename-item|rni|clear-content|clc|set-content|sc|"
                          r"add-content|ac|out-file|new-item|ni|chmod|chown|icacls|attrib|ln|touch)\b|"
                          r"^(?:sed|perl|ruby)\b.*\s-[a-z]*i|^find\b.*\s(?:-delete|-exec\s+(?:rm|shred|mv)\b)")
# Copying out of the vault is a backup (fine); copying onto it overwrites evidence.
SHELL_COPY = re.compile(r"(?i)^(?:cp|copy|xcopy|robocopy|copy-item|cpi|rsync|install)\b")
REDIRECT = re.compile(r"(?i)(?:>>?|\btee\b(?:\s+-a)?|\bof=)\s*['\"]?([^\s'\";|&]+)")
XARGS_MODIFY = re.compile(r"(?i)\bxargs\s+(?:-\S+\s+)*(?:rm|shred|unlink|mv)\b")
SQL_WRITE = re.compile(r"(?i)\b(insert|update|delete|drop|alter|create|replace|vacuum|attach)\b")
SCRIPT_WRITE = re.compile(r"(?i)(unlink|remove|rmtree|rmdir|rename|replace|truncate|write|['\"][wa]\+?b?['\"]|"
                          r"rimraf|fs\.rm)")
CD_VAULT = re.compile(r"(?i)^(?:cd|pushd|set-location|sl|chdir)\s+['\"]?\S*\.indieward[\\/]*['\"]?$")
# Once a command has cd'd into .indieward, bare names count too.
INSIDE_TARGET = re.compile(r"(?i)^(?:\.[\\/])?(?:keys|certs|vault\.db)\b")
INSIDE_PATH = re.compile(r"(?i)(?:^|[\s'\"\\/])(?:keys|certs|vault\.db)\b|(?:^|\s)(?:\*|\.)(?=$|\s)")
VAULT_MSG = ("IndieWard: the vault (.indieward keys, vault.db, certs) is your evidence, so Claude doesn't edit, move or "
             "delete it. Use IndieWard's own tools to change it, or do it yourself if you really mean to.")
GIT_WIPE_MSG = ("IndieWard: .indieward/ is gitignored, so `git clean -x`/`-X` or `git stash --all` would remove your vault "
                "(keys, vault.db, certs). Use `git clean -fd`, add `-e .indieward` to `-x`, or run it yourself.")


def _copy_destinations(args: list[str]) -> list[str]:
    """The last argument, plus any -t / --target-directory / -Destination value."""
    dests = [args[-1].strip("'\"")]
    for i, a in enumerate(args):
        low = a.lower()
        if low in ("-t", "--target-directory", "-destination") and i + 1 < len(args):
            dests.append(args[i + 1].strip("'\""))
        elif low.startswith(("--target-directory=", "-destination:")):
            dests.append(a.split("=", 1)[-1] if "=" in a else a.split(":", 1)[-1])
        elif low.startswith("-t") and len(a) > 2 and not low.startswith("-t-"):
            dests.append(a[2:])
    return dests


def _short_flags(args: list[str]) -> str:
    return "".join(a[1:] for a in args if a.startswith("-") and not a.startswith("--"))


def _wipes_ignored(seg: str) -> bool:
    """git clean -x/-X and git stash --all remove gitignored files, and .indieward/ is gitignored."""
    args = seg.split()
    if not args or args[0].lower() not in ("git", "git.exe"):
        return False
    i = 1
    while i < len(args) and args[i].startswith("-"):  # global options: -C <dir>, -c <key=value>
        i += 2 if args[i] in ("-C", "-c") else 1
    if i >= len(args):
        return False
    sub, rest = args[i], args[i + 1:]
    if sub == "clean":
        opts, excludes, j = [], [], 0
        while j < len(rest):
            a = rest[j]
            if a in ("-e", "--exclude") and j + 1 < len(rest):
                excludes.append(rest[j + 1])
                j += 1
            elif a.startswith("--exclude="):
                excludes.append(a.split("=", 1)[1])
            elif a.startswith("-e") and not a.startswith("--"):
                excludes.append(a[2:])
            elif a.startswith("-"):
                opts.append(a)
            j += 1
        flags = _short_flags(opts)
        if "n" in flags or "--dry-run" in opts:
            return False
        if "X" in flags:
            return True  # -e only adds ignore rules here, so it can't protect the vault
        return "x" in flags and not any(re.fullmatch(r"(?:\./|/)?\.indieward[\\/]?\*?", e.strip("'\"")) for e in excludes)
    if sub == "stash":
        if rest and not rest[0].startswith("-") and rest[0] not in ("push", "save"):
            return False  # list, show, apply, pop, drop, ...
        opts = [a for a in rest if a.startswith("-") and a not in ("-m", "--message")]
        return "--all" in opts or "a" in _short_flags(opts)
    return False


def _touches_vault(cmd: str) -> bool:
    if any(VAULT_PATH.search(m.group(1)) for m in REDIRECT.finditer(cmd)):
        return True
    if VAULT_PATH.search(cmd) and XARGS_MODIFY.search(cmd):
        return True
    # Script one-liners hold their own ; and quotes, so judge them whole.
    if (VAULT_PATH.search(cmd) and SCRIPT_WRITE.search(cmd)
            and re.search(r"(?i)(?:^|[;&|]\s*)(?:python3?|py|node|deno)\b", cmd)):
        return True
    inside = False
    for seg in SEGMENT.split(cmd):
        seg = WRAPPER.sub("", seg.strip())
        if CD_VAULT.match(seg):
            inside = True
            continue
        targets = [m.group(1) for m in REDIRECT.finditer(seg)]
        if any(VAULT_PATH.search(t) or (inside and INSIDE_TARGET.match(t)) for t in targets):
            return True
        args = seg.split()
        if not args or not (VAULT_PATH.search(seg) or (inside and INSIDE_PATH.search(" ".join(args[1:])))):
            continue
        if SHELL_MODIFY.search(seg):
            return True
        if SHELL_COPY.search(seg) and any(VAULT_PATH.search(d) or (inside and INSIDE_TARGET.match(d))
                                          for d in _copy_destinations(args)):
            return True
        if re.match(r"(?i)^sqlite3?\b", seg) and SQL_WRITE.search(seg):
            return True
    return False


def protect_vault(event: dict) -> tuple[int, str]:
    """Best effort, not a guarantee: a user can always disable the hook."""
    tool = event.get("tool_name", "")
    inp = event.get("tool_input", {}) or {}
    if tool in EDIT_TOOLS:
        path = str(inp.get("file_path") or inp.get("notebook_path") or "")
        return (2, VAULT_MSG) if VAULT_PATH.search(path) else (0, "")
    if tool in SHELL_TOOLS:
        cmd = str(inp.get("command", ""))
        if any(_wipes_ignored(WRAPPER.sub("", seg.strip())) for seg in SEGMENT.split(cmd)):
            return 2, GIT_WIPE_MSG
        return (2, VAULT_MSG) if _touches_vault(cmd) else (0, "")
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
    if argv and argv[0] in ("block-send", "protect-vault"):
        code, msg = (block_send if argv[0] == "block-send" else protect_vault)(event)
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
    print("usage: indieward-hook block-send|protect-vault|session-status", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
