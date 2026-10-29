from __future__ import annotations

import base64
import datetime as _dt
import hashlib
import json
from pathlib import Path

DISCLAIMER = (
    "This score measures how similar the suspect is to your registered work. It cannot show "
    "whether an AI was used or what any AI read: nobody can see another party's prompts or model "
    "logs. It is evidence for you to weigh, not a legal finding, and IndieWard is not legal advice."
)


def now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def canonical_json(obj) -> bytes:
    """Deterministic JSON (sorted keys, no whitespace, UTF-8) for hashing and signing."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def unb64(text: str) -> bytes:
    return base64.b64decode(text.encode("ascii"))


IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tga", ".gif", ".tif", ".tiff"}
AUDIO_EXT = {".wav", ".mp3", ".ogg", ".flac", ".m4a", ".aac", ".opus"}
VIDEO_EXT = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}
CODE_EXT = {".gd", ".lua", ".luau", ".cs", ".js", ".mjs", ".ts", ".cpp", ".cc", ".c", ".h", ".hpp", ".py", ".rs",
            ".java", ".kt", ".swift", ".hx", ".gml"}
TEXT_EXT = {".txt", ".md", ".json", ".csv", ".yaml", ".yml", ".po", ".ink", ".rpy", ".dialogue", ".xml", ".tres"}


def kind_for(path) -> str:
    ext = Path(path).suffix.lower()
    if ext in IMAGE_EXT:
        return "image"
    if ext in AUDIO_EXT:
        return "audio"
    if ext in VIDEO_EXT:
        return "video"
    if ext in CODE_EXT:
        return "code"
    if ext in TEXT_EXT:
        return "text"
    return "other"


def iter_files(root):
    root = Path(root)
    if root.is_file():
        yield root
        return
    for p in sorted(root.rglob("*")):
        if p.is_file() and ".indieward" not in p.parts:
            yield p


VENDOR_PARTS = {"node_modules", "vendor", "third_party", "thirdparty", "external", "plugins", "addons", "packages",
                "Plugins", "Packages", "ThirdParty", "lib", "libs"}
VENDOR_FILES = ("jquery", "three.", "phaser", "pixi", "babylon", "react", "vue.", "lodash", "howler", "matter.",
                "license", "licence", "copying", "notice", "credits")


def is_vendor_path(path: str) -> bool:
    """Bundled third-party code and licence texts: shared by many games, so never counted as copying."""
    parts = Path(path.replace("\\", "/")).parts
    name = parts[-1].lower() if parts else ""
    return any(p in VENDOR_PARTS for p in parts[:-1]) or name.startswith(VENDOR_FILES) or ".min." in name
