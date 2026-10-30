# IndieWard plugin for Claude

Guided protection for indie games, on top of the open-source IndieWard engine.

**What it does:** walks you through registering your game (signed, timestamped proof of what you had and when), invisible watermarks for art, audio and video, trap markers in builds, checks against suspected clones with Strong / Supporting / Weak filing labels, and takedown drafts for Steam, itch.io and Roblox.

**What it never does:** send email, submit forms or file anything for you. You review and send every notice from your own account.

**What it can't do:** stop anyone, human or AI, from copying or decompiling a game or rebuilding it from footage. It makes proof cheap and filing fast.

## Install

1. Install the engine (needs Python 3.10+ and FFmpeg):
   ```
   pipx install "indieward[mcp]"
   ```
2. Add the plugin:
   - Claude Code: `/plugin marketplace add JEBANERD/indieward`, then `/plugin install indieward@indieward`
   - Cowork: Customize → Plugins → Add marketplace → `JEBANERD/indieward`, then install **indieward**
3. Open your game folder and say "protect my game".

## Contents

- MCP server `indieward-mcp` (local, stdio; no send tool)
- Skills: `protect-setup`, `add-traps`, `footage-prep`, `check-suspect`, `takedown-package`, `clone-response`
- Agent: `evidence-reviewer` (skeptical review before any package)
- Hooks: tries to stop Claude from sending takedown notices or filling store forms for you; tries to stop Claude editing, moving or deleting your vault's keys, `vault.db` and certificates (reading is fine, and IndieWard's own tools still write there), including with `git clean -x` and `git stash --all`, which remove gitignored files like `.indieward`; shows vault status at session start. The guardrail hooks are best effort, not a guarantee: they match commands and paths, so a cleverly built command can slip past, and you can turn hooks off. Keep your own backup of `.indieward/keys`.

Skills also work in chat; hooks and the agent run in Claude Code and Cowork.

Not legal advice. MIT licensed.
