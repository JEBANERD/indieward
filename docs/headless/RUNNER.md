# Headless runner instructions (read every run)

You are working on IndieWard unattended, in a GitHub Actions runner. Nobody can answer questions during the run. Jasper reviews your pull request later, often from his phone, with 5–20 hours a week for all his projects. Make the PR easy to review: small, tested, plainly explained.

## 1. Pick one card
1. Open `docs/headless/QUEUE.md`.
2. If a card id was given, work that card. Otherwise take the first row whose status is `todo` and whose dependencies are all `done`.
3. Skip `needs-jasper`, `blocked`, `in-review` and `done` cards.
4. Read its brief in `docs/headless/cards/<id>.md`.
5. If no card is eligible, write `.headless/BLOCKED.md` saying so, plus a one-line `.headless/TITLE.txt`, and stop.

## 2. Do the card
- Work only on that card. If you notice another problem, add it to the "Found while working" list in the PR body instead of fixing it.
- Run `python -m pytest -q` before you finish. Also run any marker the card names (`-m engine`, `-m live`).
- Commit on the current branch with clear messages. Never push, merge, tag or release; the workflow does the pushing.
- Update the card's row in `QUEUE.md` to `in-review`, then commit that too.

## 3. Write the hand-off
- `.headless/TITLE.txt`: one line, `<card id>: <what changed>`.
- `.headless/PR_BODY.md`, in this order:
  1. **What changed**, 2–5 bullets.
  2. **How it was tested**: commands and results, including anything skipped.
  3. **Jasper by hand**: exact steps, or "nothing".
  4. **Risks / limits**.
  5. **Found while working**.
- Keep it under about 40 lines.

If you can't finish, commit what's safe, set the card to `blocked`, and write `.headless/BLOCKED.md`. Say what you tried, the exact error, and the fix you propose.

## Guardrails (never break these)
- **No sending.** Never add code that sends email, submits forms or contacts stores. Never weaken the PreToolUse hook.
- **Keep the verification gate.** Registering, trapping, checking, certifying and packaging must keep requiring a verified store link.
- **Keep the honesty rules.** The similarity disclaimer stays on every report ("cannot show whether an AI was used"). Strong, Supporting and Weak labels stay. Mechanics-only reports stay `do_not_file`. Never present a deterrent as a block.
- **Inert traps.** Traps must never affect gameplay, performance, store compliance or player data, and must never touch the network.
- **Legal text.** Don't change notice wording, store addresses or legal claims unless the card asks. If it does, cite an official source URL in the PR. Never guess an address.
- **Secrets.** Never print, commit or log secrets or tokens.
- **Licences.** Only add dependencies with permissive licences (MIT, BSD, Apache-2.0, LGPL as an optional extra). Name each new one in the PR.
- **No scraping** that breaks store terms. Use official APIs or a single public page.
- **When unsure, don't guess.** Pick the conservative option, then list the question under "Jasper by hand".
