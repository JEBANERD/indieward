---
name: add-traps
description: Add IndieWard trap markers ("trap streets") to a game build and confirm they survived export, for Godot, Unity, UE5, Roblox or web games. Use before every release build, or when the user says "add traps", "trap markers" or "prepare a build".
---

# Trap markers for a build

A trap is an inert made-up value (nonsense strings, an odd float constant, a function that only returns a nonsense word, a tiny hidden image) recorded privately in the vault. If it turns up inside someone else's game, that's near-proof they copied the actual files, even if the art was redrawn.

Rules you must keep:
- Traps never change gameplay, performance, store compliance or player data. They're read once at startup and never shown, never networked. Don't modify the snippets to do anything else.
- Never print trap values in public places (commit messages, issues, store pages, chat logs that get shared). They stay secret until a takedown package reveals the ones found.

## Steps
1. `new_trap_markers(project_dir, build_label, engine)` where engine is godot | unity | ue5 | roblox | web | generic. Use a label like "v1.2 Steam release".
2. Copy the generated files into the project exactly as `README_INDIEWARD.txt` in the snippet folder says. File and class names are randomized per project, so they don't announce themselves. **Never copy the README itself into the game.** Ask before writing into their project; if they agree, do it yourself:
   - **Godot:** the `.gd` file as an Autoload; keep its folder in the export filter.
   - **Unity:** the `.cs` file + `link.xml` under Assets; the PNG under `Assets/Resources/<folder>/`. `[Preserve]` keeps IL2CPP from stripping it.
   - **UE5:** add the `.h/.cpp` to the game module and call `<Class>::Touch()` from `GameInstance::Init()`. C++ string literals end up in the executable, which can be scanned even with encrypted paks.
   - **Roblox:** the ModuleScript in ReplicatedStorage, required once from a LocalScript; the ServerStorage copy for leaked place files.
   - **Web:** import the `.js` file once from the entry point (it registers itself so bundlers keep it); serve `public/<folder>/`.
3. Export the build as usual.
4. `register_build(project_dir, build_id, exported_build_path)`. It confirms the traps survived and stores the build's fingerprints. If `ok` is false, read `advice`, fix the placement, export again and re-run.
5. `issue_certificate` so the build's trap commitment is timestamped before release.

Be honest: a careful cloner can find and remove traps. Core traps stay the same across builds to resist diffing; build traps identify which build leaked. After a takedown package reveals core traps, run `indieward traps rotate-core` before the next build. Traps prove copying, not infringement by themselves; reports pair them with the copied art, code or text.
