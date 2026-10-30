<!-- Draft for r/gamedev. Not posted. Check the subreddit's self-promotion rules first. -->
# I built a free, local toolkit for proving you made your game and handling clones. Here's what it can't do.

**Title option:** "Free open-source anti-clone toolkit for indie devs (it can't stop copying, and says so)"

The honest part first: no tool can stop someone, or an AI, from decompiling your shipped game or rebuilding it from footage. IndieWard doesn't try to block anything. Its similarity scores can't show whether an AI was used. It isn't legal advice.

What it does is cut the time between "there's a clone of my game" and "a correct takedown notice is ready to send":

- Registers your assets, code and builds with a signed certificate and two independent timestamps.
- Adds invisible watermarks to images, audio and video, plus inert trap markers to builds (Godot, Unity, UE5, Roblox, web).
- Checks a suspect build, store page or files: one score per category, labelled Strong, Supporting or Weak. A report built only on mechanics says not to file.
- Drafts DMCA or trademark notices and checklists for Steam, itch.io and Roblox. It never sends them; you do.
- Before anything is registered, you have to prove you control the game's store page. That makes it harder to use against the real creator.

Everything runs on your machine. No account, no telemetry. MIT licensed.

Install (Python 3.10+, FFmpeg):

```
pipx install "indieward[mcp] @ git+https://github.com/JEBANERD/indieward"
indieward doctor
```

Repo and creator guide: https://github.com/JEBANERD/indieward

I'd love feedback from anyone who has dealt with a clone. What did you wish you'd had ready?

Tip jar, if you want: [TIP JAR LINK]
