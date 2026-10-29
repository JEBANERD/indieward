---
name: clone-response
description: Step-by-step playbook for when a clone of the user's game shows up on Steam, itch.io or Roblox - capture evidence, check it, register copyright if needed, prepare drafts, track counter-notices, and know when to get a lawyer. Use when the user says "someone cloned my game", "I found a copy of my game", or similar.
---

# A clone showed up

Stay calm and practical. Move in this order; the goal is a complete, honest package today.

1. **Capture evidence now**, before it changes: the suspect's store URL, screenshots of the page, and an archive copy (they can use the Wayback Machine's "Save Page Now" at https://web.archive.org/ themselves). Note the date and time.
2. **Don't contact or threaten the cloner**, and don't leave public accusations or review-bomb. It can backfire legally and alert them.
3. **Run a check** with the `check-suspect` skill (store page, plus any build, screenshots, audio or clips they got legitimately).
4. **Read the labels.** File only on Strong evidence (traps, art, text, code), backed by Supporting. Mechanics alone: don't file.
5. **Register copyright now if they haven't** (eCO: https://www.copyright.gov/registration/). It's required before suing over a US work, and within 3 months of publication it keeps statutory damages and fees available.
6. **Build the package** with the `takedown-package` skill and have them send it from their own account, to each store where the clone is listed. Steam uses its web form.
7. **Log it** (`log_takedown_sent`) and keep the store's reply.
8. **Counter-notice?** The store may restore the listing in 10-14 business days unless they file suit (17 U.S.C. 512(g)). That's the moment for a lawyer.
9. **Re-uploads:** run a new check on each one; reuse the same certificate.
10. **Next build:** if a package revealed core traps, run `indieward traps rotate-core`, then add new traps with the `add-traps` skill.

See a lawyer when: there's a counter-notice, real money involved, a cloner outside the US, or a lawsuit on the table. Low-cost help: Volunteer Lawyers for the Arts, law school IP clinics, USPTO Pro Bono Program. Not legal advice.
