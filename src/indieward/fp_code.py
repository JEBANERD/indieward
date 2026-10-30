"""Code fingerprints: normalized tokens + winnowing (the MOSS method).

Schleimer, Wilkerson & Aiken, "Winnowing: local algorithms for document
fingerprinting", SIGMOD 2003. Identifiers become ``V``, numbers ``N`` and
strings ``S``; keywords and operators stay. That makes renamed variables
invisible. Because the result is a *set* of fingerprints, reordered
functions still match. Comments and whitespace are dropped.

Works on source and on decompiled or bundled text code (Luau, GDScript, C#,
JS/TS, C/C++, Python, Haxe, GML). It does not see inside compiled native
binaries; compare decompiled output against decompiled output there.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

K = 12  # tokens per k-gram
W = 8  # winnowing window

KEYWORDS = set("""
and break do else elseif end false for function goto if in local nil not or repeat return then true until while
continue export type typeof self super extends class_name class func var const static enum signal await yield
match pass tool onready preload load is as void int float bool string null new public private protected internal
sealed override virtual abstract readonly struct namespace using try catch finally throw switch case default
let import from async def lambda with del global nonlocal assert raise except elif print this delete instanceof
of auto unsigned signed char double long short template typename operator sizeof constexpr inline extern
""".split())

# Comment syntax depends on the language. Applying every language's rules to every file broke minified JS:
# the first `i--` started a "Lua comment" and `"#fff"` a "Python comment", each swallowing the rest of a
# one-line bundle. Strings are matched first, so comment markers inside them (URLs, colours) stay text.
_STRINGS = r'"(?:\\.|[^"\\\n])*"|\'(?:\\.|[^\'\\\n])*\'|`(?:\\.|[^`\\])*`'
_C = r"/\*.*?\*/|//[^\n]*"
_LUA = r"--\[(?P<eq>=*)\[.*?\](?P=eq)\]|--[^\n]*"
_HASH = r"#(?!include|define|if|endif|pragma|region|endregion)[^\n]*"
_FAMILY = {
    **dict.fromkeys(".js .mjs .cjs .jsx .ts .tsx .cs .c .h .cc .cpp .hpp .cxx .hx .gml .java .kt .go .rs .swift"
                    " .shader .hlsl .glsl .gdshader".split(), "c"),
    **dict.fromkeys(".lua .luau".split(), "lua"),
    **dict.fromkeys(".py .gd .rb .sh".split(), "hash"),
}
_COMMENT_RES = {
    "c": re.compile(f"(?P<s>{_STRINGS})|{_C}", re.S),
    "lua": re.compile(f"(?P<s>{_STRINGS})|{_LUA}", re.S),
    "hash": re.compile(f"(?P<s>{_STRINGS})|{_HASH}", re.S),
    # Unknown extension (decompiled or extracted text): all rules, as before, but strings still win.
    None: re.compile(f"(?P<s>{_STRINGS})|{_LUA}|{_C}|{_HASH}", re.S),
}


def comment_family(name: str) -> str | None:
    return _FAMILY.get(Path(name).suffix.lower())


_TOKEN_RE = re.compile(
    r'"(?:\\.|[^"\\\n])*"|\'(?:\\.|[^\'\\\n])*\'|`(?:\\.|[^`\\])*`'  # strings
    r"|\d+(?:\.\d+)?(?:[eE][+-]?\d+)?|0x[0-9a-fA-F]+"  # numbers
    r"|[A-Za-z_][A-Za-z0-9_]*"  # identifiers
    r"|==|!=|<=|>=|&&|\|\||\.\.|::|->|=>|\+=|-=|\*=|/=|[{}()\[\];,.:+\-*/%<>=!&|^~?]"
)


def tokens_with_lines(text: str, name: str = "") -> list[tuple[str, int]]:
    """Normalized tokens with their line numbers. `name` picks the comment rules by file extension."""
    def blank(m):  # keep strings; replace comments with their newlines, so line numbers stay stable
        return m.group(0) if m.group("s") is not None else "\n" * m.group(0).count("\n")

    text = _COMMENT_RES[comment_family(name)].sub(blank, text)
    out = []
    line, pos = 1, 0
    for m in _TOKEN_RE.finditer(text):
        t = m.group(0)
        line += text.count("\n", pos, m.start())  # counted incrementally: bundles are one huge line
        pos = m.start()
        c = t[0]
        if c in "\"'`":
            tok = "S"
        elif c.isdigit():
            tok = "N"
        elif c.isalpha() or c == "_":
            tok = t if t in KEYWORDS else "V"
        else:
            tok = t
        out.append((tok, line))
    return out


def _h(seq: tuple[str, ...]) -> int:
    return int.from_bytes(hashlib.blake2b(" ".join(seq).encode(), digest_size=8).digest(), "big")


def winnow(toks: list[tuple[str, int]]) -> dict[int, int]:
    """Return {fingerprint hash: first line}."""
    if len(toks) < K:
        return {}
    grams = [(_h(tuple(t for t, _ in toks[i : i + K])), toks[i][1]) for i in range(len(toks) - K + 1)]
    picked: dict[int, int] = {}
    last = -1
    for i in range(max(1, len(grams) - W + 1)):
        window = grams[i : i + W]
        j = min(range(len(window)), key=lambda k: (window[k][0], -k))
        pos = i + j
        if pos != last:
            h, line = grams[pos]
            picked.setdefault(h, line)
            last = pos
    return picked


def fingerprint_files(paths) -> dict:
    """{hash(str): [relative file, line]} across files, plus per-file token counts."""
    fps: dict[str, list] = {}
    files = {}
    for p in paths:
        p = Path(p)
        try:
            text = p.read_text("utf-8", errors="replace")
        except OSError:
            continue
        toks = tokens_with_lines(text, p.name)
        files[p.name] = len(toks)
        for h, line in winnow(toks).items():
            fps.setdefault(str(h), [p.name, line])
    return {"k": K, "w": W, "fingerprints": fps, "files": files}


def fingerprint_text_blobs(blobs: dict[str, str]) -> dict:
    fps: dict[str, list] = {}
    for name, text in blobs.items():
        for h, line in winnow(tokens_with_lines(text, name)).items():
            fps.setdefault(str(h), [name, line])
    return {"k": K, "w": W, "fingerprints": fps, "files": {n: 0 for n in blobs}}


def compare(orig: dict, suspect: dict, common: set[str] | None = None) -> dict:
    common = common or set()
    fo = {h: v for h, v in orig["fingerprints"].items() if h not in common}
    fs = {h: v for h, v in suspect["fingerprints"].items() if h not in common}
    shared = set(fo) & set(fs)
    n_common = len((set(orig["fingerprints"]) & set(suspect["fingerprints"])) & common)
    if not fo or not fs:
        return {"score": 0, "matched": 0, "coverage_original": 0.0, "coverage_suspect": 0.0, "pairs": [],
                "excluded_common": n_common}
    cov_o = len(shared) / len(fo)
    cov_s = len(shared) / len(fs)
    # Tiny overlaps are noise; require a minimum number of shared fingerprints.
    conf = min(1.0, len(shared) / 25.0)
    score = int(round(100 * max(cov_o, cov_s) * conf))
    # Evidence: group shared fingerprints by (original file, suspect file).
    groups: dict[tuple[str, str], list[tuple[int, int]]] = {}
    for h in shared:
        (of, ol), (sf, sl) = fo[h], fs[h]
        groups.setdefault((of, sf), []).append((ol, sl))
    pairs = []
    for (of, sf), lines in sorted(groups.items(), key=lambda kv: -len(kv[1]))[:8]:
        ols = sorted(l for l, _ in lines)
        sls = sorted(l for _, l in lines)
        pairs.append({"original_file": of, "original_lines": [ols[0], ols[-1] + K // 3],
                      "suspect_file": sf, "suspect_lines": [sls[0], sls[-1] + K // 3], "shared": len(lines)})
    return {"score": score, "matched": len(shared), "coverage_original": round(cov_o, 3),
            "coverage_suspect": round(cov_s, 3), "pairs": pairs, "excluded_common": n_common}
