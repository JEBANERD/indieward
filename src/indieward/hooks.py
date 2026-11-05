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
remove gitignored files and so the whole vault (only where the git repo around
the working folder holds a vault, or where that can't be told). Reading is allowed, and IndieWard's own MCP tools and CLI still
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
import shlex
import sys
from pathlib import Path

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
# `&&`, `||`, `;`, `|`, newline, and a single `&` (cmd.exe separator) that follows a command: not PowerShell's
# call operator at the start of a segment, and not part of `2>&1` or `&>`.
SEGMENT = re.compile(r"&&|\|\||(?<=[^\s&>])\s*&(?![>&])|[;|\n]")
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


# Commands that just run the next command: `env FOO=1 git ...`, `time git ...`. PowerShell's `&` is handled apart.
PREFIX_CMDS = {"env", "command", "builtin", "exec", "time", "nice", "nohup", "xargs"}
FIRST_WORD = re.compile(r"^(?:\"([^\"]*)\"|'([^']*)'|(\S+))\s*(.*)$", re.S)


def _program(word: str) -> str:
    """`C:\\Git\\cmd\\git.exe` and `/usr/bin/GIT` both become `git`."""
    base = re.split(r"[\\/]", word.strip())[-1].lower()
    return base[:-4] if base.endswith(".exe") else base


def _normalize(seg: str) -> str:
    """Strip a leading `&` and prefix commands, and reduce the program to its bare name (best effort)."""
    seg = WRAPPER.sub("", seg.strip())
    for _ in range(8):
        seg = seg.lstrip()
        if seg.startswith("&"):
            seg = seg[1:].lstrip()
            continue
        m = FIRST_WORD.match(seg)
        if not m:
            return seg
        word, rest = next(g for g in m.groups()[:3] if g is not None), m.group(4)
        prog = _program(word)
        if prog not in PREFIX_CMDS:
            return f"{prog} {rest}".strip() if prog else seg
        while True:  # options and, for env, VAR=value words belong to the prefix
            m2 = re.match(r"^(-\S+(?:\s+\d+)?|[A-Za-z_]\w*=\S*)\s*(.*)$", rest, re.S)
            if not m2 or (prog != "env" and not m2.group(1).startswith("-")):
                break
            rest = m2.group(2)
        seg = rest
    return seg


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


def _wipes_ignored(seg: str, root_vault_only: bool = False) -> bool:
    """git clean -x/-X and git stash --all remove gitignored files, and .indieward/ is gitignored.

    root_vault_only: the only vault is at the repo root, so an anchored `-e /.indieward` really protects it."""
    seg = _normalize(seg)
    try:
        args = shlex.split(seg)  # keep quoted paths with spaces whole: git -C "my game" clean -fdx
    except ValueError:
        args = seg.split()
    if not args or _program(args[0]) != "git":
        return False
    i, aliases = 1, {}
    while i < len(args) and args[i].startswith("-"):  # global options: -C <dir>, -c <key=value>
        if args[i] == "-c" and i + 1 < len(args):
            key, _, val = args[i + 1].partition("=")
            if key.lower().startswith("alias."):  # git -c alias.c=clean c -fdx
                aliases[key[6:].lower()] = val
        i += 2 if args[i] in ("-C", "-c") else 1
    if i >= len(args):
        return False
    sub, rest = args[i], args[i + 1:]
    if sub.lower() in aliases:  # only aliases defined inline; ones in git config are out of scope
        try:
            expanded = shlex.split(aliases[sub.lower()])
        except ValueError:
            expanded = aliases[sub.lower()].split()
        if not expanded or expanded[0].startswith("!"):
            return False
        sub, rest = expanded[0], expanded[1:] + rest
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
        dry = False
        for a in opts:  # last one wins: -n --no-dry-run really deletes
            if a == "--dry-run" or (not a.startswith("--") and "n" in a):
                dry = True
            elif a == "--no-dry-run":
                dry = False
        if dry:
            return False
        flags = _short_flags(opts)
        if "X" in flags:
            return True  # -e only adds ignore rules here, so it can't protect the vault
        if "x" not in flags:
            return False
        # `.indieward` matches at any depth; `/.indieward` or `./.indieward` only the repo root's.
        pattern = r"(?:\./|/)?\.indieward[\\/]?\*?" if root_vault_only else r"\.indieward[\\/]?\*?"
        return not any(re.fullmatch(pattern, e.strip("'\"")) for e in excludes)
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
        seg = _normalize(seg)
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


CHANGES_DIR = re.compile(r"(?i)(?:^|[\s;&|(])(?:cd|pushd|set-location|sl|chdir)\b|\bgit(?:\.exe)?\s+(?:\S+\s+)*?-C\b")
SKIP_DIRS = {".git", "node_modules", "Library", "Intermediate", "DerivedDataCache", "Saved", ".godot"}


def _vaults_in_repo(cwd):
    """(repo top, every .indieward found in the enclosing repo, up to 3 levels down), or None when cwd is unknown."""
    if not cwd or not Path(cwd).is_dir():
        return None
    start = Path(cwd).resolve()
    top = next((p for p in (start, *start.parents) if (p / ".git").exists()), start)
    found = [p / ".indieward" for p in (start, *start.parents)
             if (p == top or top in p.parents) and (p / ".indieward").is_dir()]
    stack = [(top, 0)]
    while stack:
        d, depth = stack.pop()
        try:
            subdirs = [e for e in d.iterdir() if e.is_dir() and not e.is_symlink()]
        except OSError:
            return None
        for e in subdirs:
            if e.name == ".indieward":
                found.append(e)
            elif depth < 3 and e.name not in SKIP_DIRS:
                stack.append((e, depth + 1))
    return top, found


def _vault_in_repo(cwd) -> bool:
    """Could a git command run in cwd reach a vault? Unknown or missing cwd counts as yes, so the hook only
    relaxes when it can see there's no vault."""
    seen = _vaults_in_repo(cwd)
    return seen is None or bool(seen[1])


def _vault_only_at_root(cwd) -> bool:
    seen = _vaults_in_repo(cwd)
    return seen is not None and bool(seen[1]) and all(v.resolve() == (seen[0] / ".indieward").resolve() for v in seen[1])


def protect_vault(event: dict) -> tuple[int, str]:
    """Best effort, not a guarantee: a user can always disable the hook."""
    tool = event.get("tool_name", "")
    inp = event.get("tool_input", {}) or {}
    if tool in EDIT_TOOLS:
        path = str(inp.get("file_path") or inp.get("notebook_path") or "")
        return (2, VAULT_MSG) if VAULT_PATH.search(path) else (0, "")
    if tool in SHELL_TOOLS:
        cmd = str(inp.get("command", ""))
        root_only = not CHANGES_DIR.search(cmd) and _vault_only_at_root(event.get("cwd"))
        if any(_wipes_ignored(seg, root_only) for seg in SEGMENT.split(cmd)):
            # The plugin runs in every repo; don't block routine cleanups where no vault can be hit.
            # A cd or `git -C` may point at another repo, so then we don't relax.
            if CHANGES_DIR.search(cmd) or _vault_in_repo(event.get("cwd")):
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
