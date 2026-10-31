---
name: protect-setup
description: Set up IndieWard for a game - install, create the vault, verify store ownership, register art/code/audio/video/text, issue a signed timestamped certificate, and walk through US copyright and trademark registration. Use when a creator says "protect my game", "set up IndieWard", or starts using the plugin.
---

# Protect a game: first-time setup

You are guiding an indie developer. Be plain-spoken, short, and honest about limits. IndieWard proves "I had this first" and helps file fast; it does not block copying or AI.

## 0. Check the engine is installed
Call `project_status` on the game folder. If the tool is missing or errors with "command not found", tell the user to install the engine once (their terminal, not yours, unless they ask you to run it):

```
pipx install "indieward[mcp]"      # or: pip install "indieward[mcp]"
```
FFmpeg is needed for audio and video (https://ffmpeg.org/download.html). Then restart the session.

## 1. Create the vault
`init_project(project_dir, game_name, creator_legal_name, contact_email)`. Use the legal name that will appear on notices. Then tell them:
- Their keys live in `<project>/.indieward/keys/`. **Back up the whole `.indieward` folder** somewhere private (not a public repo). If the keys are lost, old watermarks can't be validated.

## 2. Verify ownership (required)
Nothing can be registered until this passes. It makes it harder for someone to register another creator's game and file false takedowns against them. It isn't airtight (the code is open), so the certificate records how verification was done and stores can re-check it. For itch.io, only the description counts, not comments.
1. Show the `verification_code` from `project_status`.
2. The user pastes it anywhere in the game's public store description (Steam, itch.io or Roblox) and saves.
3. `verify_store_page(project_dir, store, url)`. On success they may remove the code; the certificate keeps a hash of what was seen.
Alternatives: `verify_with_itch_key` (their itch.io API key) or `verify_with_steam_publisher_key` (Steamworks publisher key). Keys are used once and never stored. Don't ask for keys unless the user prefers that route.

## 3. Register the work
`register_assets(project_dir, paths, category)` for each group:
- art (sprites, textures, key art, screenshots), ui (HUD and menu screens), logo, audio (music, SFX over 4 s get a watermark), video (trailers, clips), code (source folders), text (dialogue, lore, store copy).
Watermarked copies land in `<project>/indieward_out/`; originals are untouched. **They should ship and post the watermarked copies**, not the originals.
Tell them: registering their own screenshots matters, because suspect screenshots are compared against those.
If they use asset-store packs or engine templates, run `add_common_material` on those folders so shared material never counts as copying.

## 4. Sign and timestamp
`issue_certificate(project_dir)`. Two independent timestamps (RFC 3161 and OpenTimestamps) are requested; if offline they're pending, and `retry_timestamps` finishes them later. Re-issue after each batch of new registrations.

Optional: `copyright_notice(project_dir)` returns a visible copyright line for the credits screen, SPDX headers for source files, build metadata fields and a short AGENTS.md licence notice (pass `licence` such as `MIT` if they use one). It writes no files: show the creator the text and let them paste or save it. Visible notices can count as copyright management information, and checks report when a suspect has their code or art but not the notice.

## 5. Register copyright (strongly recommended)
Not legal advice; link, don't paraphrase the law beyond this:
- Register with the US Copyright Office through eCO: https://www.copyright.gov/registration/ . A video game is usually registered as a computer program plus audiovisual work (Circular 61: https://www.copyright.gov/circs/circ61.pdf). Source-code deposits can be redacted to protect trade secrets.
- Fees (check before filing): https://www.copyright.gov/about/fees.html . Increases were proposed in 2026.
- **Timing:** register before infringement starts or within 3 months of first publication to keep statutory damages and attorney's fees available (17 U.S.C. 412). Registration is required before suing over a US work. Call `set_first_published` so `project_status` tracks the deadline.
- Small claims up to $30,000: Copyright Claims Board, https://ccb.gov
Add the registration certificate to the vault later (`indieward docs add` in a terminal).

## 6. Trademark (if the name matters commercially)
USPTO Trademark Center: https://trademarkcenter.uspto.gov . Search first. Typical classes: 9 (downloadable game software) and 41 (online game services). Fees are per class; check the USPTO fee page. Foreign-domiciled applicants need a US attorney.

## 7. Next
- Every build: the `add-traps` skill.
- Public footage: the `footage-prep` skill.
- Found a clone: the `clone-response` skill.

Point to the full creator guide in the repo's docs/creator-guide.md for details.
