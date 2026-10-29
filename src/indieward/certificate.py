"""Signed, timestamped proof-of-ownership certificates (IndieWard certificate v1).

A certificate lists the project's verified store links, every registered
asset (SHA-256, size, registration time, watermark ID) and every build (its
trap commitment, not the traps themselves). The body is canonical JSON signed
with the creator's Ed25519 key; the digest of the signed body is then
timestamped by an RFC 3161 authority and OpenTimestamps.

What it proves: these exact files existed and were held by the holder of this
key by the timestamp's date, and that key holder had shown control of the
listed store pages. It does not prove authorship. A US copyright
registration is stronger evidence of that.
"""
from __future__ import annotations

import json
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from . import payload as pl, timestamp, util
from .vault import Vault

STATEMENT = (
    "This certificate shows that the listed files (identified by SHA-256) were held by the holder of the "
    "signing key by the time of the attached third-party timestamps, and that this key holder showed control "
    "of the listed store pages. It is evidence of possession at a point in time, not proof of authorship. It "
    "is not a copyright registration and not legal advice."
)


def build_body(vault: Vault) -> dict:
    proj = vault.project()
    pub_raw = util.unb64(proj["public_key"])
    ver = [
        {"store": r["store"], "url": r["url"], "method": r["method"], "verified_at": r["verified_at"],
         "evidence_sha256": r["evidence_sha256"], "detail": json.loads(r["detail"] or "{}")}
        for r in vault.verifications() if r["status"] == "verified"
    ]
    assets = []
    for r in vault.db.execute("SELECT * FROM assets ORDER BY id").fetchall():
        a = {"record": pl.fmt(r["record_id"]), "kind": r["kind"], "category": r["category"], "name": r["name"],
             "sha256": r["sha256"], "size": r["size"], "registered_at": r["registered_at"]}
        if r["wm_payload"]:
            a["watermark"] = {"format": "IW-Mark v1", "backend": r["wm_backend"],
                              "marked_file_sha256": r["wm_output_sha256"]}
        assets.append(a)
    builds = [
        {"build_id": r["id"], "label": r["label"], "engine": r["engine"], "registered_at": r["registered_at"],
         "manifest_sha256": r["manifest_sha256"], "trap_commitment": r["trap_commitment"]}
        for r in vault.db.execute("SELECT * FROM builds ORDER BY registered_at").fetchall()
    ]
    docs = [{"kind": r["kind"], "title": r["title"], "sha256": r["sha256"], "added_at": r["added_at"]}
            for r in vault.db.execute("SELECT * FROM docs ORDER BY id").fetchall()]
    return {
        "format": "IndieWard certificate v1",
        "issued_at": util.now_iso(),
        "creator": {"name": proj["creator"], "contact": proj["contact_email"],
                    "public_key_ed25519": proj["public_key"],
                    "key_fingerprint": util.sha256_bytes(pub_raw)[:32]},
        "project": {"id": proj["id"], "name": proj["name"], "first_published": proj["first_published"],
                    "verification_code": proj["verify_code"]},
        "verified_store_links": ver,
        "assets": assets,
        "builds": builds,
        "documents": docs,
        "statement": STATEMENT,
    }


def issue(vault: Vault, out_dir=None, do_stamp: bool = True, passphrase: str | None = None) -> dict:
    vault.require_verified("issue certificates")
    body = build_body(vault)
    canon = util.canonical_json(body)
    sig = vault.signing_key(passphrase).sign(canon)
    digest = util.sha256_bytes(canon + sig)
    cert = {**body, "signature": {"alg": "Ed25519", "value": util.b64(sig)}, "digest_sha256": digest}
    if do_stamp:
        ts = timestamp.stamp(vault, f"certificate {digest[:12]}", digest)
        cert["timestamps"] = {k: {kk: vv for kk, vv in v.items() if kk != "error"} | (
            {"error": v["error"]} if v.get("error") else {}) for k, v in ts.items()}
        for k, v in ts.items():
            tok = v.get("token")
            if tok:
                cert["timestamps"][k]["token_b64"] = util.b64(vault.path("certs", "timestamps", tok).read_bytes())
    out_dir = Path(out_dir) if out_dir else vault.path("certs")
    out_dir.mkdir(parents=True, exist_ok=True)
    jpath = out_dir / f"certificate_{digest[:12]}.json"
    jpath.write_text(json.dumps(cert, indent=2, ensure_ascii=False))
    pdf = out_dir / f"certificate_{digest[:12]}.pdf"
    render_pdf(cert, pdf)
    return {"json": str(jpath), "pdf": str(pdf), "digest": digest,
            "timestamps": {k: v.get("status") for k, v in cert.get("timestamps", {}).items()}}


def summary(cert: dict, json_path=None, pdf_path=None) -> dict:
    ts = cert.get("timestamps", {})
    r = ts.get("rfc3161", {})
    if r.get("status") == "stamped":
        stamp = f"independently timestamped by {r.get('service')} at {r.get('time')} (RFC 3161)"
    else:
        stamp = "independent timestamp still pending, so the issue date above is self-reported"
    return {"digest": cert["digest_sha256"], "issued_at": cert["issued_at"], "json": json_path, "pdf": pdf_path,
            "timestamps": {k: v.get("status") for k, v in ts.items()}, "stamp_sentence": stamp,
            "builds": {b["build_id"] for b in cert.get("builds", [])}, "n_assets": len(cert.get("assets", []))}


def earliest_covering(vault: Vault, build_ids: set[str]) -> dict | None:
    """Earliest stamped certificate in the vault that lists these builds and at least one asset."""
    found = []
    for p in sorted(vault.path("certs").glob("certificate_*.json")):
        try:
            c = json.loads(p.read_text())
        except Exception:
            continue
        if not verify(c)["valid"]:
            continue
        s = summary(c, str(p), str(p.with_suffix(".pdf")))
        if s["n_assets"] and build_ids <= s["builds"] and Path(s["pdf"]).exists():
            found.append(s)
    stamped = [s for s in found if s["timestamps"].get("rfc3161") == "stamped"]
    pool = stamped or found
    return min(pool, key=lambda s: s["issued_at"]) if pool else None


def verify(cert_or_path, tsa_ca=None) -> dict:
    cert = json.loads(Path(cert_or_path).read_text()) if not isinstance(cert_or_path, dict) else cert_or_path
    body = {k: v for k, v in cert.items() if k not in ("signature", "digest_sha256", "timestamps")}
    canon = util.canonical_json(body)
    sig = util.unb64(cert["signature"]["value"])
    pub = Ed25519PublicKey.from_public_bytes(util.unb64(cert["creator"]["public_key_ed25519"]))
    try:
        pub.verify(sig, canon)
        sig_ok = True
    except InvalidSignature:
        sig_ok = False
    digest_ok = util.sha256_bytes(canon + sig) == cert.get("digest_sha256")
    out = {"signature_valid": sig_ok, "digest_matches": digest_ok, "valid": sig_ok and digest_ok,
           "timestamps": {k: v.get("status") for k, v in cert.get("timestamps", {}).items()}}
    tok = cert.get("timestamps", {}).get("rfc3161", {}).get("token_b64")
    if tok:
        out["rfc3161_token"] = timestamp.check_token(util.unb64(tok), cert.get("digest_sha256", ""), tsa_ca)
    return out


def render_pdf(cert: dict, path) -> None:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    styles = getSampleStyleSheet()
    small = styles["BodyText"].clone("small", fontSize=7.5, leading=9)
    body = styles["BodyText"].clone("b", fontSize=9.5, leading=12)
    story = [Paragraph("Proof-of-ownership certificate", styles["Title"]),
             Paragraph(f"<b>Project:</b> {cert['project']['name']} &nbsp; <b>Creator:</b> {cert['creator']['name']}", body),
             Paragraph(f"<b>Issued:</b> {cert['issued_at']} &nbsp; <b>Certificate digest:</b> {cert['digest_sha256']}", small),
             Paragraph(f"<b>Signing key fingerprint:</b> {cert['creator']['key_fingerprint']}", small),
             Spacer(1, 8)]
    ts = cert.get("timestamps", {})
    rows = [["Timestamp", "Status", "Service", "Time"]]
    for k, v in ts.items():
        rows.append([k, v.get("status", ""), v.get("service", "") or "", v.get("time", "") or ""])
    if len(rows) > 1:
        story += [Paragraph("<b>Independent timestamps</b>", body), _tbl(rows, small, Table, TableStyle, colors),
                  Spacer(1, 8)]
    vrows = [["Store", "URL", "Method", "Verified at"]] + [
        [v["store"], Paragraph(v["url"], small), v["method"], v["verified_at"]] for v in cert["verified_store_links"]]
    story += [Paragraph("<b>Verified store links</b>", body), _tbl(vrows, small, Table, TableStyle, colors),
              Spacer(1, 8)]
    arows = [["Record", "Category", "File", "SHA-256", "Registered"]] + [
        [a["record"], a["category"], Paragraph(a["name"], small), Paragraph(a["sha256"], small), a["registered_at"]]
        for a in cert["assets"]]
    story += [Paragraph(f"<b>Registered assets ({len(cert['assets'])})</b>", body),
              _tbl(arows, small, Table, TableStyle, colors, widths=[1.0, 0.6, 1.4, 2.6, 1.2]), Spacer(1, 8)]
    if cert["builds"]:
        brows = [["Build", "Label", "Engine", "Trap commitment", "Registered"]] + [
            [b["build_id"], b["label"], b["engine"], Paragraph(b["trap_commitment"], small), b["registered_at"]]
            for b in cert["builds"]]
        story += [Paragraph("<b>Builds with trap markers</b>", body), _tbl(brows, small, Table, TableStyle, colors),
                  Spacer(1, 8)]
    story += [Paragraph("<b>What this shows</b>", body), Paragraph(cert["statement"], small), Spacer(1, 6),
              Paragraph("Verify the signature and digest with <font face='Courier'>indieward cert verify "
                        "certificate.json</font>, or any Ed25519 tool over the canonical JSON body. The RFC 3161 "
                        "token and OpenTimestamps proof are embedded in the JSON file.", small)]
    SimpleDocTemplate(str(path), pagesize=letter, leftMargin=0.6 * inch, rightMargin=0.6 * inch,
                      topMargin=0.6 * inch, bottomMargin=0.6 * inch, title="IndieWard certificate").build(story)


def _tbl(rows, style, Table, TableStyle, colors, widths=None):
    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph

    data = [[c if not isinstance(c, str) else Paragraph(c, style) for c in r] for r in rows]
    t = Table(data, colWidths=[w * inch for w in widths] if widths else None, repeatRows=1)
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                           ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eeeeee")),
                           ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    return t
