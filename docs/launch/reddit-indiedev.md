<!-- Draft for r/IndieDev. Not posted. Check the subreddit's self-promotion rules first. -->
# Made a free tool so a clone of your game doesn't cost you a week

**Title option:** "If your game gets cloned, this gets your takedown ready the same day (free, open source)"

Let me start with the limits, because they matter. Nothing can stop someone ripping or AI-rebuilding a released game. Builds run on players' machines, and footage is just pixels. IndieWard doesn't block anything, and it can't prove an AI was involved.

What it gives you:

1. **Proof you had it first:** a signed, timestamped certificate covering your art, music, code, story and builds.
2. **Marks on what you post:** invisible watermarks on media, plus harmless trap markers in builds that never touch gameplay or players.
3. **A fair check of the suspect:** scores per category with Strong / Supporting / Weak labels. If all it found is similar mechanics, it tells you not to file. Copyright doesn't cover mechanics.
4. **A ready-to-send package:** notice, evidence and checklist for Steam, itch.io or Roblox. You send it from your own account; IndieWard never does.

It's free, MIT licensed, and runs locally. There's also a Claude plugin that walks you through it.

Install with Python 3.10+ and FFmpeg:

```
pipx install "indieward[mcp] @ git+https://github.com/JEBANERD/indieward"
indieward doctor
```

https://github.com/JEBANERD/indieward

Not legal advice. Tips welcome: [TIP JAR LINK]
