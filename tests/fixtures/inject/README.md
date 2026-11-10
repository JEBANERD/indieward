# Engine samples for `traps inject`

Real files saved by the engines, used as the reference layout for the inject parsers. Don't hand-edit them.

## Godot (for P2-16)

Saved by **Godot 4.4.1-stable** (official win64 build) with `ResourceSaver.save()` from a headless `--script` run:

- `godot_translation_fr.tres`: a `Translation`, locale `fr`, messages `MENU_START` → `Commencer` and `MENU_QUIT` → `Quitter`.
- `godot_optimized_translation_fr.tres`: the same messages after `OptimizedTranslation.generate()`. The messages are hashed, so inject must refuse it.

Notes from making them:
- The card asked for 4.3. 4.4.1 is what was installed; both write `format=3` text resources. Keys and values are saved as StringName literals (`&"..."`), and the keys come out sorted.
- A plain `Translation` drops message context: `add_message("Open", "Ouvrir", "verb")` saves as `&"Open": &"Ouvrir"` with no context. Only `TranslationPO` keeps context, and Godot projects normally get that from a `.po` file, which inject already handles. So there is no context sample.
