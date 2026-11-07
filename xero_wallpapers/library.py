import json
import os
import re
import shutil
import stat
from pathlib import Path
from urllib.parse import unquote, urlparse

from .svwr import ID as SVWR_ID

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
VIDEO_EXTS = {".mp4", ".webm", ".mkv"}
IMAGE_PLUGIN = "org.kde.image"
APPLETSRC = "plasma-org.kde.plasma.desktop-appletsrc"

CONTAINMENT = re.compile(r"\[Containments\]\[([^\]]+)\](.*)")
WALLPAPER_GROUP = re.compile(r"\[Wallpaper\]\[([^\]]+)\]\[General\]")


def list_media(folder: Path, kind: str) -> list[Path]:
    exts = VIDEO_EXTS if kind == "live" else IMAGE_EXTS
    try:
        candidates = [p for p in folder.iterdir() if p.suffix.lower() in exts]
    except OSError:
        return []
    found = []
    for p in candidates:
        try:
            st = p.stat()
        except OSError:
            continue
        if stat.S_ISREG(st.st_mode):
            found.append((st.st_mtime, p))
    return [p for _, p in sorted(found, key=lambda e: e[0], reverse=True)]


def restore_from_trash(trashed: Path, original: Path) -> None:
    if original.exists():
        raise FileExistsError(f"{original.name} already exists")
    shutil.move(trashed, original)
    (trashed.parent.parent / "info" / (trashed.name + ".trashinfo")).unlink(missing_ok=True)


def _local(value: str) -> str:
    url = urlparse(value)
    if url.scheme == "file":
        return unquote(url.path)
    return value if value.startswith("/") else ""


def _videos(raw: str) -> list[str]:
    try:
        entries = json.loads(raw)
    except ValueError:
        return []
    if not isinstance(entries, list):
        return []
    return [
        _local(str(e.get("filename", "")))
        for e in entries
        if isinstance(e, dict) and e.get("enabled", True)
    ]


def current_wallpapers(text: str) -> set[str]:
    plugins: dict[str, str] = {}
    values: dict[tuple[str, str, str], str] = {}
    group = None
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("["):
            m = CONTAINMENT.fullmatch(line)
            group = (m.group(1), m.group(2)) if m else None
            continue
        key, sep, value = line.partition("=")
        if group is None or not sep:
            continue
        cid, rest = group
        if not rest and key == "wallpaperplugin":
            plugins[cid] = value
        elif key in ("Image", "VideoUrls"):
            m = WALLPAPER_GROUP.fullmatch(rest)
            if m:
                values[(cid, m.group(1), key)] = value
    found: set[str] = set()
    for cid, plugin in plugins.items():
        if plugin == IMAGE_PLUGIN:
            found.add(_local(values.get((cid, plugin, "Image"), "")))
        elif plugin == SVWR_ID:
            found.update(_videos(values.get((cid, plugin, "VideoUrls"), "")))
    found.discard("")
    return found


def appletsrc_text() -> str:
    config_home = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return (config_home / APPLETSRC).read_text(errors="replace")


def read_current() -> set[str]:
    try:
        return current_wallpapers(appletsrc_text())
    except OSError:
        return set()
