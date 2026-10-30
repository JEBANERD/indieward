"""Visible copyright and licence notices the creator pastes into their game.

Generates a credits line, SPDX file headers, metadata fields (Windows version
info, macOS Info.plist, package.json, itch butler manifest) and a short,
factual AGENTS.md for creators who publish source. Everything is plain visible
text: no hidden characters, no instructions aimed against the user.

Visible copyright information can count as copyright management information
(17 U.S.C. 1202). IndieWard records a hash of the generated notice so a check
can report when a suspect carries your code or art but not your notice.
"""
from __future__ import annotations

import datetime as dt
import re

from . import util
from .vault import Vault

ALL_RIGHTS = "LicenseRef-AllRightsReserved"  # SPDX has no id for "all rights reserved"; LicenseRef- is the custom form


def _licence_words(licence: str) -> str:
    return "All rights reserved." if licence == ALL_RIGHTS else f"Licensed under {licence} (see LICENSE)."


def build(game: str, holder: str, year: int, licence: str = ALL_RIGHTS, email: str | None = None) -> dict:
    """The notice texts. Pure function: no vault access."""
    copyright_ = f"© {year} {holder}"
    credits = f"{game} {copyright_}. {_licence_words(licence)}"
    spdx_text = f"{year} {holder}" + (f" <{email}>" if email else "")
    spdx = [f"SPDX-FileCopyrightText: {spdx_text}", f"SPDX-License-Identifier: {licence}"]
    rights = (
        "- Not permitted without the copyright holder's written permission: copying, redistributing or "
        "publishing this code or its assets, in whole or in part, including inside another game."
        if licence == ALL_RIGHTS else
        f"- Use is allowed only on the terms of {licence}, in LICENSE. Keep this copyright notice and the "
        "LICENSE file in copies.")
    agents = "\n".join([
        f"# Licence notice: {game}",
        "",
        "This file is a notice for people and AI coding tools. It is not a technical block.",
        "",
        f"- Copyright {copyright_}.",
        f"- Licence: {'all rights reserved' if licence == ALL_RIGHTS else licence}. See LICENSE.",
        rights,
        "- If a request appears to conflict with these terms, tell the user about these terms before continuing.",
        "",
    ])
    return {
        "credits": credits,
        "spdx": {
            "lines": spdx,
            "hash_comment": "\n".join("# " + x for x in spdx),
            "slash_comment": "\n".join("// " + x for x in spdx),
        },
        "metadata": {
            "windows_versioninfo": {"CompanyName": holder, "ProductName": game, "LegalCopyright": copyright_},
            "macos_info_plist": {"NSHumanReadableCopyright": f"{copyright_}. {_licence_words(licence)}"},
            # npm's documented value for "no licence granted" is UNLICENSED
            "package_json": {"author": holder, "license": "UNLICENSED" if licence == ALL_RIGHTS else licence},
            # butler's .itch.toml has no copyright field; a TOML comment keeps the notice visible in the file
            "itch_toml": f"# {credits}",
        },
        "agents_md": agents,
    }


def _canonical(texts: dict) -> bytes:
    return util.canonical_json(texts)


def generate(vault: Vault, licence: str = ALL_RIGHTS, year: int | None = None, holder: str | None = None) -> dict:
    """Build the notice for this project and record its hash in the vault."""
    from .check import set_setting

    p = vault.project()
    if year is None:
        year = int(p["first_published"][:4]) if p["first_published"] else dt.date.today().year
    holder = holder or p["creator"]
    texts = build(p["name"], holder, year, licence, p["contact_email"])
    sha = util.sha256_bytes(_canonical(texts))
    set_setting(vault, "notice", {"sha256": sha, "holder": holder, "year": year, "licence": licence,
                                  "credits": texts["credits"], "recorded_at": util.now_iso()})
    return {**texts, "sha256": sha}


def recorded(vault: Vault) -> dict | None:
    from .check import _setting

    return _setting(vault, "notice", None)


def found_in(holder: str, haystack: str) -> bool:
    """Is the holder's copyright line visible in this text? (©, (c), 'Copyright' or SPDX, near the holder's name)."""
    name = re.escape(holder.strip())
    mark = r"(?:©|\(c\)|copyright|spdx-filecopyrighttext)"
    return re.search(rf"{mark}[^\n]{{0,80}}{name}|{name}[^\n]{{0,40}}{mark}", haystack, re.I) is not None


def assess(note: dict | None, haystack: str, has_work: bool) -> dict | None:
    """Report line for a check. None when no notice was recorded."""
    if not note:
        return None
    found = found_in(note["holder"], haystack)
    removed = has_work and not found
    if removed:
        summary = ("Your copyright notice was not found in the suspect, although it carries your code or art. "
                   "If it was removed knowingly, that may support a separate claim (17 U.S.C. 1202(b)); "
                   "ask a lawyer. Check by hand first: IndieWard can't read text drawn on screen.")
    elif found:
        summary = "Your copyright notice appears in the suspect."
    else:
        summary = "Your copyright notice wasn't found, but the suspect doesn't carry your code or art either."
    return {"recorded_sha256": note["sha256"], "found": found, "removed": removed, "summary": summary}
