<!-- Draft for r/IndieDev. Not posted. Check the subreddit's rules first; replace [TIP JAR LINK]. -->
**Title:** Free tool for when a clone of your game shows up: proof, checks and a takedown draft (no magic blocking)

If you've had a game cloned, you know the hard part is proving it's yours and writing a notice the store will act on.

I want to be clear about the limits first. IndieWard can't stop anyone copying your game, and nothing can, AI included. What it does:

1. **Before launch:** verify your store page, register your art, audio, code, text and builds, and get a signed, timestamped certificate. Add trap markers to each build. They're harmless made-up strings and a tiny hidden image, and they never touch gameplay or the network.
2. **When a clone appears:** run a check. You get a score per category, labelled Strong, Supporting or Weak, with matches side by side. If only mechanics match, it tells you not to file.
3. **Filing:** it builds a takedown package with a pre-filled notice and a checklist for Steam, itch.io or Roblox. You read it and send it from your own account. IndieWard never sends anything.

It's free and open source (MIT), and it runs on your machine.

```
pipx install "indieward[mcp]"
indieward doctor
```

Guide: https://github.com/JEBANERD/indieward/blob/main/docs/creator-guide.md

Tip jar if it saves you a headache: [TIP JAR LINK]

Not legal advice. Questions welcome.
