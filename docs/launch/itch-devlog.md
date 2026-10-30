<!-- Draft for an itch.io devlog. Not posted. -->
# IndieWard: free tools for when someone clones your game

First, what it can't do. Nothing can stop an AI or a person from decompiling a shipped game or rebuilding it from your trailer. A build has to run on the player's machine, so everything needed to read it is there. IndieWard doesn't block copying, and it can't tell you whether an AI was used.

What it does: it makes proof cheap and filing fast, so if a clone shows up you can answer it the same day.

- **Prove you had it first.** Register your art, audio, video, code, text and builds. You get a certificate signed with your key and timestamped by two independent services.
- **Mark what you publish.** Invisible watermarks for images, audio and video, plus visible marks and low-res previews for trailers.
- **Trap markers.** Made-up strings and constants hidden in each build. They never touch gameplay, the network or player data. Finding one in a clone is strong evidence it came from your files.
- **Check a suspect.** Scores per category, labelled Strong, Supporting or Weak. Mechanics-only matches come back as "don't file", because mechanics aren't protected by copyright.
- **Takedown drafts.** A pre-filled notice and checklist for Steam, itch.io or Roblox. IndieWard never sends anything: you review it and send it yourself.

It runs on your own computer. Free and open source (MIT). Not legal advice.

## Install

You need Python 3.10+ and FFmpeg. Then:

```
pipx install "indieward[mcp] @ git+https://github.com/JEBANERD/indieward"
indieward doctor
```

`doctor` checks your setup and prints the command to fix anything missing. Windows steps are in the README.

Source and guide: https://github.com/JEBANERD/indieward

If it helps you, you can tip here: [TIP JAR LINK]
