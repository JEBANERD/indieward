"""IndieWard MCP server (stdio) for the Claude plugin.

Exposes the local engine as tools. By design there is NO tool that sends
email, submits a form or contacts a store: packages are drafts the creator
sends from their own account. There is also no tool to override the
"don't file" advice on weak evidence; that takes a deliberate CLI flag.
"""
from __future__ import annotations

import functools
import hashlib
import json
import os
import traceback
from pathlib import Path

try:  # MCP Python SDK 2.x
    from mcp.server.mcpserver import MCPServer as _Server
except ImportError:
    try:  # MCP Python SDK 1.x
        from mcp.server.fastmcp import FastMCP as _Server
    except ImportError as e:  # pragma: no cover
        raise SystemExit("The MCP server needs the 'mcp' package: pip install 'indieward[mcp]'") from e

from . import certificate, check, cli, inject, package, registry, signals, stores, timestamp, traps, verify, watch, wm_video
from . import doctor as _doctor
from .vault import Vault, find_vault

mcp = _Server("indieward")


def _safe(fn):
    @functools.wraps(fn)
    def wrapper(*a, **k):
        try:
            return fn(*a, **k)
        except Exception as e:
            return {"error": f"{type(e).__name__}: {e}",
                    "trace": traceback.format_exc(limit=2) if not isinstance(e, (PermissionError, ValueError, FileNotFoundError)) else None}
    return wrapper


@mcp.tool()
@_safe
def doctor(project_dir: str = ".") -> dict:
    """Check this machine is ready: Python 3.10+, FFmpeg, OpenSSL with `openssl ts`, optional ots client and mcp
    package, and a writable vault folder. Each problem has one fix command for the user to run; nothing is installed."""
    return _doctor.run(project_dir)


@mcp.tool()
@_safe
def project_status(project_dir: str) -> dict:
    """Vault status: verification code and state, counts, pending timestamps, copyright-window deadline, takedowns."""
    return cli.status(find_vault(project_dir))


@mcp.tool()
@_safe
def init_project(project_dir: str, game_name: str, creator_legal_name: str, contact_email: str = "") -> dict:
    """Create a local vault in the game's project folder. Keys are generated on this machine; tell the user to back up .indieward/keys."""
    v = Vault.init(project_dir, game_name, creator_legal_name, contact_email or None)
    return cli.status(v)


@mcp.tool()
@_safe
def verify_store_page(project_dir: str, store: str, url: str) -> dict:
    """Verify control of a store page (store: steam | itch | roblox). The user must first paste the project's
    verification code into the game's public description. Reads one public page or official API."""
    return verify.verify_page(find_vault(project_dir), store, url)


@mcp.tool()
@_safe
def verify_with_itch_key(project_dir: str, url: str, api_key: str) -> dict:
    """Verify an itch.io game with the user's own itch.io API key (used once, never stored)."""
    return verify.verify_itch_key(find_vault(project_dir), url, api_key)


@mcp.tool()
@_safe
def verify_with_steam_publisher_key(project_dir: str, url: str, publisher_key: str) -> dict:
    """Verify a Steam app with a Steamworks publisher Web API key (used once, never stored)."""
    return verify.verify_steam_key(find_vault(project_dir), url, publisher_key)


@mcp.tool()
@_safe
def set_first_published(project_dir: str, date: str) -> dict:
    """Record the game's first publication date (YYYY-MM-DD) to track the 3-month copyright registration window."""
    v = find_vault(project_dir)
    v.set_first_published(date)
    return cli.status(v)


@mcp.tool()
@_safe
def register_assets(project_dir: str, paths: list[str], category: str = "", watermark: bool = True) -> dict:
    """Register files or folders: hash, fingerprint and (for images, audio, video) embed an invisible signed mark.
    category: art | ui | logo | audio | video | code | text | other (default by file type).
    Watermarked copies go to <project>/indieward_out/; originals are never modified."""
    v = find_vault(project_dir)
    out = []
    for p in paths:
        out += registry.register_path(v, p, category or None, watermark)
    return {"registered": out, "next": "issue_certificate to sign and timestamp these registrations"}


@mcp.tool()
@_safe
def issue_certificate(project_dir: str) -> dict:
    """Sign a proof-of-ownership certificate (JSON + PDF) over all registrations and request independent timestamps."""
    return certificate.issue(find_vault(project_dir))


@mcp.tool()
@_safe
def verify_certificate(certificate_json: str) -> dict:
    """Check a certificate's signature and digest."""
    return certificate.verify(certificate_json)


@mcp.tool()
@_safe
def retry_timestamps(project_dir: str) -> list:
    """Finish timestamps that were pending (e.g. made offline)."""
    return timestamp.retry_pending(find_vault(project_dir))


@mcp.tool()
@_safe
def new_trap_markers(project_dir: str, build_label: str, engine: str, out_dir: str = "") -> dict:
    """Generate trap markers for a new build. engine: godot | unity | ue5 | roblox | web | generic.
    Returns where the snippet files were written; the user (or you, with permission) copies them into the project."""
    v = find_vault(project_dir)
    r = traps.generate(v, build_label, engine)
    if out_dir:
        traps.write_snippets(v, r["build_id"], out_dir, engine)
        r["snippets"] = out_dir
    r["files"] = [str(p) for p in Path(r["snippets"]).rglob("*") if p.is_file()]
    return r


@mcp.tool()
@_safe
def register_build(project_dir: str, build_id: str, exported_build_path: str) -> dict:
    """After exporting a build: confirm its traps survived and store its fingerprints."""
    return registry.register_build(find_vault(project_dir), build_id, exported_build_path)


@mcp.tool()
@_safe
def detect_watermark(project_dir: str, file: str) -> dict:
    """Look for the creator's watermark in one image, audio or video file."""
    return cli.detect_file(find_vault(project_dir), file)


@mcp.tool()
@_safe
def check_suspect(project_dir: str, paths: list[str] | None = None, store_url: str = "", page_file: str = "",
                  suspect_name: str = "") -> dict:
    """Check a suspect: build folders/archives, screenshots, audio, clips, and/or one store page.
    Returns per-category scores with Strong/Supporting/Weak labels and the recommendation.
    Always relay the disclaimer: similarity only, can't show AI use, not a legal finding."""
    r = check.run(find_vault(project_dir), paths or [], store_url or None, page_file or None, suspect_name or None)
    r["disclaimer"] = check.util.DISCLAIMER
    return r


@mcp.tool()
@_safe
def read_check_report(project_dir: str, check_id: str) -> dict:
    """The full report for a check (evidence trimmed for length)."""
    v = find_vault(project_dir)
    row = v.db.execute("SELECT report_path FROM checks WHERE id=?", (check_id,)).fetchone()
    r = json.loads(v.path(row[0]).read_text())
    for c in r["categories"]:
        c["evidence"] = c["evidence"][:4]
    return r


@mcp.tool()
@_safe
def build_takedown_package(project_dir: str, check_id: str, stores_csv: str = "",
                           claim: str = "copyright", suspect_urls: list[str] | None = None,
                           registration_number: str = "") -> dict:
    """Build a proof-of-work takedown package from a check: certificate, evidence, pre-filled notice, and a
    pre-addressed .eml draft + checklist per store. NOTHING IS SENT. Refuses checks that advise against filing.
    Leave stores_csv empty to target only the stores the suspect URLs are on."""
    stores_list = [s.strip() for s in stores_csv.split(",") if s.strip()] or None
    return package.build(find_vault(project_dir), check_id, stores_list, claim,
                         suspect_urls, registration_number or None, override_weak=False)


@mcp.tool()
@_safe
def log_takedown_sent(project_dir: str, check_id: str, store: str, note: str = "") -> dict:
    """Record that the USER sent a notice themselves. Only call after they confirm they sent it."""
    v = find_vault(project_dir)
    package.mark_sent(v, check_id, store, note or None)
    return {"logged": True}


@mcp.tool()
@_safe
def store_channels() -> dict:
    """Each store's official takedown channel, with source pages and last-checked date."""
    return stores.STORES


@mcp.tool()
@_safe
def footage_burn_in(src: str, dst: str, text: str) -> dict:
    """Burn a visible corner mark into a video (deterrent and leak tracing, not protection)."""
    return wm_video.burn_in(src, dst, text)


@mcp.tool()
@_safe
def footage_preview(src: str, dst: str, max_height: int = 720) -> dict:
    """Make a lower-resolution public preview; keep the master private."""
    wm_video.preview(src, dst, max_height)
    return {"preview": dst}


@mcp.tool()
@_safe
def rights_signals(which: str = "robots") -> str:
    """AI-use reservation text: robots | cawg | tdmrep. These are signals some crawlers honor, not blocks."""
    return {"robots": signals.robots_txt, "cawg": signals.cawg_training_mining, "tdmrep": signals.tdm_rep_header}[which]()


@mcp.tool()
@_safe
def add_common_material(project_dir: str, path: str) -> dict:
    """Index shared material (asset-store packs, engine templates) so it never counts as copying."""
    return check.add_common(find_vault(project_dir), path)


@mcp.tool()
@_safe
def set_mechanics(project_dir: str, mechanics: list[str]) -> dict:
    """List the game's mechanics in a few words each (scored only as Weak evidence)."""
    check.set_setting(find_vault(project_dir), "mechanics", mechanics)
    return {"mechanics": mechanics}


def _confirm_code(*parts) -> str:
    """Short hash of exactly what a plan showed, so an apply/run can't do anything else."""
    return hashlib.sha256(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()[:12]


def _inject_code(build_id: str, file: str, rows: bool, plan: dict) -> str:
    p = Path(file)
    return _confirm_code("inject", build_id, str(p.resolve()), bool(rows), plan["diff"],
                         hashlib.sha256(p.read_bytes()).hexdigest())


@mcp.tool()
@_safe
def trap_inject_plan(project_dir: str, build_id: str, file: str, rows: bool = False) -> dict:
    """Plan adding a build's trap values to one of the creator's own localization files (.csv, .tsv, .json, .po).
    Writes nothing. Returns the diff and a confirm_code. Show the diff to the user; only if they say yes, call
    trap_inject_apply with the same arguments and the confirm_code."""
    v = find_vault(project_dir)
    plan = inject.inject(v, build_id, file, apply=False, rows=rows)
    plan["confirm_code"] = _inject_code(build_id, file, rows, plan)
    plan["next"] = "Show this diff to the user. Call trap_inject_apply only after they agree."
    return plan


@mcp.tool()
@_safe
def trap_inject_apply(project_dir: str, build_id: str, file: str, confirm_code: str, rows: bool = False) -> dict:
    """Write the change trap_inject_plan showed (a backup goes into the vault first). Call it only after the user
    has seen that diff and agreed. Refuses if the confirm_code doesn't match, for example because the file changed."""
    v = find_vault(project_dir)
    plan = inject.inject(v, build_id, file, apply=False, rows=rows)
    if confirm_code != _inject_code(build_id, file, rows, plan):
        raise ValueError("confirm_code doesn't match the current plan: run trap_inject_plan again and show the user")
    return inject.inject(v, build_id, file, apply=True, rows=rows)


def _watch_plan(v, sources: list[str], include_core: bool) -> dict:
    v.require_verified("watch for copies")
    sources = list(dict.fromkeys(sources))
    bad = [x for x in sources if x not in watch.SOURCES]
    if bad or not sources:
        raise ValueError(f"choose sources from {', '.join(watch.SOURCES)}")
    texts, hashes = watch.text_needles(v, include_core), watch.hash_needles(v)
    plan = {}
    for src in sources:  # same selection as watch.run
        if src == "swh":
            plan[src] = [{"label": h["label"], "sends": f"{h['algo']} hash only"} for h in hashes]
        else:
            plan[src] = [{"label": n["label"], "sends": n["value"]} for n in texts if src == "github" or not n.get("notice")]
    return {"sources": sources, "include_core": include_core, "will_send": plan,
            "disclosure": watch.DISCLOSURE if any(x in watch.TEXT_SOURCES for x in sources) else None}


@mcp.tool()
@_safe
def watch_plan(project_dir: str, sources: list[str], include_core: bool = False) -> dict:
    """Show what a canary search would send to each source (swh, github, npm), without sending anything.
    Software Heritage gets hashes only; GitHub and npm get the exact strings, which discloses them to those
    companies. Returns a confirm_code. Show this plan to the user; only if they agree, call watch_run."""
    plan = _watch_plan(find_vault(project_dir), sources, include_core)
    plan["confirm_code"] = _confirm_code("watch", plan["sources"], include_core, plan["will_send"])
    plan["next"] = "Show the user what will be sent and to whom. Call watch_run only after they agree."
    return plan


@mcp.tool()
@_safe
def watch_run(project_dir: str, sources: list[str], confirm_code: str, include_core: bool = False) -> dict:
    """Run the canary search watch_plan showed, after the user agreed to it. Uses the GITHUB_TOKEN set in this
    server's environment for GitHub (never pass a token as an argument). Writes leads to the vault; files nothing."""
    v = find_vault(project_dir)
    plan = _watch_plan(v, sources, include_core)
    if confirm_code != _confirm_code("watch", plan["sources"], include_core, plan["will_send"]):
        raise ValueError("confirm_code doesn't match the current plan: run watch_plan again and show the user")
    return watch.run(v, plan["sources"], token=os.environ.get("GITHUB_TOKEN"), include_core=include_core,
                     accept_disclosure=True)  # the user accepted the disclosure shown in watch_plan


@mcp.tool()
@_safe
def watch_leads(project_dir: str) -> list:
    """Leads found by earlier canary searches, for the user to review. Read-only."""
    return watch.leads(find_vault(project_dir))


def main():
    mcp.run()


if __name__ == "__main__":
    main()
