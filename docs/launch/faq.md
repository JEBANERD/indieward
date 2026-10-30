<!-- Short FAQ to link from launch posts. Not posted. -->
# IndieWard FAQ

**Can it stop people or AI from copying my game?**
No. A shipped build runs on the player's machine and footage is pixels, so anyone determined can copy either. IndieWard makes proof cheap and filing fast instead.

**Can it tell whether a clone was made with AI?**
No. Scores measure similarity to your registered work. Nobody can see another party's prompts or logs.

**Does it send takedowns for me?**
Never. It drafts the notice, evidence and a checklist. You review it and send it from your own account.

**Will the trap markers affect my game?**
No. They're inert values, each read at most once at startup: never shown, no gameplay or performance change, no network, no player data. Check they survived each export with `indieward build register`.

**Is a "Strong" score a legal finding?**
No. It's evidence for you to weigh. Mechanics alone aren't protected by copyright, so mechanics-only reports advise against filing. This isn't legal advice.

**Does anything leave my computer?**
A SHA-256 digest for timestamping; one read of your store page (or one store-API call with your key) to prove you control it; and, when you check a suspect, its store page and up to 12 images. Opt-in `indieward watch` sends file hashes to Software Heritage, or with `--accept-disclosure` your marker strings to GitHub or npm. No account, no telemetry.

**Which engines?**
Trap snippets for Godot, Unity, UE5, Roblox and web builds, plus a generic option.

**How do I install it?**
Python 3.10+ and FFmpeg, then:

```
pipx install "indieward[mcp] @ git+https://github.com/JEBANERD/indieward"
indieward doctor
```

**What does it cost?**
Nothing. It's MIT licensed. If it helps, there's a tip jar: [TIP JAR LINK]
