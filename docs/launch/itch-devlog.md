<!-- Draft for an itch.io devlog. Not posted. Replace [TIP JAR LINK] before posting. -->
# IndieWard: free proof-of-ownership and clone checks for indie games

**What it can't do, first.** Nothing stops a person or an AI from decompiling a shipped game or rebuilding one from footage. A build has to run on the player's machine, so everything needed to read it is there. IndieWard doesn't block copying. It makes proof cheap and filing fast.

**What it does.** IndieWard runs on your own machine and never sends anything for you.

- **Proof you had it first.** Register art, audio, video, code, story text and builds. You get a certificate signed with your key and timestamped by an RFC 3161 authority and OpenTimestamps.
- **Marks.** Invisible watermarks for images, audio and video, and inert trap markers in builds. Traps don't touch gameplay, performance, the network or player data.
- **Checks.** Compare a suspect's build, files or store page with your work. Each category gets a 0-100 score labelled Strong, Supporting or Weak. A score can't show whether an AI was used, and mechanics-only matches come back as "don't file".
- **Takedown drafts.** A pre-filled notice and checklist for Steam, itch.io or Roblox. You review it and send it yourself.

You have to prove you control your store page before registering anything, so nobody else can register your game in their name.

**Install** (Python 3.10+ and FFmpeg):

```
pipx install "indieward[mcp]"
indieward doctor
```

Then read the creator guide: https://github.com/JEBANERD/indieward/blob/main/docs/creator-guide.md

It's MIT-licensed and free. If it helps you, there's a tip jar: [TIP JAR LINK]

Not legal advice.
