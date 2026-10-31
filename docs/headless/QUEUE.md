# Headless queue

The headless worker takes the first `todo` row whose dependencies are `done`. Jasper sets a card to `done` after merging its PR (or asks `@claude` in the PR to do it).

Statuses: `todo` · `in-review` · `done` · `blocked` · `needs-jasper` (needs his hands; the worker skips it)

| Id | Card | Phase | Status | Depends | Size |
| --- | --- | --- | --- | --- | --- |
| P1-00 | Replace the placeholder repo slug `indieward/indieward` with this repo's | 1 | done | – | S |
| P1-01 | CI green on Linux, Windows, macOS | 1 | done | P1-00 | M |
| P1-02 | Live services green (FreeTSA, OpenTimestamps format, Steam/Roblox/itch shapes) | 1 | done | P1-01 | M |
| P1-03 | `indieward doctor` + Windows-first install docs | 1 | done | P1-01 | S |
| P1-04 | Dogfood on one of Jasper's real games | 1 | needs-jasper | P1-03 | – |
| P2-01 | Godot export: traps survive (engines/godot green) | 2 | done | P1-01 | M |
| P2-02 | Rojo .rbxlx and .rbxl: traps survive (engines/rojo green) | 2 | done | P1-01 | M |
| P2-03 | Unity IL2CPP via GameCI (needs a Unity licence secret) | 2 | needs-jasper | P1-01 | L |
| P2-04 | UE5 local trap-check script + guide | 2 | done | P1-01 | S |
| P2-05 | Optional TrustMark image backend (publicly readable marks) | 2 | needs-jasper | P1-01 | L |
| P2-06 | Research + prototype AudioSeal / Video Seal backends | 2 | needs-jasper | P2-05 | L |
| P2-07 | Vectorized image matching (2,000 × 2,000 in under 10 s) | 2 | done | P1-01 | M |
| P2-08 | Default common-material index (popular JS libraries, licence texts) | 2 | done | P2-07 | M |
| P2-09 | Trap camouflage: inject traps into the creator's own data files, not a separate snippet | 2 | done | P2-01 | M |
| P2-10 | `indieward notice`: visible copyright / licence metadata (CMI) + factual AGENTS.md notice | 2 | done | P1-01 | S |
| P2-11 | Hook: stop AI tools editing or deleting the vault (keys, vault.db, certs) | 2 | done | P1-01 | S |
| P2-12 | Guide update: code signing, licence choice, CMI, EU decompilation, Third Circuit note | 2 | done | P2-10 | S |
| P2-13 | Hook: stop `git clean -x` / `git stash --all` wiping the gitignored vault | 2 | done | P2-11 | S |
| P2-14 | Pick code-comment rules by file type (minified JS is nearly invisible to code checks) | 2 | done | P2-08 | M |
| P2-15 | MCP tool for `indieward notice` (returns text; writes no files) | 2 | done | P2-10 | S |
| P3-05 | IndieWard name + fork policy (trademark the name so unsafe forks can't use it) | 3 | needs-jasper | P1-00 | – |
| P4-01 | Canary monitoring via official code-search APIs (web and open-source games) | 4 | done | P2-10 | M |
| P3-01 | Static guide site + Cloudflare Pages deploy workflow | 3 | done | P1-01 | M |
| P3-02 | Release workflow (wheel + GitHub release; PyPI trusted publishing ready) | 3 | needs-jasper | P1-03 | S |
| P3-03 | Plugin directory submission prep (`validate --profile`, listing copy) | 3 | done | P1-00 | S |
| P3-04 | Launch post drafts (itch devlog, Reddit, Discord) | 3 | done | P3-01 | S |
| P2-16 | `traps inject` for Godot `.tres` translations and Unity Localization string tables | 2 | needs-jasper | P2-09 | M |
| P2-17 | MCP tools for `watch` and `traps inject` (plan, then apply with a confirm code) | 2 | done | P4-01 | M |
| P2-18 | More libraries in the common-material index (Babylon, React, Vue, jQuery, Kaboom, Excalibur) | 2 | done | P2-08 | M |
| P2-19 | Detect bundled libraries by their unique fingerprints (stops generic-overlap false matches) | 2 | in-review | P2-18 | S |
