# Unreal Engine 5: trap markers and the local check

UE5 builds are too heavy for free CI, so you package on your own machine and run `scripts/ue5_check.ps1`. It packages a Shipping build with RunUAT and then runs `indieward build register` on it.

Traps are inert: a few made-up strings and numbers, read once at startup, never shown, no network, no player data, no effect on gameplay or performance.

## 1. Make the trap files

In the folder that holds your vault (usually the folder with your `.uproject`):

```
indieward traps new --label "v1.0 Steam" --engine ue5
```

Note the build id it prints (`b` plus 10 characters). The files are in `.indieward\traps\<build id>\`:

| File | What to do with it |
| --- | --- |
| `Source\<Class>.h`, `Source\<Class>.cpp` | Put both in your game module, e.g. `Source\<YourGame>\` (or its `Public\` / `Private\` folders). |
| `Content\<folder>\<file>.csv`, `.png` | Optional, Blueprint-only route (below). |
| `README_INDIEWARD.txt` | Read it. Never ship it. |

`<Class>` is a bland made-up name like `KofamuTable`. Keep the files as generated.

Blueprint-only project? Add any C++ class once (Tools > New C++ Class) so the project has a module, then use the C++ route. If you can't, import the CSV as a String Table and the PNG as a texture, reference both from one always-loaded Data Asset, and check against the unpacked pak instead, since encrypted paks can't be scanned.

## 2. Call `Touch()` from your GameInstance

In your GameInstance `.cpp`:

```cpp
#include "KofamuTable.h"   // your <Class>.h

void UMyGameInstance::Init()
{
    Super::Init();
    KofamuTable::Touch();
}
```

No GameInstance yet? Create one (Tools > New C++ Class > GameInstance), then pick it in Project Settings > Maps & Modes > Game Instance Class.

`Touch()` reads the strings once and stores a number nobody uses. The call keeps the linker from dropping the strings from the Shipping executable.

## 3. Package and check

From the IndieWard repo, in PowerShell:

```powershell
.\scripts\ue5_check.ps1 -UProject "D:\Games\MyGame\MyGame.uproject" -Build b1a2b3c4d5
```

What it does:

1. Checks the vault has a verified store link (`indieward status`). If not, it stops before touching your project.
2. Checks the `.h/.cpp` are in `Source\<Module>\` and that something calls `<Class>::Touch()`. If the files are missing it stops and tells you where they go. Add `-Apply` to let it copy them in. It never edits your GameInstance.
3. Runs `RunUAT BuildCookRun` (Shipping, Win64, cook, pak, stage, archive) into `<project>\..\<Name>_IndieWard\<build id>\`.
4. Runs `indieward build register --build <id> <that folder>`, which scans the packaged files and stores the build's fingerprints.

Useful options: `-PrintOnly` (show the commands; it only reads the vault), `-EngineRoot "C:\Program Files\Epic Games\UE_5.4"` (or set `UE_ROOT`), `-Module`, `-ArchiveDir`, `-VaultDir`, `-SkipPackage` (register a build you already packaged into `-ArchiveDir`).

Unreal writes its usual caches (`Binaries\`, `Intermediate\`, `Saved\`) in the project while packaging, as it does from the editor. Without `-Apply` the script writes nothing to `Source\`, `Content\` or `Config\`.

Packaging from the editor instead (Platforms > Windows > Package Project, Shipping) works too. Then run:

```
indieward build register --build <id> "<packaged folder>"
```

### What success looks like

```
Traps found   : 6 of 9
PASS: traps survived. Build b1a2b3c4d5 is registered (manifest ...).
```

A pass needs at least 2 core traps and the build trap. In a Shipping build with the C++ route, expect the strings (`loc_key`, `meta_value`, `function_return`, `build_tag`) and the two numbers (`constant`, `build_constant`) to be found in the `.exe`. `dead_function` (a function name), `hidden_asset` and `hidden_asset_hash` (the PNG) are usually reported missing: Shipping executables carry no function names, and the PNG only ships through the Blueprint route.

## Why the executable is enough

C++ `TEXT("...")` literals are stored as UTF-16 inside the game's `.exe`, and IndieWard searches UTF-8, UTF-16 and UTF-32. That works even when your paks are encrypted, because the executable itself isn't. Files over 512 MB (usually big paks) are skipped by the scan; the executable is well under that.

## Before you upload

- Make sure `README_INDIEWARD.txt` isn't in the build.
- Keep the trap values secret. They only help if a cloner doesn't know to remove them.
- Next build: `indieward traps new` again. Core traps stay the same across builds; the build trap tells you which build was ripped.
