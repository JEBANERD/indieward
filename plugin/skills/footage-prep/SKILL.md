---
name: footage-prep
description: Prepare trailers, gameplay clips and screenshots for public posting with IndieWard - invisible watermarks, burned-in visible marks, low-res previews, trailer cut rules and AI-use signals. Use when the user is about to post footage, make a trailer, or asks how to stop AI tools rebuilding their game from video.
---

# Footage prep

Say this plainly first, every time it's relevant: **nothing can stop an AI or a person from rebuilding a game from public footage.** Watermarks prove the footage was yours; footage discipline limits what can be recovered. Signals like robots.txt are requests that some companies honor, mostly for training crawls.

## Do
1. **Invisible watermark** the masters you'll publish: `register_assets(project_dir, [video_or_folder], "video")`. Watermarked copies go to `indieward_out/`. Detection works best on clips of 20 seconds or more; heavy compression on short clips can lose it.
2. **Visible burn-in** for each platform or press kit: `footage_burn_in(src, dst, "@studio · YouTube")`. Use a different text per platform or recipient, so a leak tells you its source. It's a deterrent, not protection: it can be painted out.
3. **Low-res public previews**: `footage_preview(src, dst, 720)`. Keep 1080p+ masters private.
4. **Cut trailers so they never show** a full level, a full UI layout, a full map, tech tree or shop screen. Show mechanics in short fragments, from cinematic angles.
5. **Press kits**: one watermarked, burned-in copy per recipient.
6. **Screenshots**: post the watermarked copies from `indieward_out/`, and register them so suspect screenshots can be compared.
7. **Platform settings**: on YouTube, leave third-party AI training access off (it's off by default) — it only binds companies that choose to honor it.
8. **Website signals**: `rights_signals("robots")` gives a robots.txt block with AI-crawler opt-outs and a Content-Signal line; `rights_signals("cawg")` gives the C2PA/CAWG "notAllowed" training assertion. Label them as signals when you hand them over. In the EU, a machine-readable opt-out has legal weight for training; in the US it doesn't.

## Don't
- Don't promise any of this blocks AI or ripping.
- Don't recommend Glaze or Nightshade as game protection: they're image-only, and researchers showed they can be detected and removed (LightShed, USENIX Security 2025).
