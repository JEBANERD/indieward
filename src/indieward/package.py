"""Proof-of-work takedown package: everything a store needs, drafted, never sent.

IndieWard has no code that sends email or submits forms. It writes .eml
drafts (open them in Outlook, Apple Mail or Thunderbird, or import them
into Gmail) and per-store checklists for stores that only take web forms.
You review and send from your own account. A false DMCA notice carries legal
liability for whoever files it (17 U.S.C. 512(f)).
"""
from __future__ import annotations

import csv
import io
import json
import mimetypes
import zipfile
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from pathlib import Path

from . import certificate, stores, util
from .vault import Vault


class WeakEvidence(PermissionError):
    pass


NOTICE = """Notice of copyright infringement under 17 U.S.C. 512(c)(3)

To: {store_name} designated copyright agent
Date: {date}

1. Copyrighted work(s). I am the owner, or authorized to act for the owner, of the copyrights in the video game
   "{project}" and its art, code, text and audio. {registration}
   Proof of prior possession: IndieWard certificate {cert_digest}, issued {cert_issued} and signed with my key;
   {cert_stamp} (attached: certificate.pdf and certificate.json).

2. Infringing material and its location:
   {suspect_urls}
   It reproduces my work as follows (details and side-by-side evidence in the attached check report):
{evidence_lines}

3. Contact information: {creator}, {email}, {postal}, {phone}

4. I have a good faith belief that use of the material in the manner complained of is not authorized by the
   copyright owner, its agent, or the law. I considered whether the use could be fair use before sending this
   notice.

5. The information in this notification is accurate, and under penalty of perjury, I am authorized to act on
   behalf of the owner of an exclusive right that is allegedly infringed.

Signature: /<type your full legal name>/
Name: {creator}
"""

TRADEMARK_NOTICE = """Trademark complaint

To: {store_name} trademark agent
Date: {date}

I own the mark "{project}" used for video games. {registration}
The listing at:
   {suspect_urls}
uses a confusingly similar name or logo for a competing game, which is likely to cause confusion:
{evidence_lines}

Contact: {creator}, {email}, {postal}, {phone}

I have a good faith belief that this use is not authorized by me, my agent, or the law, and the information in this
complaint is accurate.

Signature: /<type your full legal name>/
Name: {creator}
"""

BEFORE_YOU_SEND = """# Before you send

IndieWard drafted this package. It has not sent anything, and it never will. Read all of this first.

1. **Check every match yourself.** Open check_report.html. For each category, confirm the matched material is your
   original work, not a shared asset-store pack, a free font or sound library, engine template code, or something
   you licensed to others.
2. **Mechanics are not enough.** Copyright doesn't protect game rules, mechanics or ideas (17 U.S.C. 102(b)).
   Filing on mechanics alone gets rejected and hurts your credibility with the store.
3. **Consider fair use.** Courts require senders to consider fair use before sending (Lenz v. Universal, 9th Cir.
   2015). Reviews, parody and commentary can be fair use.
4. **A false claim can cost you.** Knowingly misrepresenting infringement makes you liable for damages, including
   the other side's costs and attorney's fees (17 U.S.C. 512(f)).
5. **Fill in the blanks.** Add your postal address and phone, any copyright registration number, and type your
   name as the signature. Remove anything you're not sure of.
6. **Expect a counter-notice.** If the other side files one, the store can restore the listing in 10 to 14
   business days unless you file a lawsuit (17 U.S.C. 512(g)). Registration with the US Copyright Office is
   required before suing over a US work.
7. **Re-check the address.** Store channels in this package were checked on {last_checked} against each store's
   official page (listed in the checklist). Stores change them; open the source page before you send.
8. **When to see a lawyer:** you receive a counter-notice; the clone earns real money; the other side is outside
   the US; you're thinking about a lawsuit; or anything here is unclear. Low-cost help: Volunteer Lawyers for the
   Arts, law school IP clinics, and the USPTO Pro Bono Program.

This package is not legal advice.
"""


def _evidence_lines(report: dict, claim: str = "copyright") -> list[str]:
    out = []
    for c in report["categories"]:
        if claim == "copyright" and c["key"] == "name":
            continue  # names and logos belong in a trademark complaint, not a copyright notice
        if claim == "trademark" and c["key"] not in ("name",):
            continue
        if c["score"] >= 20 and c["strength"] != "Weak":
            out.append(f"   - {c['label']} ({c['strength']}, similarity {c['score']}/100): {c['summary']}")
    if report["traps"]["count"] and claim == "copyright":
        out.append(f"   - {report['traps']['count']} hidden trap markers from my builds were found inside the "
                   f"suspect's files. These are made-up values that exist only in my game.")
    if report["watermarks"] and claim == "copyright":
        out.append(f"   - My invisible watermark was detected in {len(report['watermarks'])} of the suspect's files.")
    return out


def stores_for_urls(urls) -> list[str]:
    import urllib.parse

    out = []
    for u in urls or []:
        h = (urllib.parse.urlparse(u).hostname or "").lower()
        st = ("steam" if h in ("store.steampowered.com", "steamcommunity.com") else
              "itch" if h == "itch.io" or h.endswith(".itch.io") else
              "roblox" if h in ("www.roblox.com", "roblox.com") else None)
        if st and st not in out:
            out.append(st)
    return out


def build(vault: Vault, check_id: str, stores_list=None, claim: str = "copyright",
          suspect_urls: list[str] | None = None, registration_number: str | None = None,
          override_weak: bool = False) -> dict:
    vault.require_verified("build takedown packages")
    row = vault.db.execute("SELECT * FROM checks WHERE id=?", (check_id,)).fetchone()
    if not row:
        raise ValueError(f"unknown check {check_id}")
    report = json.loads(vault.path(row["report_path"]).read_text())
    if report["recommendation"] == "do_not_file" and not override_weak:
        raise WeakEvidence(
            "This check advises against filing (" + report["message"] + ") IndieWard won't build a package for it. "
            "If you've reviewed the evidence with a lawyer and still want one, rerun with --override-weak.")
    url_stores = stores_for_urls(suspect_urls or [report["suspect"].get("store_url")])
    if not stores_list:
        stores_list = url_stores
        if not stores_list:
            raise ValueError("Give the suspect's store URL(s) so the package only targets stores where it's listed.")
    elif url_stores:
        extra = [st for st in stores_list if st not in url_stores]
        if extra:
            raise ValueError(f"No suspect URL is on {', '.join(extra)}. Only file where the clone is actually listed.")
    proj = vault.project()
    out = vault.path("packages", f"{check_id}_{claim}")
    out.mkdir(parents=True, exist_ok=True)

    # The proof that matters is the EARLIEST certificate covering the copied work, made before the
    # clone appeared. A fresh one is added too, so the package also covers anything registered since.
    trap_builds = {t["build_id"] for t in report["traps"]["found"]}
    earliest = certificate.earliest_covering(vault, trap_builds)
    current = certificate.issue(vault, out_dir=out)
    cur_json, cur_pdf = Path(current["json"]), Path(current["pdf"])
    cur_json.rename(out / "certificate_current.json")
    cur_pdf.rename(out / "certificate_current.pdf")
    if earliest:
        (out / "certificate.json").write_bytes(Path(earliest["json"]).read_bytes())
        (out / "certificate.pdf").write_bytes(Path(earliest["pdf"]).read_bytes())
        prior = earliest
    else:
        (out / "certificate.json").write_bytes((out / "certificate_current.json").read_bytes())
        (out / "certificate.pdf").write_bytes((out / "certificate_current.pdf").read_bytes())
        prior = certificate.summary(json.loads((out / "certificate.json").read_text()))
    cert = {"digest": prior["digest"], "timestamps": prior["timestamps"]}

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["record", "category", "file", "sha256", "registered_at"])
    for a in json.loads((out / "certificate.json").read_text())["assets"]:
        w.writerow([a["record"], a["category"], a["name"], a["sha256"], a["registered_at"]])
    (out / "registration_hashes.csv").write_text(buf.getvalue())

    check_dir = vault.path("checks", check_id)
    (out / "check_report.json").write_bytes((check_dir / "report.json").read_bytes())
    (out / "check_report.html").write_bytes((check_dir / "report.html").read_bytes())
    ev_zip = out / "evidence.zip"
    with zipfile.ZipFile(ev_zip, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(check_dir / "report.html", "check_report.html")
        for f in sorted((check_dir / "evidence").glob("*")):
            z.write(f, f"evidence/{f.name}")

    disclosure = {
        "explanation": "Each trap below was generated and recorded before release. Recompute "
                       "sha256(salt|tier|kind|value) to get its commitment; the build's trap_commitment in the "
                       "certificate is sha256 of all that build's commitments joined with '|'. Only traps found in "
                       "the suspect are revealed.",
        "found": [{"build_id": t["build_id"], "tier": t["tier"], "label": t["label"], "value": t["value"],
                   "commitment": t["commitment"], "found_in": t["found_in"]} for t in report["traps"]["found"]],
    }
    if disclosure["found"]:
        found_ids = {t["id"] for t in report["traps"]["found"]}
        lists, salts = {}, {}
        for t in vault.db.execute("SELECT * FROM traps ORDER BY id").fetchall():
            if t["build_id"] in {f["build_id"] for f in report["traps"]["found"]}:
                lists.setdefault(t["build_id"], []).append(
                    util.sha256_bytes(f"{t['salt']}|{t['tier']}|{t['kind']}|{t['value']}".encode()))
                if t["id"] in found_ids:
                    salts[str(t["id"])] = t["salt"]
        for f, t in zip(disclosure["found"], report["traps"]["found"]):
            f["salt"] = salts.get(str(t["id"]))
            f["kind"] = t.get("kind")
        disclosure["build_commitment_lists"] = lists
        disclosure["explanation"] = (
            "Each trap below was generated and recorded before release. For each, sha256(salt|tier|kind|value) "
            "equals its commitment, and that commitment appears in the build's list; sha256 of the list joined "
            "with '|' is the build's trap_commitment in the timestamped certificate. Traps that weren't found "
            "stay hidden: their salts are not revealed.")
    (out / "trap_disclosure.json").write_text(json.dumps(disclosure, indent=2))
    (out / "BEFORE_YOU_SEND.md").write_text(BEFORE_YOU_SEND.format(last_checked=stores.LAST_CHECKED))

    urls = suspect_urls or [u for u in [report["suspect"].get("store_url")] if u] or ["<paste the suspect's store URL>"]
    template = NOTICE if claim == "copyright" else TRADEMARK_NOTICE
    if claim == "copyright":
        reg = (f"US Copyright Office registration number: {registration_number}." if registration_number
               else "Copyright registration: <add your registration number, or delete this line>.")
    else:
        reg = (f"US trademark registration number: {registration_number}." if registration_number
               else "Trademark registration: <add your USPTO registration or serial number, or delete this line>.")
    attachments = ["certificate.pdf", "certificate.json", "check_report.html", "evidence.zip", "trap_disclosure.json"]
    drafts = {}
    for st in stores_list:
        ch = stores.channel(st, claim)
        notice = template.format(
            store_name=ch["name"], date=util.now_iso()[:10], project=proj["name"], registration=reg,
            cert_digest=cert["digest"][:16], cert_issued=prior["issued_at"], cert_stamp=prior["stamp_sentence"],
            suspect_urls="\n   ".join(urls),
            evidence_lines="\n".join(_evidence_lines(report, claim)) or "   - <describe what was copied>",
            creator=proj["creator"], email=proj["contact_email"] or "<your email>", postal="<your postal address>",
            phone="<your phone>")
        sd = out / st
        sd.mkdir(exist_ok=True)
        (sd / f"{claim}_notice.txt").write_text(notice)
        to = ch.get("email")
        if not to:  # web-form store: the draft is a record copy to yourself
            to = proj["contact_email"] or ""
            subject = f"[Your record] {ch['name']} {claim} notice for {proj['name']}: submit via the web form"
            intro = (f"{ch['name']} takes {claim} notices through its web form, not email:\n{ch['form_url']}\n"
                     f"This draft is addressed to you as a record of what you filed. Paste the notice below into "
                     f"the form, attach the files, and keep this email.\n\n")
        else:
            subject = f"{'DMCA notice of copyright infringement' if claim == 'copyright' else 'Trademark complaint'}: {proj['name']}"
            intro = ""
        msg = EmailMessage()
        msg["To"] = to
        msg["From"] = proj["contact_email"] or ""
        msg["Subject"] = subject
        msg["Date"] = formatdate(localtime=False)
        msg["Message-ID"] = make_msgid(domain="indieward.local")
        msg["X-Unsent"] = "1"  # Outlook and others open this as an editable draft
        msg["X-IndieWard"] = "draft generated locally; never sent by IndieWard"
        msg.set_content(intro + notice)
        for name in attachments:
            p = out / name
            ctype = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
            maintype, subtype = ctype.split("/", 1)
            msg.add_attachment(p.read_bytes(), maintype=maintype, subtype=subtype, filename=p.name)
        eml = sd / f"{st}_{claim}_draft.eml"
        eml.write_bytes(bytes(msg))
        (sd / "CHECKLIST.md").write_text(_checklist(ch, claim, attachments))
        drafts[st] = {"eml": str(eml), "to": to, "channel": ch["channel"], "form_url": ch.get("form_url"),
                      "attachments": attachments}
        vault.db.execute("INSERT INTO takedowns (check_id,store,created_at,status,package_path) VALUES (?,?,?,?,?)",
                         (check_id, st, util.now_iso(), "drafted (not sent)", vault.rel(sd)))
    vault.db.commit()

    zpath = vault.path("packages", f"{check_id}_{claim}.zip")
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(out.rglob("*")):
            if f.is_file():
                z.write(f, f.relative_to(out))
    return {"package_dir": str(out), "zip": str(zpath), "drafts": drafts, "sent": False,
            "certificate_digest": cert["digest"], "certificate_issued": prior["issued_at"],
            "timestamps": cert["timestamps"]}


def _checklist(ch: dict, claim: str, attachments: list[str]) -> str:
    lines = [f"# {ch['name']}: {claim} checklist", "",
             f"Channel checked {ch['last_checked']} against: " + ", ".join(ch["sources"]), ""]
    if ch["channel"] == "web_form":
        lines += [f"1. Open the form: {ch['form_url']}",
                  "2. Paste each part of the notice (see *_notice.txt) into the matching field: the work, the "
                  "infringing URLs, your contact details, the good-faith and perjury statements, your signature.",
                  f"3. Attach or link: {', '.join(attachments)} (some forms accept links only; host the files "
                  "somewhere you control, or describe them and offer them on request).",
                  "4. Submit, then save the confirmation page and keep the draft .eml as your record."]
    else:
        lines += [f"1. Open the .eml draft in your mail app. Check it's addressed to {ch['email']}.",
                  "2. Fill in every <placeholder> in the notice. Type your full name as the signature.",
                  f"3. Confirm the attachments are there: {', '.join(attachments)}.",
                  "4. Send it from your own email account."]
        if ch.get("form_url"):
            lines.append(f"5. Or use the store's web flow instead (guide: {ch['form_url']})")
    lines += ["", "Then run `indieward takedown sent --check <id> --store <store>` to log it in your vault.", ""]
    lines += [f"- {n}" for n in ch["notes"]]
    return "\n".join(lines) + "\n"


def mark_sent(vault: Vault, check_id: str, store: str, note: str | None = None) -> None:
    vault.db.execute("UPDATE takedowns SET status='sent by creator', sent_at=?, note=? WHERE check_id=? AND store=?",
                     (util.now_iso(), note, check_id, store))
    vault.db.commit()
