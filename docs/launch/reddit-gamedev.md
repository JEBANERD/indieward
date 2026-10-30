<!-- Draft for r/gamedev. Not posted. Check the subreddit's self-promotion rules first; replace [TIP JAR LINK]. -->
**Title:** I made a free, local toolkit for proving you made your game and checking suspected clones (it can't stop copying, and says so)

Up front: no tool can stop someone decompiling a shipped game or rebuilding it from footage. That includes AI tools. I built IndieWard to make the part after that cheaper: proof, comparison, and a takedown you send yourself.

It's an open-source (MIT) Python CLI plus an optional Claude Code plugin. It runs locally, has no account or server, and never sends anything for you.

What it does:

- Registers your files and builds in a signed certificate with two independent timestamps (RFC 3161 and OpenTimestamps).
- Adds invisible watermarks to images, audio and video, and inert trap markers to builds.
- Checks a suspect's files or store page and scores each category 0-100: traps, watermarks, code, art, text, audio, video, name, mechanics. Each score is labelled Strong, Supporting or Weak as a basis for filing.
- Drafts a DMCA or trademark notice and a checklist for Steam, itch.io or Roblox. Nothing is sent.

Honesty rules that are built in and tested:

- Every report says a similarity score can't show whether an AI was used.
- Mechanics-only matches are labelled Weak and come back as "don't file", because mechanics aren't protected by copyright.
- You have to verify you control the store page before registering anything.

Install: `pipx install "indieward[mcp]"`, then `indieward doctor`.

Repo and creator guide: https://github.com/JEBANERD/indieward

I'd love feedback from anyone who's dealt with a clone. What evidence did the store actually ask for? Not legal advice.
