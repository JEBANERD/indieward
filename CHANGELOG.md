# Changelog

All notable changes to IndieWard. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow [Semantic Versioning](https://semver.org/).

To release: put the date on the version's heading (or add a new `## [x.y.z] - YYYY-MM-DD` section and bump `version` in `pyproject.toml`), merge, then push the tag `vx.y.z`. See [docs/releasing.md](docs/releasing.md).

## [0.1.0] - unreleased

First public release.

### Added
- Store verification gate: registering, trapping, checking, certifying and packaging all need a verified Steam, itch.io or Roblox page.
- Registration of art, audio, video, code, story text and builds, with a certificate signed by the creator's key and timestamped by an RFC 3161 authority and by OpenTimestamps.
- IW-Mark v1 invisible watermarks for images, audio and video (open format, 40-bit record ID plus a 24-bit MAC).
- Optional Adobe TrustMark image backend (`indieward[trustmark]`, `register --backend trustmark`): anyone can read the record ID, and only the creator's key confirms it.
- Inert trap markers for Godot, Unity, UE5, Roblox and web builds, which can be hidden in the creator's own data files.
- `indieward check`: per-category Strong / Supporting / Weak scores from traps, watermarks and fingerprints, with the similarity disclaimer and "don't file" advice for mechanics-only reports.
- Takedown packages with pre-addressed drafts for Steam, itch.io and Roblox. The creator reviews and sends them; IndieWard never sends anything.
- `indieward doctor`, visible copyright notices (`indieward notice`), opt-in canary monitoring through official code-search APIs, and the Claude plugin with guardrail hooks.
