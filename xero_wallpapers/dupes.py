import io
import sqlite3
import threading
from pathlib import Path
from typing import Callable, NamedTuple
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit

from PIL import Image, ImageOps, ImageStat

from . import paths
from .library import IMAGE_EXTS, list_media
from .sources.base import Item

MAX_BITS = 6
MAX_RATIO_DIFF = 0.03
MIN_CONTRAST = 2.0
MAX_PIXELS = 64_000_000
DRAFT_BOX = (256, 256)


class Fingerprint(NamedTuple):
    dhash: int
    ahash: int
    ratio: float
    pixels: int


def _bits(values, threshold) -> int:
    out = 0
    for v in values:
        out = (out << 1) | (v > threshold)
    return out


def fingerprint(image: Image.Image) -> Fingerprint | None:
    # None means the picture is too flat to tell apart from other flat pictures.
    w, h = image.size
    if not w or not h or w * h > MAX_PIXELS:
        return None
    if image.getexif().get(0x0112) in (5, 6, 7, 8):
        w, h = h, w
    image.draft("RGB", DRAFT_BOX)
    image = ImageOps.exif_transpose(image)
    grey = image.convert("L").resize((32, 32), Image.Resampling.BOX)
    if ImageStat.Stat(grey).stddev[0] < MIN_CONTRAST:
        return None
    d = grey.resize((9, 8), Image.Resampling.BILINEAR).tobytes()
    dhash = 0
    for row in range(8):
        for col in range(8):
            dhash = (dhash << 1) | (d[row * 9 + col + 1] > d[row * 9 + col])
    a = grey.resize((8, 8), Image.Resampling.BOX).tobytes()
    ahash = _bits(a, sum(a) / len(a))
    return Fingerprint(dhash, ahash, w / h, w * h)


def fingerprint_bytes(data: bytes) -> Fingerprint | None:
    return fingerprint(Image.open(io.BytesIO(data)))


def item_ratio(item: Item, fp: Fingerprint) -> float:
    return item.width / item.height if item.width > 0 and item.height > 0 else fp.ratio


def same_picture(a: Fingerprint, b: Fingerprint, ratio_a: float | None = None, ratio_b: float | None = None) -> bool:
    ra, rb = ratio_a or a.ratio, ratio_b or b.ratio
    return (
        (a.dhash ^ b.dhash).bit_count() <= MAX_BITS
        and (a.ahash ^ b.ahash).bit_count() <= MAX_BITS
        and abs(ra - rb) <= max(ra, rb) * MAX_RATIO_DIFF
    )


def normalise_url(url: str) -> str:
    parts = urlsplit(url.strip())
    host = (parts.hostname or "").removeprefix("www.")
    port = f":{parts.port}" if parts.port and parts.port not in (80, 443) else ""
    query = urlencode(sorted(parse_qsl(parts.query, keep_blank_values=True)))
    return f"{host}{port}{unquote(parts.path).rstrip('/')}" + (f"?{query}" if query else "")


def identity(item: Item) -> tuple[str, set[str]]:
    primary = f"{item.source}|{normalise_url(item.page_url)}"
    keys = {primary}
    if item.download_url:
        keys.add("dl|" + normalise_url(item.download_url))
    if item.extra.get("id"):
        keys.add(f"{item.source}#{item.extra['id']}")
    return primary, keys


class _Store:
    def __init__(self):
        self._lock = threading.Lock()
        self._path: Path | None = None
        self._db: sqlite3.Connection | None = None

    def _conn(self) -> sqlite3.Connection:
        path = Path(paths.CACHE_DIR) / "fingerprints.db"
        if path != self._path:
            if self._db is not None:
                self._db.close()
            path.parent.mkdir(parents=True, exist_ok=True)
            self._db = sqlite3.connect(path, check_same_thread=False)
            self._db.execute(
                "CREATE TABLE IF NOT EXISTS fp (key TEXT PRIMARY KEY, dhash TEXT, ahash TEXT, ratio REAL, pixels INTEGER)"
            )
            self._path = path
        return self._db

    def get(self, key: str) -> tuple[bool, Fingerprint | None]:
        with self._lock:
            row = self._conn().execute("SELECT dhash, ahash, ratio, pixels FROM fp WHERE key = ?", (key,)).fetchone()
        if row is None:
            return False, None
        if not row[0]:
            return True, None
        return True, Fingerprint(int(row[0], 16), int(row[1], 16), row[2], row[3])

    def put(self, key: str, fp: Fingerprint | None):
        values = (f"{fp.dhash:x}", f"{fp.ahash:x}", fp.ratio, fp.pixels) if fp else ("", "", 0.0, 0)
        with self._lock:
            db = self._conn()
            db.execute("INSERT OR REPLACE INTO fp VALUES (?, ?, ?, ?, ?)", (key, *values))
            db.commit()


STORE = _Store()


def for_url(url: str, fetch: Callable[[str], bytes]) -> Fingerprint | None:
    key = "url|" + normalise_url(url)
    found, fp = STORE.get(key)
    if not found:
        fp = fingerprint_bytes(fetch(url))
        STORE.put(key, fp)
    return fp


def _file_key(path: Path) -> str:
    st = path.stat()
    return f"file|{path}|{st.st_size}|{st.st_mtime_ns}"


def for_file(path: Path, compute: bool = True) -> Fingerprint | None:
    # Videos only have the fingerprints remembered from a grabbed frame or their thumbnail.
    try:
        key = _file_key(path)
        found, fp = STORE.get(key)
        if found or not compute or path.suffix.lower() not in IMAGE_EXTS:
            return fp
        try:
            with Image.open(path) as image:
                fp = fingerprint(image)
        except (OSError, ValueError, Image.DecompressionBombError):
            fp = None
        STORE.put(key, fp)
        return fp
    except OSError:
        return None


def remember_file(path: Path, fp: Fingerprint | None):
    try:
        STORE.put(_file_key(path), fp)
    except OSError:
        pass


def find_copy(folder: Path, kind: str, fp: Fingerprint, ratio: float) -> Path | None:
    for path in list_media(folder, kind):
        other = for_file(path)
        if other is not None and same_picture(fp, other, ratio):
            return path
    return None


def collapse(entries: list[tuple[str, Fingerprint | None, tuple]]) -> tuple[list[str], dict[str, str]]:
    # entries: (path, fingerprint, rank); the highest rank in each group is kept.
    # Returns the kept paths in input order and {extra copy: kept path}.
    parent = list(range(len(entries)))

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    known = [i for i, e in enumerate(entries) if e[1] is not None]
    for n, i in enumerate(known):
        for j in known[n + 1:]:
            if same_picture(entries[i][1], entries[j][1]):
                parent[root(j)] = root(i)
    best: dict[int, int] = {}
    for i, e in enumerate(entries):
        r = root(i)
        if r not in best or e[2] > entries[best[r]][2]:
            best[r] = i
    kept = [e[0] for i, e in enumerate(entries) if best[root(i)] == i]
    extras = {e[0]: entries[best[root(i)]][0] for i, e in enumerate(entries) if best[root(i)] != i}
    return kept, extras


class _Entry:
    def __init__(self, item: Item, fp: Fingerprint | None, keys: set[str], seq: int):
        self.item = item
        self.fp = fp
        self.keys = keys
        self.seq = seq


def _pixels(item: Item) -> int:
    return max(item.width, 0) * max(item.height, 0)


class Registry:
    """First-seen owner of each picture across pages and sources."""

    def __init__(self):
        self._owners: dict[str, _Entry] = {}
        self._alias: dict[str, str] = {}
        self._seq = 0

    def _owner_of(self, primary: str, keys: set[str]) -> str | None:
        target = self._alias.get(primary)
        if target is not None and target != primary:
            return target
        return next((self._alias[k] for k in keys if self._alias.get(k, primary) != primary), None)

    def place(self, item: Item, fp: Fingerprint | None) -> tuple[Item, Item | None]:
        """Returns (winner, loser): loser is the item to hide, or None when nothing is hidden."""
        primary, keys = identity(item)
        owner = self._owner_of(primary, keys)
        if owner is not None:
            return self._owners[owner].item, item
        entry = self._owners.get(primary)
        if entry is None:
            self._seq += 1
            entry = self._owners[primary] = _Entry(item, fp, keys, self._seq)
        else:
            entry.item, entry.fp, entry.keys = item, fp or entry.fp, entry.keys | keys
        for k in keys:
            self._alias.setdefault(k, primary)
        if entry.fp is None:
            return item, None
        ratio = item_ratio(item, entry.fp)
        for other in self._owners.values():
            if other is entry or other.fp is None:
                continue
            if not same_picture(entry.fp, other.fp, ratio, item_ratio(other.item, other.fp)):
                continue
            earlier, later = (other, entry) if other.seq < entry.seq else (entry, other)
            winner, loser = (later, earlier) if _pixels(later.item) > _pixels(earlier.item) else (earlier, later)
            winner.seq = earlier.seq
            self._merge(winner, loser)
            return winner.item, loser.item
        return item, None

    def _merge(self, winner: _Entry, loser: _Entry):
        target = next(p for p, e in self._owners.items() if e is winner)
        gone = next(p for p, e in self._owners.items() if e is loser)
        del self._owners[gone]
        for k, v in self._alias.items():
            if v == gone:
                self._alias[k] = target
