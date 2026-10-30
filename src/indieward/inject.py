"""Trap camouflage: add a build's trap strings to the creator's own key-addressed data files.

A separate file of odd constants is easy for a refactor (human or AI) to spot and delete. Extra
entries in a localization table look like the rest of it. IndieWard only appends: existing entries
are never changed, keys follow the file's own naming style, nothing is written without --apply,
and a backup is made first.

Only key-addressed data is supported (localization CSV with a key column, JSON objects, gettext
PO): the game looks entries up by key, so an extra key is never displayed or read by gameplay.
Arrays and row tables a game iterates over are refused.
"""
from __future__ import annotations

import csv
import datetime as dt
import difflib
import hashlib
import io
import json
import re
import shutil
from pathlib import Path

from . import traps
from .vault import Vault

KEY_HEADERS = {"key", "keys", "id", "string_id", "stringid", "string_key", "loc_key", "lockey", "token", "identifier",
               "msgid", "name", "tag", "term"}
WORDS = ["hint", "tip", "caption", "label", "desc", "note", "line", "text", "blurb", "subtitle"]
WARNING = ("Inject only into files your game looks entries up in by key (localization tables). "
           "Don't use a file your game loops over, or the extra entries could be shown.")


class InjectError(ValueError):
    pass


def _values(vault: Vault, build_id: str) -> list[str]:
    rows = traps.records(vault, build_id)
    if not rows:
        raise InjectError(f"unknown build {build_id}")
    return [t["value"] for t in rows if t["kind"] == "string"]


# --- key naming -----------------------------------------------------------------------

def _style(keys: list[str]) -> tuple[str, str]:
    """(separator style, most common prefix) of existing keys."""
    keys = [k for k in keys if isinstance(k, str) and k]
    if not keys:
        return "snake", ""
    if all("." in k for k in keys):
        sep = "."
    elif sum("-" in k for k in keys) > len(keys) / 2:
        sep = "-"
    elif sum("_" in k for k in keys) > len(keys) / 2:
        sep = "_"
    else:
        sep = ""
    upper = sum(k.isupper() for k in keys) > len(keys) / 2
    style = {".": "dot", "-": "kebab", "_": "upper" if upper else "snake", "": "camel"}[sep]
    prefix = ""
    if sep:
        heads = [k.split(sep)[0] for k in keys if sep in k]
        if heads:
            top = max(set(heads), key=heads.count)
            prefix = top if heads.count(top) > 1 else ""
    return style, prefix


def _make_key(style: str, prefix: str, value: str, n: int) -> str:
    word = WORDS[int(hashlib.sha256(value.encode()).hexdigest(), 16) % len(WORDS)]
    parts = [p for p in (prefix, word, str(n)) if p]
    if style == "dot":
        return ".".join(parts)
    if style == "kebab":
        return "-".join(parts).lower()
    if style == "upper":
        return "_".join(parts).upper()
    if style == "camel":
        return parts[0] + "".join(p[:1].upper() + p[1:] for p in parts[1:])
    return "_".join(parts).lower()


def _new_keys(existing: list[str], values: list[str]) -> list[str]:
    style, prefix = _style(existing)
    taken, out = set(existing), []
    for v in values:
        n = 2 + int(hashlib.sha256(v.encode()).hexdigest()[:4], 16) % 40
        k = _make_key(style, prefix, v, n)
        while k in taken:
            n += 1
            k = _make_key(style, prefix, v, n)
        taken.add(k)
        out.append(k)
    return out


# --- formats --------------------------------------------------------------------------

def _newline(text: str) -> str:
    return "\r\n" if "\r\n" in text else "\n"


def _csv(text: str, values: list[str]) -> tuple[str, list[tuple[str, str]]]:
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    rows = list(csv.reader(io.StringIO(text), dialect))
    if not rows or not rows[0] or rows[0][0].strip().lower() not in KEY_HEADERS:
        raise InjectError("this CSV's first column isn't a key column (key, id, ...), so it may be a table the "
                          "game loops over; not injecting")
    keys = _new_keys([r[0] for r in rows[1:] if r], values)
    nl = _newline(text)
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=dialect.delimiter, quotechar=dialect.quotechar or '"', lineterminator=nl)
    for k, v in zip(keys, values):
        w.writerow([k] + [v] * (len(rows[0]) - 1))
    head = text if text.endswith(("\n", "\r")) else text + nl
    return head + buf.getvalue(), list(zip(keys, values))


def _object_spans(text: str) -> list[tuple[int, int, int]]:
    """(start, end, depth) of every JSON object, end being the index of its closing brace."""
    spans, stack, in_str, esc = [], [], False, False
    for i, c in enumerate(text):
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c in "{[":
            stack.append((c, i))
        elif c in "}]":
            o, s = stack.pop()
            if o == "{":
                spans.append((s, i, len(stack) + 1))
    return spans


def _insert(text: str, start: int, end: int, entries: list[tuple[str, str]], colon: str) -> str:
    j = end - 1
    while text[j] in " \t\r\n":
        j -= 1
    items = [json.dumps(k, ensure_ascii=False) + colon + json.dumps(v, ensure_ascii=False) for k, v in entries]
    body = text[start + 1:end]
    if "\n" not in body.strip("\r\n"):  # one-line object
        add = (", " if text[j] != "{" else "") + ", ".join(items)
        return text[:j + 1] + add + text[j + 1:]
    nl = _newline(text)
    last_line = text[:j + 1].rsplit("\n", 1)[-1]
    indent = re.match(r"[ \t]*", last_line).group(0) if text[j] != "{" else "  "
    add = ("," if text[j] != "{" else "") + "".join(nl + indent + x + ("," if n < len(items) - 1 else "")
                                                     for n, x in enumerate(items))
    return text[:j + 1] + add + text[j + 1:]


def _json(text: str, values: list[str]) -> tuple[str, list[tuple[str, str]]]:
    data = json.loads(text)
    if not isinstance(data, dict):
        raise InjectError("this JSON file is a list, which games usually loop over; not injecting")
    spans = _object_spans(text)
    top = [s for s in spans if s[2] == 1][0]
    colon = ": " if re.search(r'"\s*:\s', text) else ":"
    if any(isinstance(v, str) for v in data.values()):
        targets = [(top, data)]
    elif data and all(isinstance(v, dict) and any(isinstance(x, str) for x in v.values()) for v in data.values()):
        subs = sorted(s for s in spans if s[2] == 2)
        targets = list(zip(subs, data.values()))  # one object per locale, in file order
    else:
        raise InjectError("couldn't find a flat table of strings in this JSON file; not injecting")
    keys = _new_keys([k for _, obj in targets for k in obj], values)
    entries = list(zip(keys, values))
    for (s, e, _), _obj in sorted(targets, key=lambda t: -t[0][0]):  # back to front keeps offsets valid
        text = _insert(text, s, e, entries, colon)
    return text, entries


_PO_ID = re.compile(r'^msgid\s+"((?:\\.|[^"\\])*)"', re.M)


def _po(text: str, values: list[str]) -> tuple[str, list[tuple[str, str]]]:
    ids = [m.group(1) for m in _PO_ID.finditer(text) if m.group(1)]
    if not _PO_ID.search(text):
        raise InjectError("no msgid entries found; is this a gettext .po file?")
    keys = _new_keys(ids, values)
    nl = _newline(text)
    esc = lambda s: s.replace("\\", "\\\\").replace('"', '\\"')  # noqa: E731
    add = "".join(f'{nl}msgid "{esc(k)}"{nl}msgstr "{esc(v)}"{nl}' for k, v in zip(keys, values))
    head = text if text.endswith(("\n", "\r")) else text + nl
    return head + add, list(zip(keys, values))


FORMATS = {".csv": _csv, ".json": _json, ".po": _po}


def plan(vault: Vault, build_id: str, path) -> dict:
    """What injecting would change, as a diff. Writes nothing."""
    vault.require_verified("inject trap markers")
    p = Path(path)
    fmt = FORMATS.get(p.suffix.lower())
    if not fmt:
        raise InjectError(f"supported files: {', '.join(FORMATS)}")
    raw = p.read_bytes()
    text = raw.decode("utf-8-sig")
    bom = raw.startswith(b"\xef\xbb\xbf")
    values = _values(vault, build_id)
    if any(v in text for v in values):
        raise InjectError("this build's traps are already in that file")
    new, entries = fmt(text, values)
    diff = "".join(difflib.unified_diff(text.splitlines(True), new.splitlines(True), str(p), str(p) + " (injected)"))
    return {"file": str(p), "entries": [{"key": k} for k, _ in entries], "diff": diff, "warning": WARNING,
            "_new": ("﻿" if bom else "") + new}


def apply(vault: Vault, build_id: str, path) -> dict:
    r = plan(vault, build_id, path)
    p = Path(path)
    backup = p.with_name(p.name + ".indieward-" + dt.datetime.now().strftime("%Y%m%d%H%M%S") + ".bak")
    shutil.copy2(p, backup)
    p.write_bytes(r.pop("_new").encode("utf-8"))
    return {**r, "applied": True, "backup": str(backup)}
