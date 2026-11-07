import itertools
import re
import threading
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

from . import net
from .fsutil import move_no_replace
from .library import IMAGE_EXTS, VIDEO_EXTS
from .naming import clean_filename, name_slug
from .sources.base import Item

MEDIA_EXTS = IMAGE_EXTS | VIDEO_EXTS
CONTENT_TYPE_EXTS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "video/mp4": ".mp4",
    "video/webm": ".webm",
}
CHUNK = 64 * 1024
SAFE_SCHEMES = ("http", "https")
UNTYPED = ("", "application/octet-stream", "binary/octet-stream")


class DownloadCancelled(Exception):
    pass


def require_http(url: str) -> None:
    if urlparse(url).scheme.lower() not in SAFE_SCHEMES:
        raise ValueError(f"refusing to fetch a non-http(s) URL: {url}")


def _extension(item: Item, url: str, content_type: str, sniffed: str = "") -> str:
    ext = Path(urlparse(url).path).suffix.lower()
    if ext in MEDIA_EXTS:
        return ext
    mime = content_type.split(";")[0].strip().lower()
    if mime in CONTENT_TYPE_EXTS:
        return CONTENT_TYPE_EXTS[mime]
    return sniffed or (".mp4" if item.kind == "live" else ".jpg")


def _part(path: Path) -> Path:
    return path.with_suffix(path.suffix + ".part")


def target_path(folder: Path, item: Item, url: str, content_type: str = "", sniffed: str = "") -> Path:
    ext = _extension(item, url, content_type, sniffed)
    stem = clean_filename(item)
    path = folder / f"{stem}{ext}"
    n = 2
    while path.exists() or _part(path).exists():
        path = folder / f"{stem}-{n}{ext}"
        n += 1
    return path


def already_downloaded(folder: Path, item: Item) -> Path | None:
    base = name_slug(item.title)
    if not base:
        return None
    res = rf"(-{item.width}x{item.height})?" if item.width and item.height else ""
    pattern = re.compile(rf"{re.escape(base)}{res}(-\d+)?")
    try:
        files = sorted(folder.iterdir())
    except OSError:
        return None
    for p in files:
        if p.suffix.lower() in MEDIA_EXTS and pattern.fullmatch(p.stem) and p.is_file():
            return p
    return None


def _magic(head: bytes) -> str:
    if head[4:8] == b"ftyp":
        return ".mp4"
    if head[:4] == b"\x1a\x45\xdf\xa3":
        return ".webm"
    if head[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if head[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return ".webp"
    if head[:4] == b"GIF8":
        return ".gif"
    return ""


def _disposition_ext(header: str) -> str:
    m = re.search(r"filename\*?=(?:[\w-]+'[\w-]*')?\"?([^\";]+)", header or "", re.IGNORECASE)
    return Path(m.group(1).strip()).suffix.lower() if m else ""


def _check_media(url: str, final_url: str, headers, head: bytes) -> str:
    # Returns the extension the bytes prove, for responses whose type doesn't say.
    mime = headers.get("Content-Type", "").split(";")[0].strip().lower()
    if mime.startswith(("image/", "video/")):
        return ""
    if mime in UNTYPED:
        sniffed = _magic(head)
        if sniffed:
            return sniffed
        named = _disposition_ext(headers.get("Content-Disposition", ""))
        exts = {named, *(Path(urlparse(u).path).suffix.lower() for u in (url, final_url) if u)}
        if exts & MEDIA_EXTS and head.lstrip()[:1] not in (b"<", b"{"):
            return named if named in MEDIA_EXTS else ""
    raise ValueError(f"the server sent {mime or 'an unknown file type'} instead of a wallpaper")


def download(
    url: str,
    folder: Path,
    item: Item,
    progress: Callable[[int, int], None],
    cancel: threading.Event,
) -> Path:
    require_http(url)
    folder.mkdir(parents=True, exist_ok=True)
    resp = net.SESSION.get(url, stream=True, timeout=net.TIMEOUT)
    part = None
    try:
        resp.raise_for_status()
        content_type = resp.headers.get("Content-Type", "")
        chunks = resp.iter_content(CHUNK)
        head = next(chunks, b"")
        sniffed = _check_media(url, resp.url, resp.headers, head)
        total = int(resp.headers.get("Content-Length") or 0)
        while part is None:
            dest = target_path(folder, item, url, content_type, sniffed)
            try:
                f = open(_part(dest), "xb")
            except FileExistsError:
                continue
            part = _part(dest)
        done = 0
        with f:
            for chunk in itertools.chain([head], chunks):
                if cancel.is_set():
                    raise DownloadCancelled()
                f.write(chunk)
                done += len(chunk)
                progress(done, total)
                if cancel.is_set():
                    raise DownloadCancelled()
        while True:
            try:
                move_no_replace(part, dest)
                return dest
            except FileExistsError:
                dest = target_path(folder, item, url, content_type, sniffed)
    finally:
        resp.close()
        if part is not None:
            part.unlink(missing_ok=True)
