# IndieWard

Free, open-source anti-clone toolkit for indie game developers. It runs on your own machine and never sends anything for you.

- **Prove you had it first:** register art, audio, video, code, story text and builds. Each gets a SHA-256 hash in a certificate signed with your key and timestamped by two independent services (an RFC 3161 authority, and OpenTimestamps, which anchors in Bitcoin once you upgrade the proof with the official `ots` client).
- **Mark what you publish:** invisible watermarks for images, audio and video (IW-Mark v1, an open format; each mark carries an ID plus a MAC only your key can produce). Visible burn-in marks and low-res previews for footage.
- **Trap markers in builds:** inert made-up strings, constants, a dead function and a tiny hidden image, recorded privately. Finding one inside a suspect's files is near-proof they ripped your build, even with redrawn art.
- **Check a suspect:** traps, watermarks, and fingerprints (code winnowing, perceptual image hashes, audio landmarks, text matching, video frames) produce a 0-100 score per category, each labeled **Strong**, **Supporting** or **Weak** as a basis for filing, with matches shown side by side.
- **Takedown package:** signed certificate, evidence, a pre-filled DMCA (or trademark) notice, and a pre-addressed `.eml` draft plus checklist for Steam, itch.io and Roblox. **You** review and send it.
- **Claude plugin:** skills, an evidence-review agent and guardrail hooks that guide you through all of it (`plugin/`).

## What it can't do (read this)

- **Nothing stops an AI, or a person, from decompiling a shipped game or rebuilding one from footage.** A build has to run on the player's machine, so everything needed to read it is there. Footage is pixels. IndieWard makes proof cheap and filing fast; it doesn't block anything.
- Watermarks can be stripped and don't survive AI regeneration or redraws. Traps can be found and removed by a careful cloner. Fingerprints miss full re-implementations.
- A score measures similarity to your registered work. It **can't show whether an AI was used** or what any AI read: nobody can see another party's prompts or logs. It's evidence for you to weigh, **not a legal finding**.
- Game mechanics aren't protected by copyright. Reports built only on mechanics say so and advise against filing.
- Not legal advice.

## Install

Needs Python 3.10+ and [FFmpeg](https://ffmpeg.org/download.html) (for audio and video). `openssl` (ships with Git for Windows, macOS, Linux) is used for RFC 3161 timestamps.

```
pipx install "indieward[mcp]"        # or: pip install "indieward[mcp]"
indieward --help
```

From source:

```
git clone https://github.com/JEBANERD/indieward && cd indieward
pip install -e ".[mcp,dev]"
```

## Quick start

```
cd MyGame
indieward init --name "My Game" --creator "My Studio LLC" --email me@example.com
indieward status                       # shows your verification code
# paste the code into your game's public store description, then:
indieward verify page --store itch --url https://you.itch.io/my-game
indieward published 2026-10-01         # first publication date (tracks the 3-month copyright window)
indieward register art --category art
indieward register ui --category ui
indieward register music trailers src dialogue
indieward cert                          # signed + timestamped certificate (JSON + PDF)
indieward notice                        # visible copyright line, SPDX headers, metadata, AGENTS.md notice

indieward traps new --label "v1.0 release" --engine godot --out traps_v1
#   ...copy the snippet into the project as its comments say, export the build...
indieward build register --build <build_id> path/to/export

# a clone shows up
indieward check path/to/suspect_build.zip --store-url https://store.example/clone
indieward package --check <check_id> --url https://clone.itch.io/game   # targets only the stores your URLs are on
#   -> .indieward/packages/<check>_copyright/  (read BEFORE_YOU_SEND.md, then send from your own email)
indieward takedown sent --check <check_id> --store itch
```

Back up the `.indieward/` folder privately. It holds your keys and trap records; it's git-ignored automatically.

## The Claude plugin

```
/plugin marketplace add JEBANERD/indieward
/plugin install indieward@indieward
```

In Cowork: Customize → Plugins → Add marketplace → `JEBANERD/indieward`. Then open your game folder and say "protect my game". See [plugin/README.md](plugin/README.md).

## Tests (the end-to-end demo)

```
pip install -e ".[mcp,dev]"
pytest -q                      # core suite
pytest -q -m engine           # engine exports (needs godot / rojo / npm on PATH)
INDIEWARD_LIVE=1 pytest -q -m live   # real outside services
```

`tests/test_end_to_end.py` builds a synthetic game, registers it as a verified creator, watermarks an image, an audio clip and a video, adds trap markers to the build, survives screenshots and re-encodes, issues a certificate timestamped by a throwaway local RFC 3161 authority, then checks a planted clone (variables renamed, functions reordered, art recolored and resized, dialogue reworded, watermarks stripped, traps left in) against an unrelated game, and builds the takedown package. Network calls are stubbed; nothing leaves the machine.

## Headless build loop

`docs/headless/` holds a queue of task cards for the rest of the roadmap. `.github/workflows/claude-headless.yml` works one card per weekday run with Claude Code and opens a pull request for review; `ci.yml`, `engines.yml` (Godot, Rojo, Vite exports) and `live.yml` (real timestamp and store services) check the results. One-time setup: [docs/headless/SETUP.md](docs/headless/SETUP.md).

## Layout

```
src/indieward/    engine (CLI, MCP server, hooks)
plugin/           Claude plugin (skills, agent, hooks, MCP config)
docs/             creator guide, IW-Mark v1 spec, threat model
tests/            end-to-end and plugin tests
```

## Open and private

All code is open source (MIT). What stays private is each creator's own data on their own machine: signing and MAC keys, trap values, fingerprints and asset copies. See [docs/threat-model.md](docs/threat-model.md).

## License

MIT. See [LICENSE](LICENSE).
