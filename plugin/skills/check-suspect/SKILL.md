---
name: check-suspect
description: Check a suspected clone with IndieWard - scan a suspect build, screenshots, audio, clips or store page for the creator's trap markers and watermarks, score similarity per category, and explain the Strong/Supporting/Weak filing labels. Use when the user says "check this game", "is this a clone", or pastes a store link.
---

# Check a suspect

## Gather
Ask for whatever they have; any one is enough to start:
- the suspect's store page URL (one page is read, no crawling) or a saved copy of it,
- a downloaded build (folder, .zip, .pck, .rbxl/.rbxlx). **Only builds they obtained legitimately** (bought, free download). Never suggest pirating or bypassing DRM to get one.
- screenshots, audio or clips from the suspect.
Don't scrape stores in bulk or automate store browsing; it can break store terms.

## Run
`check_suspect(project_dir, paths, store_url, page_file, suspect_name)` then `read_check_report` for detail. Point them to the HTML report (`report_html`); it shows matches side by side.

## Explain, in this order
1. **The disclaimer, every time:** the score measures similarity to their registered work. It can't show whether an AI was used or what any AI read, because nobody can see another party's prompts or logs. It's evidence to weigh, not a legal finding.
2. **Trap markers and watermarks found** (the strongest signals of a direct rip).
3. **Each category with its label:**
   - Strong: trap markers, art, story/text, code.
   - Supporting: UI, audio, name/logo, video.
   - Weak: mechanics only. Game rules and mechanics aren't protected by copyright (17 U.S.C. 102(b)).
4. **The recommendation** (`file`, `review`, `do_not_file`). If the report rests only on mechanics, say clearly: don't file; it would likely be rejected and hurts credibility with the store.
5. **What to double-check:** matches on shared asset packs, free fonts or SFX, or engine template code don't count. Offer `add_common_material` for those, then re-run.

Never call a suspect "infringing" or "stolen" as a conclusion. Say "the evidence shows X matches Y".

If the recommendation is `file`, offer the `takedown-package` skill.
