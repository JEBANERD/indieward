# Changelog

All notable changes to IndieWard. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow [Semantic Versioning](https://semver.org/).

To release: set the same version in `pyproject.toml` and `src/indieward/__init__.py`, rename `[Unreleased]` below to `[X.Y.Z] - YYYY-MM-DD` (and start a new empty `[Unreleased]`), merge, then `git tag vX.Y.Z && git push origin vX.Y.Z`. The `release` workflow refuses a tag whose version or changelog section doesn't match.

## [Unreleased]

### Added
- `indieward doctor` (and an MCP tool) checks Python, FFmpeg, OpenSSL and the vault folder, and prints one fix command per problem. Windows-first install steps in the README.
- `indieward traps inject` hides a build's trap values in your own localization CSV, JSON or PO files. Data tables and JSON lists need `--rows`.
- `indieward notice` prints a visible copyright/licence notice (credits line, SPDX headers, platform metadata, AGENTS.md). Checks now note when a copied work's notice was removed.
- `indieward watch`: opt-in canary search for your markers, by hash on Software Heritage and, with `--accept-disclosure`, by text on GitHub and npm.
- Built-in common-material index (popular JS game libraries and licence texts), so bundling the same library isn't counted as copying.
- UE5 guide and `scripts/ue5_check.ps1`, Godot export guidance, and a Rojo-built `.rbxl` test fixture.
- Static guide site builder (`site/build.py`): no scripts, no trackers.
- Plugin hooks stop AI tools editing or deleting the vault, including through `git clean -x` and `git stash --all` when the repo holds a vault.
- Launch post drafts in `docs/launch/`.
- Release workflow: GitHub release with sdist, wheel, CycloneDX SBOM and signed build provenance; PyPI trusted publishing once enabled.

### Changed
- Image matching is vectorized: 2,000 × 2,000 comparisons in a few seconds.
- Code fingerprints pick comment rules by file type, so minified JS keeps its code. Re-register JS, C#, Lua and Python builds made before this.
- The creator guide covers code signing, licence choice, visible notices, EU decompilation rules and differences between courts.

### Fixed
- OpenTimestamps proofs keep their calendar after `ots upgrade`.
