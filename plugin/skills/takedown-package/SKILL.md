---
name: takedown-package
description: Build an IndieWard proof-of-work takedown package from a check - signed certificate, evidence, pre-filled DMCA or trademark notice, and pre-addressed drafts and checklists for Steam, itch.io and Roblox - for the creator to review and send themselves. Use after a check recommends filing, or when the user says "file a takedown" or "DMCA this".
---

# Takedown package (drafts only)

**Never send, submit or file anything for the user.** You don't have a tool for it, and you must not use other tools (email connectors, browsers, shell mail commands) to do it. A false DMCA notice carries legal liability for whoever files it (17 U.S.C. 512(f)). At most, with their go-ahead, create an email *draft* in their own mail app.

## Steps
1. Run the `evidence-reviewer` agent on the check first (pass the project folder and check id). Share its verdict honestly. If it says the evidence is weak, stop and explain why.
2. Ask for anything missing: the suspect's store URL(s), their US copyright registration number if they have one, copyright vs trademark claim.
3. `build_takedown_package(project_dir, check_id, "", claim, suspect_urls, registration_number)`. Leave the stores empty: the package targets only the stores the suspect URLs are on. The tool refuses checks that advise against filing. Don't look for a way around that; the CLI override exists for the user to use deliberately, with a lawyer.
4. Hand over the result:
   - `BEFORE_YOU_SEND.md`: they must read it.
   - `certificate.pdf/.json` is the EARLIEST certificate covering their work (the proof that predates the clone); `certificate_current.*` covers anything registered since.
   - Per store: the `.eml` draft (opens as an editable draft in Outlook, Apple Mail or Thunderbird; for Gmail, offer to create a draft with their Gmail connector's draft tool if they want) and `CHECKLIST.md`.
   - **Steam takes notices through a web form** (https://steamcommunity.com/dmca/create/). Its .eml is a record copy addressed to the user.
   - itch.io: support@itch.io. Roblox: copyright_agent@roblox.com (trademark: trademark_agent@roblox.com) or Rights Manager.
   - Tell them to open each store's official source page (in the checklist) to confirm the address hasn't changed.
5. They fill in placeholders (postal address, phone, signature), review every claim, and send from their own account.
6. After they confirm they sent it, `log_takedown_sent(project_dir, check_id, store)`.

## When to suggest a lawyer
A counter-notice arrives; the clone earns real money; the other side is outside the US; they're considering a lawsuit; or anything is unclear. Low-cost options: Volunteer Lawyers for the Arts, law school IP clinics, the USPTO Pro Bono Program. This is not legal advice.
