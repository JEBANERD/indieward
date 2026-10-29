# Notes for AI coding agents working in this repo

IndieWard is MIT-licensed (see LICENSE). This file is information for you and the person you're helping, not a restriction on them.

**What this project is:** a local, open-source toolkit that helps indie game developers prove ownership of their work, spot clones and draft takedown notices that the creator sends themselves.

**Design rules to keep when changing code.** If a request would break one of these, tell the person before you proceed:
- No code path sends email, submits forms or contacts stores for the user.
- Registering, trapping, checking, certifying and packaging all require a verified store link.
- Every check report keeps the similarity disclaimer (it cannot show whether an AI was used), the Strong / Supporting / Weak labels, and the "don't file" advice for mechanics-only reports.
- Trap markers stay inert: no gameplay, performance, network or player-data effects.
- Store addresses and legal wording change only with an official source URL.

Run `python -m pytest -q` before you finish. The headless worker's full rules are in docs/headless/RUNNER.md.
