import logging
import re
import threading
import unicodedata
from pathlib import Path
from typing import Callable

from PIL import Image

from .fsutil import move_no_replace
from .library import IMAGE_EXTS, list_media
from .sources.base import Item

log = logging.getLogger("xero_wallpapers.naming")

_SEP = r"[\s._-]+"
_NOISE = ["live wallpapers", "live wallpaper", "free download", "4k", "8k", "uhd", "hd", "alls com"]
_SITES = ["4kwallpapers", "moewalls", "motionbgs", "wallhaven"]
_NOISE_RE = re.compile(
    r"(?<![a-z0-9])(?:"
    + "|".join(
        [rf"{s}(?:{_SEP}com)?" for s in _SITES]
        + [_SEP.join(map(re.escape, p.split())) for p in _NOISE]
    )
    + r")(?![a-z0-9])",
    re.IGNORECASE,
)
_RESOLUTION = re.compile(r"(?<![0-9])\d{3,5}\s*x\s*\d{3,5}(?![0-9])", re.IGNORECASE)
_TRAILING_ID = re.compile(r"(?:[\s#_-]+\d{5,})+\s*$")
_TRAILING_NOISE = re.compile(r"(?:^|[\s._-]+)(?:wallpapers?|download)\s*$", re.IGNORECASE)
_CLASH_SUFFIX = re.compile(r"[-\s(]+\d{1,3}\)?\s*$")
_EDGE_PUNCT = re.compile(r"^[\s\-_|:;,.]+|[\s\-_|:;,.]+$")
_WORD = re.compile(r"[^\W_]+(?:'[^\W_]+)?")
_WALLHAVEN_STEM = re.compile(r"wallhaven-([0-9a-z]+)(?:[-_ ]\(?\d{1,3}\)?)?", re.IGNORECASE)
_CODE = re.compile(r"(?=\S*[a-z])(?=\S*\d)[a-z0-9]{1,8}|\d+", re.IGNORECASE)
_VOWELS = "aeiouy"
_ONSETS = set(
    "bl br ch cl cr dr dw fl fr gh gl gn gr kn kr ph pl pr ps rh sc sh sk sl sm sn sp st sw th tr tw "
    "wh wr chr phr sch scr shr sph spl spr str thr".split()
)


def _case(m: re.Match) -> str:
    word = m.group(0)
    if word.isupper() and 2 <= len(word) <= 4:
        return word
    return word[:1].upper() + word[1:].lower()


def _clean_part(text: str) -> str:
    text = _RESOLUTION.sub(" ", text)
    text = _NOISE_RE.sub(" ", text)
    text = _TRAILING_ID.sub("", text)
    while True:
        text = _EDGE_PUNCT.sub("", re.sub(r"\s+", " ", text))
        stripped = _TRAILING_NOISE.sub("", text)
        if stripped == text:
            break
        text = stripped
    if not any(c.isalnum() for c in text) or is_code(_CLASH_SUFFIX.sub("", text)):
        return ""
    return text


def _random_letters(word: str) -> bool:
    if not any(c in _VOWELS for c in word):
        return True
    onset = re.match(rf"[^{_VOWELS}]*", word).group(0)
    return (len(onset) >= 2 and onset not in _ONSETS) or bool(re.search(rf"[^{_VOWELS}]{{5,}}", word))


def is_code(text: str) -> bool:
    text = text.strip()
    if _CODE.fullmatch(text):
        return True
    # Wallhaven ids can be letters only (e.g. "jqwel"); real lowercase words rarely look this random.
    return bool(re.fullmatch(r"[a-z]{5,8}", text)) and _random_letters(text)


def clean_title(raw: str) -> str:
    parts = [_clean_part(p) for p in re.split(r"\s*[,|]\s*", raw or "")]
    return _WORD.sub(_case, ", ".join(p for p in parts if p))


def title_from_tags(tags: list[str], limit: int = 4) -> str:
    seen: set[str] = set()
    picked: list[str] = []
    for tag in tags:
        title = clean_title(tag)
        if not title or title.isdigit() or title.lower() in seen:
            continue
        seen.add(title.lower())
        picked.append(title)
        if len(picked) == limit:
            break
    return " ".join(picked)


def _slug(text: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")[:80].strip("-")


def name_slug(title: str) -> str:
    return "" if is_code(title) else _slug(title)


def _stem(title: str, width: int, height: int, source: str) -> str:
    base = name_slug(title) or _slug(source) or "wallpaper"
    return f"{base}-{width}x{height}" if width and height else base


def clean_filename(item: Item) -> str:
    return _stem(item.title, item.width, item.height, item.source)


def _image_size(path: Path) -> tuple[int, int]:
    if path.suffix.lower() not in IMAGE_EXTS:
        return 0, 0
    try:
        with Image.open(path) as im:
            return im.size
    except Exception:
        return 0, 0


def _target_stem(path: Path, lookup: Callable[[str], list[str]] | None) -> str:
    m = _WALLHAVEN_STEM.fullmatch(path.stem)
    if not m and path.stem.lower().startswith("wallhaven"):
        return ""
    if m:
        # "wallhaven-2560x1440" is this app's own name for an untitled download, not an id.
        if lookup is None or re.fullmatch(r"\d+x\d+", m.group(1)):
            return ""
        try:
            title, source = title_from_tags(lookup(m.group(1))), "wallhaven"
        except Exception as e:
            log.warning("tags for %s failed: %s", path.name, e)
            return ""
    else:
        title, source = clean_title(re.sub(r"[_-]+", " ", path.stem)), ""
        if not title:
            return ""
    return _stem(title, *_image_size(path), source)


def propose_renames(
    folder: Path, kind: str, lookup: Callable[[str], list[str]] | None, stop: threading.Event | None = None
) -> list[tuple[Path, Path]]:
    files = list_media(folder, kind)
    taken = {p.name for p in files}
    pairs = []
    for path in files:
        if stop is not None and stop.is_set():
            break
        stem = _target_stem(path, lookup)
        if not stem:
            continue
        ext = path.suffix.lower()
        name, n = stem + ext, 2
        while name in taken and name != path.name:
            name, n = f"{stem}-{n}{ext}", n + 1
        if name != path.name:
            taken.add(name)
            pairs.append((path, folder / name))
    return pairs


def apply_renames(pairs) -> list[tuple[Path, Path]]:
    done = []
    for old, new in pairs:
        if new.exists() or not old.is_file():
            continue
        try:
            move_no_replace(old, new)
        except OSError as e:
            log.warning("rename %s -> %s failed: %s", old, new, e)
            continue
        done.append((old, new))
    return done
