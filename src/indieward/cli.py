"""IndieWard command line. Run `indieward --help`."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path

from . import __version__


def _out(obj, as_json: bool):
    if as_json:
        print(json.dumps(obj, indent=2, ensure_ascii=False, default=str))
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, (dict, list)):
                print(f"{k}:")
                print("  " + json.dumps(v, ensure_ascii=False, default=str)[:2000])
            else:
                print(f"{k}: {v}")
    elif isinstance(obj, list):
        for x in obj:
            _out(x, False)
            print()
    else:
        print(obj)


def status(v) -> dict:
    from . import payload as pl

    p = v.project()
    s = {
        "project": p["name"], "creator": p["creator"], "vault": str(v.dir),
        "verification_code": p["verify_code"],
        "verified": v.is_verified(),
        "verified_links": [f"{r['store']}: {r['url']} ({r['method']}, {r['verified_at']})"
                           for r in v.verifications() if r["status"] == "verified"],
        "assets": v.db.execute("SELECT COUNT(*) FROM assets").fetchone()[0],
        "builds": v.db.execute("SELECT COUNT(*) FROM builds").fetchone()[0],
        "pending_timestamps": v.db.execute(
            "SELECT COUNT(*) FROM timestamps WHERE status IN ('pending','failed')").fetchone()[0],
        "checks": v.db.execute("SELECT COUNT(*) FROM checks").fetchone()[0],
        "takedowns": [dict(r) for r in v.db.execute("SELECT check_id, store, status, created_at FROM takedowns")],
    }
    if p["first_published"]:
        d = dt.date.fromisoformat(p["first_published"])
        deadline = d + dt.timedelta(days=90)
        left = (deadline - dt.date.today()).days
        s["copyright_window"] = (
            f"Register with the US Copyright Office by about {deadline} ({left} days left) to keep statutory damages "
            f"and attorney's fees available (17 U.S.C. 412). The statute says 3 months; file earlier to be safe."
            if left >= 0 else f"The 3-month window after first publication ({p['first_published']}) has passed. "
            f"Register anyway: it's still required before suing, and it protects against future infringement.")
    else:
        s["copyright_window"] = "Set your first publication date: indieward published YYYY-MM-DD"
    if not s["verified"]:
        s["next_step"] = (f"Paste {p['verify_code']} into your game's public store description, then run "
                          f"`indieward verify page --store itch|steam|roblox --url <page>`.")
    _ = pl
    return s


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="indieward", description="IndieWard: prove you made it, spot clones, draft takedowns.")
    ap.add_argument("--version", action="version", version=f"indieward {__version__}")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("-C", "--project", default=".", help="game project folder (default: current folder)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("init", help="create a vault in this game project")
    a.add_argument("--name", required=True, help="game name")
    a.add_argument("--creator", required=True, help="your name or studio's legal name")
    a.add_argument("--email", help="contact email for notices")
    a.add_argument("--passphrase-env", help="env var holding a passphrase to encrypt your signing key")

    sub.add_parser("doctor", help="check this machine is ready (Python, FFmpeg, OpenSSL, ...); prints fixes")
    sub.add_parser("status", help="project, verification, deadlines, takedowns")

    a = sub.add_parser("verify", help="prove you control the game's store page")
    vs = a.add_subparsers(dest="method", required=True)
    b = vs.add_parser("page"); b.add_argument("--store", required=True, choices=["steam", "itch", "roblox"]); b.add_argument("--url", required=True)
    b = vs.add_parser("itch-key"); b.add_argument("--url", required=True); b.add_argument("--key", default=os.environ.get("ITCH_API_KEY"))
    b = vs.add_parser("steam-key"); b.add_argument("--url", required=True); b.add_argument("--key", default=os.environ.get("STEAM_PUBLISHER_KEY"))

    a = sub.add_parser("published", help="set the game's first publication date (YYYY-MM-DD)")
    a.add_argument("date")

    a = sub.add_parser("register", help="register files or folders (hash, watermark, fingerprint)")
    a.add_argument("paths", nargs="+")
    a.add_argument("--category", choices=["art", "ui", "logo", "audio", "video", "code", "text", "other"])
    a.add_argument("--no-watermark", action="store_true")
    a.add_argument("--out", help="where watermarked copies go (default: indieward_out/)")
    a.add_argument("--keep-copy", action="store_true", help="also keep a copy of each original in the vault")

    a = sub.add_parser("traps", help="trap markers for builds")
    ts = a.add_subparsers(dest="action", required=True)
    b = ts.add_parser("new"); b.add_argument("--label", required=True); b.add_argument("--engine", default="generic", choices=["godot", "unity", "ue5", "roblox", "web", "generic"]); b.add_argument("--out")
    b = ts.add_parser("verify"); b.add_argument("--build", required=True); b.add_argument("path")
    ts.add_parser("list")
    ts.add_parser("rotate-core", help="start new core traps (after a package revealed the old ones)")

    a = sub.add_parser("build", help="register an exported build (fingerprints + trap check)")
    bs = a.add_subparsers(dest="action", required=True)
    b = bs.add_parser("register"); b.add_argument("--build", required=True); b.add_argument("path")

    a = sub.add_parser("cert", help="issue or verify a signed, timestamped certificate")
    cs = a.add_subparsers(dest="action")
    b = cs.add_parser("verify"); b.add_argument("file"); b.add_argument("--tsa-ca", help="TSA CA certificate (e.g. FreeTSA's cacert.pem) to check the token's signature")
    a.add_argument("--no-stamp", action="store_true")

    a = sub.add_parser("stamp", help="finish pending timestamps")
    a.add_argument("--retry", action="store_true", required=True)

    a = sub.add_parser("check", help="check a suspect build, files or store page")
    a.add_argument("paths", nargs="*")
    a.add_argument("--store-url"); a.add_argument("--page-file"); a.add_argument("--name", help="the suspect game's name")
    a.add_argument("--mechanics", nargs="*")

    a = sub.add_parser("package", help="build a takedown package from a check (drafts only)")
    a.add_argument("--check", required=True)
    a.add_argument("--stores", help="comma list; default: the stores your --url links are on")
    a.add_argument("--claim", default="copyright", choices=["copyright", "trademark"])
    a.add_argument("--url", action="append", help="suspect URL(s) to name in the notice")
    a.add_argument("--registration", help="US Copyright Office registration number")
    a.add_argument("--override-weak", action="store_true",
                   help="build a package even though the check advises against filing (asks you to confirm)")

    a = sub.add_parser("takedown", help="log what you sent")
    tds = a.add_subparsers(dest="action", required=True)
    b = tds.add_parser("sent"); b.add_argument("--check", required=True); b.add_argument("--store", required=True); b.add_argument("--note")
    tds.add_parser("list")

    a = sub.add_parser("docs", help="document locker: registrations, licenses, contracts")
    ds = a.add_subparsers(dest="action", required=True)
    b = ds.add_parser("add"); b.add_argument("file"); b.add_argument("--kind", required=True, choices=["copyright_registration", "trademark", "license", "contract", "correspondence", "other"]); b.add_argument("--title", required=True)
    ds.add_parser("list")

    a = sub.add_parser("common", help="index shared material so it never counts as copying")
    a.add_argument("action", choices=["add"]); a.add_argument("path")

    a = sub.add_parser("mechanics", help="list your game's mechanics (Weak category)")
    a.add_argument("action", choices=["set"]); a.add_argument("items", nargs="+")

    a = sub.add_parser("detect", help="look for your watermark in one file")
    a.add_argument("file")

    a = sub.add_parser("footage", help="public footage helpers")
    fs = a.add_subparsers(dest="action", required=True)
    b = fs.add_parser("burn-in"); b.add_argument("src"); b.add_argument("dst"); b.add_argument("--text", required=True)
    b = fs.add_parser("preview"); b.add_argument("src"); b.add_argument("dst"); b.add_argument("--max-height", type=int, default=720)

    a = sub.add_parser("signals", help="print AI-use reservation files (signals, not blocks)")
    a.add_argument("which", choices=["robots", "cawg", "tdmrep"])

    sub.add_parser("stores", help="show each store's takedown channel and its official source")

    args = ap.parse_args(argv)
    try:
        return _run(args)
    except Exception as e:  # friendly one-line errors for expected failures
        from .package import WeakEvidence
        from .vault import NotVerified, VaultMissing
        from .verify import VerifyError

        if isinstance(e, (NotVerified, VaultMissing, VerifyError, WeakEvidence, FileExistsError, ValueError)):
            print(f"indieward: {e}", file=sys.stderr)
            return 2
        raise


def _run(args) -> int:
    from . import certificate, check, package, registry, signals, stores, timestamp, traps, util, verify
    from .vault import Vault, find_vault

    j = args.json
    if args.cmd == "init":
        pw = os.environ.get(args.passphrase_env) if args.passphrase_env else None
        v = Vault.init(args.project, args.name, args.creator, args.email, pw)
        _out(status(v), j)
        return 0
    if args.cmd == "signals":
        print({"robots": signals.robots_txt, "cawg": signals.cawg_training_mining, "tdmrep": signals.tdm_rep_header}[args.which]())
        return 0
    if args.cmd == "doctor":
        from . import doctor

        r = doctor.run(args.project)
        print(json.dumps(r, indent=2)) if j else print(doctor.format_report(r))
        return 0 if r["ok"] else 1
    if args.cmd == "stores":
        _out(stores.STORES, j)
        return 0
    if args.cmd == "footage":
        from . import wm_video

        if args.action == "burn-in":
            _out(wm_video.burn_in(args.src, args.dst, args.text), j)
        else:
            wm_video.preview(args.src, args.dst, args.max_height)
            _out({"preview": args.dst}, j)
        return 0

    v = find_vault(args.project)
    if args.cmd == "status":
        _out(status(v), j)
    elif args.cmd == "verify":
        if args.method == "page":
            r = verify.verify_page(v, args.store, args.url)
        elif args.method == "itch-key":
            if not args.key:
                raise ValueError("pass --key or set ITCH_API_KEY")
            r = verify.verify_itch_key(v, args.url, args.key)
        else:
            if not args.key:
                raise ValueError("pass --key or set STEAM_PUBLISHER_KEY")
            r = verify.verify_steam_key(v, args.url, args.key)
        _out(r, j)
    elif args.cmd == "published":
        dt.date.fromisoformat(args.date)
        v.set_first_published(args.date)
        _out(status(v), j)
    elif args.cmd == "register":
        res = []
        for p in args.paths:
            res += registry.register_path(v, p, args.category, not args.no_watermark, args.out, args.keep_copy)
        _out(res, j)
        if not j:
            print("Next: `indieward cert` to sign and timestamp a certificate covering these files.")
    elif args.cmd == "traps":
        if args.action == "new":
            r = traps.generate(v, args.label, args.engine)
            if args.out:
                traps.write_snippets(v, r["build_id"], args.out, args.engine)
                r["snippets"] = args.out
            _out(r, j)
        elif args.action == "verify":
            _out(traps.verify_build(v, args.build, args.path), j)
        elif args.action == "rotate-core":
            _out({"core_rotation": traps.rotate_core(v),
                  "next": "New builds get new core traps. Old builds keep theirs and still match."}, j)
        else:
            _out([{k: r[k] for k in ("id", "label", "engine", "registered_at", "verified_at", "verify_result")}
                  for r in v.db.execute("SELECT * FROM builds ORDER BY registered_at")], j)
    elif args.cmd == "build":
        _out(registry.register_build(v, args.build, args.path), j)
    elif args.cmd == "cert":
        if args.action == "verify":
            _out(certificate.verify(args.file, args.tsa_ca), j)
        else:
            _out(certificate.issue(v, do_stamp=not args.no_stamp), j)
    elif args.cmd == "stamp":
        _out(timestamp.retry_pending(v), j)
    elif args.cmd == "check":
        if not (args.paths or args.store_url or args.page_file):
            raise ValueError("give suspect files/folders, --store-url or --page-file")
        r = check.run(v, args.paths, args.store_url, args.page_file, args.name, args.mechanics)
        _out(r, j)
        if not j:
            print(f"\n{util.DISCLAIMER}\nOpen the report: {r['report_html']}")
    elif args.cmd == "package":
        if args.override_weak:
            if not sys.stdin.isatty():
                raise ValueError("--override-weak needs you at an interactive terminal to confirm it.")
            ans = input("This check advises against filing. Type I UNDERSTAND THE RISK to build a package anyway: ")
            if ans.strip() != "I UNDERSTAND THE RISK":
                raise ValueError("not confirmed; no package built")
        stores_list = [s.strip() for s in args.stores.split(",")] if args.stores else None
        r = package.build(v, args.check, stores_list, args.claim, args.url, args.registration, args.override_weak)
        _out(r, j)
        if not j:
            print("\nNothing was sent. Read BEFORE_YOU_SEND.md, then send each draft from your own account.")
    elif args.cmd == "takedown":
        if args.action == "sent":
            package.mark_sent(v, args.check, args.store, args.note)
        _out([dict(r) for r in v.db.execute("SELECT * FROM takedowns ORDER BY id")], j)
    elif args.cmd == "docs":
        if args.action == "add":
            import shutil

            src = Path(args.file)
            sha = util.sha256_file(src)
            dst = v.path("docs", f"{sha[:12]}_{src.name}")
            shutil.copy2(src, dst)
            v.db.execute("INSERT INTO docs (kind,title,path,sha256,added_at) VALUES (?,?,?,?,?)",
                         (args.kind, args.title, v.rel(dst), sha, util.now_iso()))
            v.db.commit()
        _out([dict(r) for r in v.db.execute("SELECT kind,title,sha256,added_at FROM docs ORDER BY id")], j)
    elif args.cmd == "common":
        _out(check.add_common(v, args.path), j)
    elif args.cmd == "mechanics":
        check.set_setting(v, "mechanics", args.items)
        _out({"mechanics": args.items}, j)
    elif args.cmd == "detect":
        _out(detect_file(v, args.file), j)
    return 0


def detect_file(v, path) -> dict:
    """Check one file against every registered mark of the same kind."""
    import numpy as np

    from . import mediaio, registry, util, wm_audio, wm_image, wm_video

    kind = util.kind_for(path)
    hits = []
    for r in registry.assets(v, kind):
        if not r["wm_payload"]:
            continue
        p = int(r["wm_payload"], 16)
        if kind == "image":
            m = wm_image.match_array(wm_image.load_rgb(path)[0], p, np.load(v.path(r["ref_path"])).astype(np.float32))
        elif kind == "audio":
            d, sr = mediaio.read_audio(path)
            m = wm_audio.match_array(d, sr, p, np.load(v.path(r["ref_path"])).astype(np.float64))
        elif kind == "video":
            m = wm_video.match_file(path, p)
        else:
            continue
        if m["detected"]:
            hits.append({"registered": r["name"], "record": f"{r['record_id']:010x}", **m})
    return {"file": str(path), "kind": kind, "detected": bool(hits), "matches": hits}


if __name__ == "__main__":
    sys.exit(main())
