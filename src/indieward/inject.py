"""Trap camouflage: hide a build's trap values inside the creator's own data files.

A separate file full of nonsense constants is easy for a refactoring tool to
spot and strip as dead code. The same values as a few extra keys in a real
localization file, manifest or data table look like everything around them.

Supported: localization/data CSV (one more row per value), JSON (extra keys in
the busiest string table, or one more object in a list of objects), and
gettext PO (extra msgid/msgstr entries). Lists of rows need ``rows=True``, because a
game that loops over every row would show or load the trap. New entries follow the file's own key
style (prefix, separator, case) and are only ever added: existing text is never
rewritten. Nothing is written without ``apply=True``; a backup goes into the
vault first. Injected keys aren't referenced by game code, so they're never
displayed and never read by gameplay. Keep the snippet from ``traps new`` as a
fallback for builds that drop unused data.
"""
from __future__ import annotations

import csv
import difflib
import io
import json
import re
from collections import Counter
from pathlib import Path

from . import util
from .traps import records
from .vault import Vault

BOM = "\ufeff"
FORMATS = {".csv": "csv", ".tsv": "csv", ".json": "json", ".po": "po", ".pot": "po"}


class InjectError(ValueError):
    pass


# --- key style ------------------------------------------------------------------

def _style(keys: list[str]) -> dict:
    keys = [k for k in keys if k]
    sep = next((s for s, _ in Counter(c for k in keys for c in k if c in "._-/:").most_common(1)), "")
    prefix = ""
    if sep:
        heads = Counter(k.split(sep, 1)[0] for k in keys if sep in k)
        if heads:
            head, n = heads.most_common(1)[0]
            prefix = head if n >= 2 or len(heads) == 1 else ""
    words = [k.split(sep)[-1] if sep else k for k in keys]
    case = ("upper" if words and all(w.isupper() for w in words if any(c.isalpha() for c in w)) else
            "camel" if words and sum(bool(re.match(r"^[a-z]+[A-Z]", w)) for w in words) > len(words) / 2 else
            "pascal" if words and sum(bool(re.match(r"^[A-Z][a-z]+[A-Z]", w)) for w in words) > len(words) / 2 else
            "lower")
    return {"sep": sep, "prefix": prefix, "case": case}


def _key(style: dict, word: str) -> str:
    """A key in the file's style. Keys are only camouflage: the trap values are what scans find."""
    parts = [p for p in re.split(r"[^A-Za-z0-9]+", word) if p]
    if style["case"] in ("camel", "pascal"):
        w = "".join(p.capitalize() for p in parts)
        w = w[:1].lower() + w[1:] if style["case"] == "camel" else w
    else:
        w = "_".join(parts)
        w = w.upper() if style["case"] == "upper" else w.lower()
    return f"{style['prefix']}{style['sep']}{w}" if style["prefix"] else w


def _entries(vault: Vault, build_id: str) -> tuple[list[tuple[str, str]], str]:
    """(word for the key, trap value) pairs, plus the build constant for numeric fields."""
    v = {r["label"]: r["value"] for r in records(vault, build_id)}
    if not v:
        raise InjectError(f"unknown build {build_id}")
    # Two core strings and the build string are what `traps verify` needs to pass.
    return [(v["loc_key"], v["meta_value"]), (v["dead_function"].strip("_"), v["function_return"]),
            (v["build_tag"][:9], v["build_tag"])], v["build_constant"]


# --- formats --------------------------------------------------------------------

def _nl(text: str) -> str:
    return "\r\n" if "\r\n" in text else "\n"


def _inject_csv(text: str, pairs, path: Path) -> tuple[str, list[str]]:
    sample = text[:20000]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel_tab if path.suffix.lower() == ".tsv" else csv.excel
    rows = list(csv.reader(io.StringIO(text), dialect))
    rows = [r for r in rows if r]
    if len(rows) < 2:
        raise InjectError("the CSV needs a header row and at least one data row to copy its style from")
    width = len(rows[0])
    style = _style([r[0] for r in rows[1:]])
    nl = _nl(text)
    out = io.StringIO()
    w = csv.writer(out, dialect, lineterminator=nl)
    keys = []
    for word, value in pairs:
        k = _key(style, word)
        keys.append(k)
        w.writerow([k] + [value] * max(width - 1, 1))
    return (text if text.endswith(("\n", "\r")) else text + nl) + out.getvalue(), keys


def _json_dump_variants(obj, text: str):
    """A json.dumps that reproduces the file byte for byte, so re-dumping only adds lines."""
    # JSON strings never hold a raw newline, so the file's line ending (CRLF on Windows) maps back exactly.
    nl = "\r\n" if "\r\n" in text else "\n"
    tail = nl if text.endswith("\n") else ""
    layouts = [(i, (",", ": ")) for i in (2, 4, "\t", 1, 3)] + [(None, (",", ":")), (None, (", ", ": "))]
    for ascii_ in (False, True):
        for indent, seps in layouts:
            def dump(o, indent=indent, seps=seps, ascii_=ascii_):
                return json.dumps(o, indent=indent, separators=seps, ensure_ascii=ascii_).replace("\n", nl) + tail
            if dump(obj) == text:
                return dump
    return None


def _string_tables(obj, path=()):
    """Every dict whose values are mostly strings, with its path."""
    if isinstance(obj, dict):
        vals = list(obj.values())
        if vals and sum(isinstance(x, str) for x in vals) * 2 >= len(vals):
            yield path, obj
        for k, x in obj.items():
            yield from _string_tables(x, path + (k,))


ROWS_WARNING = ("Only use a file your game looks things up in by key or id. If your game loops over every row "
                "(an item list, a level list, an asset preload list), the trap rows would be shown or loaded, "
                "which traps must never do.")


def _inject_json(text: str, pairs, number: str, rows: bool = False) -> tuple[str, list[str]]:
    body = text[1:] if text.startswith(BOM) else text
    try:
        obj = json.loads(body)
    except json.JSONDecodeError as e:
        raise InjectError(f"not valid JSON: {e}") from e
    dump = _json_dump_variants(obj, body)
    if dump is None:
        raise InjectError("couldn't add to this JSON without reformatting it; use the snippet from `traps new` "
                          "instead, or reformat the file with 2-space indentation first")
    keys = []
    if isinstance(obj, list) and obj and all(isinstance(x, dict) for x in obj):
        # A manifest or data table: one more row per value, shaped like the last row.
        if not rows:
            raise InjectError("this JSON is a list of rows (a manifest or data table). " + ROWS_WARNING +
                              " If the game only looks rows up by id, run again with --rows")
        template = obj[-1]
        text_fields = [k for k, val in template.items() if isinstance(val, str)]
        if len(text_fields) < 2:
            raise InjectError("the list's objects need a name field and at least one more text field")
        id_field = text_fields[0]
        style = _style([x[id_field] for x in obj if isinstance(x.get(id_field), str)])
        new = list(obj)
        for word, value in pairs:
            row = {}
            for k, val in template.items():
                if k == id_field:
                    row[k] = _key(style, word)
                elif isinstance(val, str):
                    row[k] = value
                elif isinstance(val, float):
                    row[k] = float(number)
                elif isinstance(val, (bool, int)) or val is None:
                    row[k] = val
                else:
                    row[k] = type(val)()
            new.append(row)
            keys.append(row[id_field])
    elif isinstance(obj, dict):
        tables = list(_string_tables(obj))
        if not tables:
            raise InjectError("found no string table (an object whose values are text) to add keys to")
        path_, table = max(tables, key=lambda t: len(t[1]))
        style = _style(list(table))
        new = json.loads(json.dumps(obj))
        target = new
        for k in path_:
            target = target[k]
        for word, value in pairs:
            k = _key(style, word)
            if k in target:
                raise InjectError(f"key {k!r} already exists")
            target[k] = value
            keys.append(k)
    else:
        raise InjectError("the JSON must be an object or a list of objects")
    return (BOM if text.startswith(BOM) else "") + dump(new), keys


def _po_quote(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def _inject_po(text: str, pairs) -> tuple[str, list[str]]:
    ids = [m.group(1) for m in re.finditer(r'^msgid\s+"(.*)"\s*$', text, re.M)]
    ids = [i for i in ids if i]
    if not ids:
        raise InjectError("found no msgid entries to copy the style from")
    ctxt = bool(re.search(r"^msgctxt\s", text, re.M))
    keylike = sum(bool(re.match(r"^[\w.\-/:]+$", i)) for i in ids) * 2 >= len(ids)
    style = _style(ids) if keylike else {"sep": "", "prefix": "", "case": "lower"}
    ctx = Counter(m.group(1) for m in re.finditer(r'^msgctxt\s+"(.*)"\s*$', text, re.M)).most_common(1)
    nl = _nl(text)
    blocks, keys = [], []
    for word, value in pairs:
        k = _key(style, word) if keylike else value
        if f'msgid {_po_quote(k)}' in text:
            raise InjectError(f"msgid {k!r} already exists")
        lines = ([f"msgctxt {_po_quote(ctx[0][0])}"] if ctxt and ctx else []) + \
                [f"msgid {_po_quote(k)}", f"msgstr {_po_quote(value)}"]
        blocks.append(nl.join(lines))
        keys.append(k)
    head = text if text.endswith(("\n", "\r")) else text + nl
    return head + nl + (nl + nl).join(blocks) + nl, keys


def _extends(old, new) -> bool:
    """new keeps every old key and value as is; lists may only grow at the end."""
    if isinstance(old, dict):
        return isinstance(new, dict) and all(k in new and _extends(v, new[k]) for k, v in old.items())
    if isinstance(old, list):
        return isinstance(new, list) and len(new) >= len(old) and all(_extends(a, b) for a, b in zip(old, new))
    return type(old) is type(new) and old == new


# --- entry point ----------------------------------------------------------------

def inject(vault: Vault, build_id: str, into, apply: bool = False, rows: bool = False) -> dict:
    """Plan (and with apply=True, write) trap entries into one of the creator's data files."""
    vault.require_verified("inject trap markers")
    path = Path(into)
    fmt = FORMATS.get(path.suffix.lower())
    if not fmt:
        raise InjectError(f"unsupported file type {path.suffix!r}; use a .csv, .tsv, .json or .po file")
    if not path.is_file():
        raise InjectError(f"no such file: {path}")
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as e:
        raise InjectError("the file isn't UTF-8 text") from e
    pairs, number = _entries(vault, build_id)
    if any(p[1] in text for p in pairs):
        raise InjectError("this file already holds this build's trap values")
    if fmt == "csv":
        new, keys = _inject_csv(text, pairs, path)
    elif fmt == "json":
        new, keys = _inject_json(text, pairs, number, rows)
    else:
        new, keys = _inject_po(text, pairs)
    if not new.startswith(text.rstrip("\r\n")) and fmt != "json":
        raise InjectError("refusing: the change would alter existing lines")  # belt and braces
    if fmt == "json" and not _extends(json.loads(text.lstrip(BOM)), json.loads(new.lstrip(BOM))):
        raise InjectError("refusing: the change would alter existing JSON entries")  # belt and braces
    diff = "".join(difflib.unified_diff(text.splitlines(True), new.splitlines(True),
                                        fromfile=str(path), tofile=str(path)))
    res = {"file": str(path), "format": fmt, "build_id": build_id, "keys": keys, "diff": diff, "applied": False}
    if fmt == "csv" or rows:
        res["warning"] = ROWS_WARNING
    if not apply:
        res["next"] = "Review the diff, then run again with --apply to write it (a backup goes into the vault first)."
        return res
    backups = vault.path("backups")
    backups.mkdir(parents=True, exist_ok=True)
    stamp = util.now_iso().replace(":", "").replace("-", "")[:15]
    backup = backups / f"{stamp}_{path.name}"
    backup.write_bytes(raw)
    path.write_bytes(new.encode("utf-8"))
    from .check import _setting, set_setting

    log = _setting(vault, "injections", [])
    log.append({"build_id": build_id, "file": str(path.resolve()), "keys": keys, "at": util.now_iso(),
                "sha256": util.sha256_bytes(new.encode("utf-8")), "backup": vault.rel(backup)})
    set_setting(vault, "injections", log)
    res.update(applied=True, backup=str(backup),
               next="Don't reference these keys from game code. Export the build, then run "
                    f"`indieward build register --build {build_id} <export>` to confirm they survived.")
    return res
