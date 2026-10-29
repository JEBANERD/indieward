# Plugin directory listing (draft)

Copy for Anthropic's plugin directory submission. Jasper submits; nothing here has been sent.

Validation: `claude plugin validate plugin --profile directory --strict` passes with nothing to report (Claude Code 2.1.312). The directory also runs a safety scan and policy review that the local command doesn't.

## Name
IndieWard

## One-line
Prove you made your indie game, spot clones, and draft takedowns you send yourself.

## Description
IndieWard helps indie game developers protect their work from clones on Steam, itch.io and Roblox. It runs on your machine through a local, open-source engine (MIT).

- **Register your game**: signed, timestamped proof of what you had and when, after you verify you own the store page.
- **Mark your work**: invisible watermarks for art, audio and video, and inert trap markers in builds that don't touch gameplay, performance, the network or player data.
- **Check a suspect**: compare a suspected clone's store page, build, screenshots, audio or clips against your registered work, with Strong / Supporting / Weak labels for each category. Similarity can't show whether an AI was used, and mechanics-only matches come back as "don't file".
- **Prepare a takedown**: a skeptical evidence-review agent first, then pre-filled DMCA or trademark drafts and checklists for each store.

IndieWard never sends email, submits forms or files anything for you. You review and send every notice from your own account. It can't stop anyone copying or decompiling a game; it makes proof cheap and filing fast. Not legal advice.

Requires Python 3.10+ and FFmpeg: `pipx install "indieward[mcp]"`.

## Category / keywords
Suggested: game development (pick the closest category the form offers). Keywords from plugin.json: game-dev, copyright, dmca, anti-clone, watermark, indie.

## Screenshots to capture (Jasper)
1. "Protect my game" in Claude Code: the `protect-setup` skill verifying a store link and issuing a certificate.
2. A check report showing per-category scores with Strong / Supporting / Weak labels and the similarity disclaimer.
3. A mechanics-only check returning "don't file".
4. The `evidence-reviewer` agent's verdict before a package is built.
5. A takedown package folder: certificate, evidence and the unsent notice draft.
6. The hook blocking an attempt to send a notice for the user.

Use a test game or your own game; don't show real trap values, API keys or a real suspect's name.

## Privacy notes
- **Local only.** The vault, keys, registrations, check reports and packages stay in your project folder (`.indieward/`, `indieward_out/`). IndieWard has no account, server or telemetry and collects no data.
- **Network requests it makes, only when you run the matching step:**
  - Timestamping: only a SHA-256 digest goes to FreeTSA and the OpenTimestamps calendars. Offline, the timestamp stays pending.
  - Store ownership: one request to the store page or official store API you name. A Steamworks or itch.io API key, if you choose that method, is used once and never stored.
  - Checking a suspect: one read of the suspect's store page and up to 12 of its images. No crawling.
- **No sending.** No tool sends email, submits forms or contacts stores, and a PreToolUse hook tries to stop Claude doing so with other tools (best effort; you can turn hooks off).
- **Traps** are inert values that never touch the network or player data.
