"""Builds a small synthetic test game, a planted clone of it, and an unrelated game.

Everything is generated: procedural art, synthesized music, scripted dialogue
and GDScript-style code. No third-party assets are used.
"""
from __future__ import annotations

import json
import random
import re
import shutil
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from indieward import mediaio

ORIG_CODE = {
    "player.gd": '''extends CharacterBody2D
# Lantern Moth: the player moth that carries light between lamps.
const MAX_SPEED := 220.0
const GLOW_DECAY := 0.18
var glow := 1.0
var carried_lamps := []
var wing_phase := 0.0

func _physics_process(delta):
    var dir := Input.get_vector("left", "right", "up", "down")
    velocity = velocity.lerp(dir * MAX_SPEED * (0.5 + glow * 0.5), 0.2)
    wing_phase += delta * (6.0 + velocity.length() * 0.02)
    glow = max(0.0, glow - GLOW_DECAY * delta)
    if glow <= 0.0:
        emit_signal("burned_out")
    move_and_slide()

func touch_lamp(lamp):
    if lamp.lit and not carried_lamps.has(lamp):
        carried_lamps.append(lamp)
        glow = min(1.0, glow + lamp.charge * 0.35)
        lamp.flicker(0.4)
    elif not lamp.lit and glow > 0.25:
        lamp.ignite(glow * 0.5)
        glow -= 0.25

func wing_offset() -> float:
    return sin(wing_phase) * 3.5 + cos(wing_phase * 0.5) * 1.25

func score_for_chain(chain_len, time_left):
    var base := chain_len * chain_len * 15
    var bonus := int(time_left * 3.0)
    if chain_len >= 5:
        bonus += 250
    return base + bonus
''',
    "lamp.gd": '''extends Node2D
# Lamps hold charge; moths carry it between them.
export var charge := 0.6
var lit := true
var flicker_time := 0.0
var neighbours := []

func _process(delta):
    if flicker_time > 0.0:
        flicker_time -= delta
        modulate.a = 0.6 + 0.4 * abs(sin(flicker_time * 40.0))
    else:
        modulate.a = 1.0 if lit else 0.35
    if lit:
        charge = min(1.0, charge + delta * 0.05)

func flicker(seconds):
    flicker_time = seconds

func ignite(amount):
    lit = true
    charge = clamp(amount, 0.1, 1.0)
    for n in neighbours:
        if not n.lit and n.global_position.distance_to(global_position) < 140.0:
            n.charge += amount * 0.25

func dim(rate, delta):
    charge -= rate * delta
    if charge <= 0.0:
        lit = false
        charge = 0.0
''',
    "night.gd": '''extends Node
# Night cycle: the bell tower rings, the dark creeps in, lamps fade.
var minutes := 0.0
var bell_interval := 45.0
var next_bell := 45.0
var darkness := 0.0
var lamps := []

func _process(delta):
    minutes += delta
    darkness = clamp(minutes / 600.0, 0.0, 0.85)
    for lamp in lamps:
        lamp.dim(0.01 + darkness * 0.03, delta)
    if minutes >= next_bell:
        ring_bell()
        next_bell += bell_interval * (1.0 - darkness * 0.4)

func ring_bell():
    for lamp in lamps:
        if lamp.lit:
            lamp.flicker(0.25)
    emit_signal("bell_rang", int(minutes / bell_interval))

func dawn_progress() -> float:
    return 1.0 - darkness / 0.85
''',
}

UNRELATED_CODE = {
    "miner.gd": '''extends KinematicBody2D
# Crystal Quarry: dig, sort gems, upgrade the drill.
var drill_level = 1
var cargo = {}
var fuel = 100

func dig(tile):
    if fuel <= 0:
        return null
    fuel -= 2 + tile.hardness
    var gem = tile.roll_gem(drill_level)
    if gem:
        cargo[gem.kind] = cargo.get(gem.kind, 0) + 1
    return gem

func sell_all(shop):
    var total = 0
    for kind in cargo.keys():
        total += shop.price(kind) * cargo[kind]
    cargo.clear()
    return total

func upgrade(cost_table, money):
    var cost = cost_table[drill_level]
    if money >= cost:
        drill_level += 1
        return money - cost
    return money
''',
    "shop.gd": '''extends Node
var prices = {"ruby": 40, "opal": 25, "jade": 15}
var demand = {}

func price(kind):
    var d = demand.get(kind, 1.0)
    return int(prices.get(kind, 5) * d)

func tick(hours):
    for k in prices.keys():
        demand[k] = 0.8 + randf() * 0.4
''',
}

DIALOGUE = [
    "The lantern moths only fly when the bell tower rings at midnight.",
    "Carry the light from lamp to lamp before the dark swallows the square.",
    "Old Maren says the first moth was a spark that refused to go out.",
    "If your glow fades completely, the night keeps you until dawn.",
    "Every lamp you relight remembers you, and burns a little longer.",
    "The bell keeps time for the whole town, even the ones who sleep.",
    "Follow the warm air above the bakery chimney to reach the high lamps.",
    "Moths that chain five lamps together earn the lamplighter's blessing.",
    "Don't touch the cold lamps by the river unless your wings are bright.",
    "The clockmaker swears the tower rings one extra time on the longest night.",
    "We lost the east district last winter when nobody carried the light.",
    "A lamp that flickers is asking for help, not warning you away.",
    "Your wings beat faster when you're close to a lit lamp.",
    "The fog rolls in from the harbor after the third bell.",
    "Children leave paper moths on the windowsills for good luck.",
    "When the square is fully lit, the statues open their eyes.",
    "Some say the darkness is just the night trying to sleep.",
    "Bring the ember from the lighthouse before the tide turns.",
]

REWORD = [
    ("only fly", "only take flight"), ("rings at midnight", "chimes at midnight"),
    ("Carry the light", "Bring the light"), ("swallows", "eats"), ("says", "claims"),
    ("refused to go out", "would not go out"), ("completely", "entirely"), ("keeps you", "holds you"),
    ("relight", "rekindle"), ("burns a little longer", "burns a bit longer"), ("Follow", "Ride"),
    ("earn", "receive"), ("Don't touch", "Never touch"), ("swears", "insists"), ("We lost", "We lost"),
    ("asking for help", "begging for help"), ("beat faster", "flap faster"), ("rolls in", "drifts in"),
    ("leave", "put"), ("fully lit", "completely lit"), ("trying to sleep", "wanting to sleep"),
    ("Bring the ember", "Fetch the ember"),
]

UNRELATED_DIALOGUE = [
    "Rubies sell best on Tuesdays when the caravan comes through.",
    "Your drill overheats if you dig through basalt for too long.",
    "The foreman keeps the good maps locked in the tool shed.",
    "Jade is common up top but the deep layers hide opals.",
    "Buy a bigger fuel tank before you try the lower quarry.",
    "The shop owner only pays full price for polished gems.",
    "Watch for gas pockets glowing green in the cave walls.",
    "Every upgrade makes the drill louder and the rocks softer.",
]


def _art(seed: int, size=256, palette=None) -> Image.Image:
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:size, 0:size] / size
    base = np.stack([0.2 + 0.5 * xx, 0.15 + 0.4 * yy, 0.35 + 0.3 * (1 - xx)], -1)
    noise = rng.random((size // 8, size // 8))
    noise = np.asarray(Image.fromarray((noise * 255).astype(np.uint8)).resize((size, size), Image.Resampling.BICUBIC)) / 255.0
    img = np.clip(base * (0.7 + 0.5 * noise[..., None]), 0, 1)
    im = Image.fromarray((img * 255).astype(np.uint8))
    d = ImageDraw.Draw(im)
    for _ in range(9):
        x, y = rng.integers(0, size, 2)
        r = int(rng.integers(12, 60))
        col = tuple(int(c) for c in rng.integers(40, 255, 3))
        if rng.random() < 0.5:
            d.ellipse((x - r, y - r, x + r, y + r), fill=col, outline=(20, 20, 20), width=3)
        else:
            pts = [(int(x + r * np.cos(a)), int(y + r * np.sin(a))) for a in np.linspace(0, 2 * np.pi, int(rng.integers(3, 7)), endpoint=False)]
            d.polygon(pts, fill=col, outline=(15, 15, 15))
    for _ in range(6):
        x0, y0, x1, y1 = (int(v) for v in rng.integers(0, size, 4))
        d.line((x0, y0, x1, y1), fill=(250, 240, 200), width=2)
    return im.filter(ImageFilter.SMOOTH)


def _music(seed: int, seconds=12.0, sr=44100) -> np.ndarray:
    rng = np.random.default_rng(seed)
    t = np.arange(int(seconds * sr)) / sr
    x = np.zeros_like(t)
    scale = np.array([0, 2, 3, 5, 7, 8, 10, 12])
    root = 196.0 * (1 + seed % 3 * 0.12)
    step = 0.375
    for i in range(int(seconds / step)):
        f = root * 2 ** (scale[rng.integers(0, 8)] / 12)
        seg = (t >= i * step) & (t < i * step + step * 1.6)
        env = np.exp(-(t - i * step) * 4) * seg
        for h in range(1, 5):
            x += 0.18 / h * np.sin(2 * np.pi * f * h * t) * env
    x += 0.12 * np.sin(2 * np.pi * root / 2 * t) * (0.6 + 0.4 * np.sin(2 * np.pi * 0.13 * t))
    x += 0.02 * rng.standard_normal(len(t)) * np.exp(-((t % (step * 2)) * 25))
    x = x / np.abs(x).max() * 0.8
    return np.stack([x, 0.92 * x], 1)


def _video(path: Path, arts: list[Image.Image], seconds=20, fps=30, w=640, h=360):
    bg = Image.new("RGB", (w * 2, h * 2))
    for i, a in enumerate(arts[:4]):
        bg.paste(a.resize((w, h)), ((i % 2) * w, (i // 2) * h))
    wr = mediaio.FrameWriter(path, w, h, fps, crf=16)
    for i in range(seconds * fps):
        t = i / fps
        ox = int((w / 2) * (1 + np.sin(t * 0.35)))
        oy = int((h / 2) * (1 + np.sin(t * 0.21)))
        fr = bg.crop((ox, oy, ox + w, oy + h))
        d = ImageDraw.Draw(fr)
        for k in range(3):
            cx = int((t * 70 * (k + 1)) % w)
            cy = int(h / 2 + 70 * np.sin(t * 1.7 + k))
            d.ellipse((cx - 14, cy - 10, cx + 14, cy + 10), fill=(255, 230, 140))
        d.rectangle((0, 0, w, 26), fill=(14, 14, 24))
        d.text((10, 7), f"GLOW {100 - (i % 100):03d}   LAMPS {i // 90}", fill=(255, 220, 120))
        wr.write(np.asarray(fr, dtype=np.float64))
    wr.close()


def make_original(root: Path) -> dict:
    root.mkdir(parents=True, exist_ok=True)
    (root / "src").mkdir(exist_ok=True)
    for n, c in ORIG_CODE.items():
        (root / "src" / n).write_text(c)
    (root / "art").mkdir(exist_ok=True)
    arts = []
    for i in range(6):
        a = _art(100 + i)
        a.save(root / "art" / f"moth_{i}.png")
        arts.append(a)
    (root / "ui").mkdir(exist_ok=True)
    hud = _art(900, 320)
    ImageDraw.Draw(hud).rectangle((0, 0, 320, 40), fill=(14, 14, 24))
    hud.save(root / "ui" / "hud.png")
    (root / "text").mkdir(exist_ok=True)
    (root / "text" / "dialogue.json").write_text(json.dumps({"lines": DIALOGUE}, indent=2))
    (root / "audio").mkdir(exist_ok=True)
    mediaio.write_audio(root / "audio" / "theme.wav", _music(7), 44100)
    (root / "video").mkdir(exist_ok=True)
    _video(root / "video" / "trailer.mp4", arts)
    return {"arts": arts}


def export_build(src_root: Path, traps_dir: Path, out_zip: Path, art_dir: Path | None = None) -> Path:
    """'Export' the game: scripts, data, art and trap files packed into one archive."""
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted((src_root / "src").glob("*.gd")):
            z.write(f, f"scripts/{f.name}")
        z.write(src_root / "text" / "dialogue.json", "data/dialogue.json")
        for f in sorted((art_dir or (src_root / "art")).glob("*.png")):
            z.write(f, f"art/{f.name}")
        for f in sorted(traps_dir.rglob("*")):
            if f.is_file() and not f.name.startswith("README_"):  # the README is never shipped
                z.write(f, f"{f.relative_to(traps_dir)}")
    return out_zip


def _rename_identifiers(code: str, seed: int) -> str:
    rng = random.Random(seed)
    keep = {"extends", "func", "var", "const", "if", "elif", "else", "for", "in", "return", "not", "and", "or",
            "while", "true", "false", "export", "max", "min", "sin", "cos", "abs", "clamp", "int", "float",
            "Input", "velocity", "move_and_slide", "emit_signal", "modulate", "global_position", "delta",
            "CharacterBody2D", "Node2D", "Node", "lerp", "length", "has", "append", "distance_to", "get_vector"}
    names = sorted(set(re.findall(r"\b[a-z_][a-z0-9_]*\b", code)) - keep)
    mapping = {n: f"{rng.choice(['q', 'zz', 'm', 'fl', 'k'])}{i}_{rng.randint(10, 99)}" for i, n in enumerate(names)}

    def sub(line: str) -> str:
        if line.lstrip().startswith("#") or '"' in line:
            return line
        return re.sub(r"\b[a-z_][a-z0-9_]*\b", lambda m: mapping.get(m.group(0), m.group(0)), line)

    return "\n".join(sub(l) for l in code.splitlines()) + "\n"


def _reorder_functions(code: str, seed: int) -> str:
    parts = re.split(r"\n(?=func )", code)
    head, funcs = parts[0], parts[1:]
    random.Random(seed).shuffle(funcs)
    return "\n".join([head, *funcs])


def _recolor(im: Image.Image, shift: int = 60, scale: float = 0.75) -> Image.Image:
    hsv = np.asarray(im.convert("HSV")).copy()
    hsv[..., 0] = (hsv[..., 0].astype(int) + shift) % 256
    out = Image.fromarray(hsv, mode="HSV").convert("RGB")
    return out.resize((int(im.width * scale), int(im.height * scale)), Image.Resampling.LANCZOS)


def make_clone(orig_root: Path, orig_build_zip: Path, clone_root: Path) -> Path:
    """Variables renamed, functions reordered, art recolored and resized (from unmarked art, so no
    watermarks), dialogue lightly reworded, trap files copied over untouched."""
    clone_root.mkdir(parents=True, exist_ok=True)
    work = clone_root / "unpacked"
    if work.exists():
        shutil.rmtree(work)
    with zipfile.ZipFile(orig_build_zip) as z:
        z.extractall(work)
    for f in (work / "scripts").glob("*.gd"):
        code = _reorder_functions(_rename_identifiers(f.read_text(), 3), 5)
        (work / "scripts" / f"c_{f.name}").write_text(code)
        f.unlink()
    lines = json.loads((work / "data" / "dialogue.json").read_text())["lines"]
    new = []
    for ln in lines:
        for a, b in REWORD:
            ln = ln.replace(a, b)
        new.append(ln)
    (work / "data" / "dialogue.json").write_text(json.dumps({"text": new}))
    for f in (work / "art").glob("*.png"):
        f.unlink()
    for f in sorted((orig_root / "art").glob("*.png")):
        _recolor(Image.open(f).convert("RGB")).save(work / "art" / f"sprite_{f.stem[-1]}.png")
    # copied music, re-encoded (watermark stripped: built from the unmarked original)
    mediaio.transcode(orig_root / "audio" / "theme.wav", work / "music.ogg", mediaio.vorbis_args(4))
    out = clone_root / "NightFlightMoths.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(work.rglob("*")):
            if f.is_file():
                z.write(f, f.relative_to(work))
    shutil.rmtree(work)
    return out


def make_unrelated(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    out = root / "CrystalQuarry.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for n, c in UNRELATED_CODE.items():
            z.writestr(f"scripts/{n}", c)
        z.writestr("data/lines.json", json.dumps(UNRELATED_DIALOGUE))
        for i in range(5):
            p = root / f"gem_{i}.png"
            im = _art(5000 + i)
            im = Image.fromarray(np.asarray(im)[:, ::-1, ::-1].copy()).rotate(90)
            im.save(p)
            z.write(p, f"art/gem_{i}.png")
        mediaio.write_audio(root / "quarry.wav", _music(9001) * 0.7, 44100)
        z.write(root / "quarry.wav", "audio/quarry.wav")
    return out
