import contextlib
import io
import logging
import math
import os
import re
import shutil
import tempfile
import threading
import time
import warnings
import weakref
from collections import Counter
from dataclasses import asdict, fields, replace
from pathlib import Path
from urllib.parse import urlparse

import requests
from PIL import Image
from PyQt6.QtCore import QBuffer, QFile, QObject, QProcess, QTimer, QUrl, pyqtProperty, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QDesktopServices, QGuiApplication, QImage

from .. import dupes, kpackage, library, net, paths, slideshow, svwr, update, upscale, wallpaper
from ..colors import hue_matches, palette
from ..config import Config
from ..downloads import SAFE_SCHEMES, DownloadCancelled, already_downloaded, download
from ..naming import apply_renames, propose_renames, title_from_tags
from ..sources import custom
from ..sources.base import Filters, Item, Source, SourceError, screen_size
from ..sources.custom import validate_custom
from ..sources.registry import BUILTINS
from ..tags import RateLimiter, Stopped, WorkQueue
from ..wallpaper import WallpaperError, set_live, set_static
from .models import WallpaperModel, cover_url, fill_url, source_label, thumb_url
from .thumbs import CACHE_SIZES_MB, THUMB_EXECUTOR, cache_dir, cached_bytes, clear_cache, evict, set_disk_cap

log = logging.getLogger("xero_wallpapers.browse")

MIN_RES = {"1440p": (2560, 1440), "4k": (3840, 2160), "8k": (7680, 4320)}
LOCAL_SORTS = {
    "res_desc": (lambda i: i.width * i.height, True),
    "res_asc": (lambda i: i.width * i.height, False),
    "size": (lambda i: i.file_size, True),
}
FILTER_KEYS = {f.name for f in fields(Filters)}
MAX_AUTO_PAGES = 4
FILL_ROWS = 24
ULTRAWIDE = 2.3
RATIO_TOLERANCE = 0.02
SIZE_CALLS_PER_MINUTE = 30
TOP_TAGS = 10
HERO_MIN_WIDTH = 1920
HERO_MAX_FILE = 4 * 1024 * 1024
# How long a page waits for its fingerprints so duplicates never flash in and out.
DUPE_HOLD_MS = 300


def screen_res(width: int, height: int) -> str:
    return f"{width}x{height}" if width > 0 and height > 0 else "any"


def pick_featured(items: list[Item]) -> Item | None:
    for item in items:
        if item.width >= HERO_MIN_WIDTH and 0 < item.file_size <= HERO_MAX_FILE:
            return item
    return items[0] if items else None


def _ratio_ok(width: int, height: int, ratio: str) -> bool:
    value = width / height
    if ratio == "ultrawide":
        return value >= ULTRAWIDE
    try:
        w, h = (float(p) for p in ratio.split(":"))
    except ValueError:
        return False
    want = w / h
    return abs(value - want) <= want * RATIO_TOLERANCE


def _sized(f: Filters, source: Source) -> bool:
    return source.sizes != "none" and (f.min_res != "any" or f.ratio != "any")


# "yes", "no", or "size" / "colour" while that is still unknown.
def _verdict(item: Item, f: Filters, source: Source) -> str:
    server = source.server_filters
    if "query" not in server and f.query.strip():
        q = f.query.strip().lower()
        if q not in item.title.lower() and not any(q in t.lower() for t in item.tags):
            return "no"
    if "tags" not in server and f.tags:
        hay = item.title.lower() + " " + " ".join(item.tags).lower()
        if not all(t.lower() in hay for t in f.tags):
            return "no"
    # Size and colour are checked here even when the server filtered them: its matching is loose.
    if _sized(f, source):
        if not (item.width > 0 and item.height > 0):
            return "size" if source.sizes == "details" else "no"
        screen = screen_size(f.min_res)
        if screen:
            if (item.width, item.height) != screen:
                return "no"
        else:
            w, h = MIN_RES.get(f.min_res, (0, 0))
            if item.width < w or item.height < h:
                return "no"
        if f.ratio != "any" and not _ratio_ok(item.width, item.height, f.ratio):
            return "no"
    if f.hue is not None:
        if not item.colors:
            return "colour"
        if not hue_matches(item.colors, f.hue):
            return "no"
    return "yes"


def _strict(f: Filters) -> bool:
    return bool(f.tags) or f.hue is not None or f.min_res != "any" or f.ratio != "any"


def _thumb_palette(url: str) -> list[str]:
    return palette(Image.open(io.BytesIO(cached_bytes(url))))


def _thumb_fingerprint(url: str) -> dupes.Fingerprint | None:
    return dupes.for_url(url, cached_bytes)


def _fingerprint_or_none(url: str) -> dupes.Fingerprint | None:
    if not url:
        return None
    try:
        return _thumb_fingerprint(url)
    except Exception as e:
        log.debug("fingerprint for %s failed: %s", url, e)
        return None


def _filters_from(base: Filters, changes: dict) -> Filters:
    values = asdict(base)
    values.update({k: v for k, v in changes.items() if k in FILTER_KEYS})
    hue = values.get("hue")
    values["hue"] = int(hue) if isinstance(hue, (int, float)) and hue >= 0 else None
    values["tags"] = [str(t) for t in values.get("tags") or []]
    return Filters(**values)


def _filter_info(items: list[Item], source: Source | None) -> dict:
    tags = Counter(t for i in items for t in dict.fromkeys(t.lower() for t in i.tags))
    return {
        "tags": [t for t, _ in tags.most_common(TOP_TAGS)],
        "resolution": source is not None and source.sizes != "none",
    }


class BrowseController(QObject):
    _loaded = pyqtSignal(int, int, object, str)
    _tagged = pyqtSignal(int, str, list)
    _sizedUp = pyqtSignal(int, str, object)
    _coloured = pyqtSignal(int, str, list)
    _fingerprinted = pyqtSignal(str, object)
    checkingChanged = pyqtSignal()
    sourcesChanged = pyqtSignal()
    currentSourceChanged = pyqtSignal()
    modeChanged = pyqtSignal()
    busyChanged = pyqtSignal()
    errorTextChanged = pyqtSignal()
    filtersChanged = pyqtSignal()
    featuredChanged = pyqtSignal()
    liveEnabledChanged = pyqtSignal()
    filterInfoChanged = pyqtSignal()

    def __init__(
        self, sources: list[Source], live_enabled: bool = False, tags=None, min_res: str = "any", screen: str = "",
        hide_duplicates: bool = True, parent=None,
    ):
        super().__init__(parent)
        self._tags = tags
        self._hide = hide_duplicates
        self._registry = {"static": dupes.Registry(), "live": dupes.Registry()}
        self._fps: dict[str, dupes.Fingerprint | None] = {}
        self._fp_wanted: set[str] = set()
        self._held: list[Item] = []
        self._hold_timer = QTimer(self)
        self._hold_timer.setSingleShot(True)
        self._hold_timer.setInterval(DUPE_HOLD_MS)
        self._hold_timer.timeout.connect(lambda: self._drain(force=True))
        self._sizes = WorkQueue(RateLimiter(max_calls=SIZE_CALLS_PER_MINUTE, stop=net.STOP), "size-check")
        self._known_sizes: dict[str, Item] = {}
        self._known_colors: dict[str, list[str]] = {}
        self._waiting: list[tuple[str, Item]] = []
        self._auto_pages = 0
        self._live_enabled = live_enabled
        self._sources = self._usable(sources)
        self._model = WallpaperModel(self)
        self._mode = "static"
        self._current = {
            kind: next((s.name for s in self._sources if s.kind == kind), "")
            for kind in ("static", "live")
        }
        self._screen = screen
        self._defaults = Filters(min_res=min_res)
        self._filters = self._defaults
        self._by_mode: dict[str, Filters] = {}
        self._busy = False
        self._error = ""
        self._featured: dict = {}
        self._featured_item: Item | None = None
        self._gen = 0
        self._page = 0
        self._failed_page = 0
        self._done = False
        self._raw: list[Item] = []
        self._all: list[Item] = []
        self._info = _filter_info([], None)
        self._loaded.connect(self._on_loaded)
        self._tagged.connect(self._on_tagged)
        self._sizedUp.connect(self._on_sized)
        self._coloured.connect(self._on_coloured)
        self._fingerprinted.connect(self._on_fingerprinted)
        self._reload(clear=True)

    @pyqtProperty(QObject, constant=True)
    def model(self):
        return self._model

    @pyqtProperty(list, notify=sourcesChanged)
    def sources(self):
        return [{"name": s.name, "label": source_label(s.name), "kind": s.kind} for s in self._sources]

    @pyqtProperty(bool, notify=liveEnabledChanged)
    def liveEnabled(self):
        return self._live_enabled

    def _usable(self, sources: list[Source]) -> list[Source]:
        return [s for s in sources if s.kind == "static" or self._live_enabled]

    def set_sources(self, sources: list[Source], live: bool):
        if live != self._live_enabled:
            self._live_enabled = live
            self.liveEnabledChanged.emit()
        self._sources = self._usable(sources)
        self.sourcesChanged.emit()
        for kind, name in self._current.items():
            if self._source(name) is None:
                self._current[kind] = next((s.name for s in self._sources if s.kind == kind), "")
        if not self._current[self._mode]:
            self._enter_mode("static")
        self.currentSourceChanged.emit()
        self._reload(clear=True)

    @pyqtProperty(str, notify=currentSourceChanged)
    def currentSource(self):
        return self._current[self._mode]

    @pyqtProperty(str, notify=modeChanged)
    def mode(self):
        return self._mode

    @pyqtProperty(str, constant=True)
    def screenRes(self):
        return self._screen

    @pyqtProperty(bool, notify=busyChanged)
    def busy(self):
        return self._busy

    @pyqtProperty(str, notify=errorTextChanged)
    def errorText(self):
        return self._error

    @pyqtProperty("QVariantMap", notify=filtersChanged)
    def filters(self):
        return asdict(self._filters)

    @pyqtProperty("QVariantMap", notify=featuredChanged)
    def featured(self):
        return self._featured

    @pyqtProperty("QVariantMap", notify=filterInfoChanged)
    def filterInfo(self):
        return self._info

    @pyqtProperty(str, notify=checkingChanged)
    def checking(self):
        need = {why for why, _ in self._waiting}
        if "size" in need:
            return "Checking sizes..."
        return "Checking colours..." if need else ""

    @pyqtSlot(str)
    def setMode(self, mode: str):
        if mode not in self._current or mode == self._mode or not self._current[mode]:
            return
        self._enter_mode(mode)
        self.currentSourceChanged.emit()
        self._reload(clear=True)

    @pyqtSlot(str)
    def setSource(self, name: str):
        source = self._source(name)
        if source is None:
            return
        if source.kind != self._mode:
            self._enter_mode(source.kind)
        self._current[self._mode] = name
        self.currentSourceChanged.emit()
        self._reload(clear=True)

    @pyqtSlot(str)
    def search(self, text: str):
        self.applyFilters({"query": text})

    @pyqtSlot(str)
    def setSort(self, sort: str):
        self.applyFilters({"sort": sort})

    @pyqtSlot("QVariantMap")
    def applyFilters(self, changes: dict):
        self._filters = _filters_from(self._filters, changes)
        self.filtersChanged.emit()
        self._reload(clear=False)

    def set_hide_duplicates(self, on: bool):
        if on == self._hide:
            return
        self._hide = on
        self._registry = {"static": dupes.Registry(), "live": dupes.Registry()}
        self._reload(clear=True)

    def set_match_screen(self, on: bool):
        previous, new = ("any", self._screen) if on else (self._screen, "any")
        if not screen_size(self._screen):
            return
        self._defaults = replace(self._defaults, min_res=new)
        for mode, f in self._by_mode.items():
            if f.min_res == previous:
                self._by_mode[mode] = replace(f, min_res=new)
        if self._filters.min_res == previous:
            self.applyFilters({"min_res": new})

    def _enter_mode(self, mode: str):
        # Each mode keeps its own filters: live sources list no colours or tags and few sizes,
        # so static filters carried over would empty the page. Only the search text is shared.
        self._by_mode[self._mode] = self._filters
        self._filters = replace(self._by_mode.get(mode, self._defaults), query=self._filters.query)
        self._mode = mode
        self.modeChanged.emit()
        self.filtersChanged.emit()

    @pyqtSlot(result=int)
    def featuredIndex(self) -> int:
        return next((i for i, it in enumerate(self._raw) if it is self._featured_item), -1)

    @pyqtSlot()
    def loadMore(self):
        if self._busy or self._done or self._error or not self._page:
            return
        self._request(self._page + 1)

    @pyqtSlot()
    def retry(self):
        if self._failed_page > 1:
            self._request(self._failed_page)
        else:
            self._reload(clear=False)

    def _source(self, name: str) -> Source | None:
        return next((s for s in self._sources if s.name == name), None)

    def _set_busy(self, busy: bool):
        if busy != self._busy:
            self._busy = busy
            self.busyChanged.emit()

    def _set_error(self, text: str):
        if text != self._error:
            self._error = text
            self.errorTextChanged.emit()

    def _reload(self, clear: bool):
        self._gen += 1
        if self._tags is not None:
            self._tags.clear()
        self._page = 0
        self._done = False
        self._auto_pages = 0
        self._sizes.clear()
        self._set_waiting([])
        self._held = []
        self._hold_timer.stop()
        if clear:
            self._raw = []
            self._set_all([], None)
            self._model.set_items([])
            self._featured = {}
            self.featuredChanged.emit()
        self._request(1)

    def _request(self, page: int):
        source = self._source(self.currentSource)
        if source is None:
            return
        self._set_busy(True)
        self._set_error("")
        gen = self._gen
        server = Filters(
            **{k: v for k, v in asdict(self._filters).items() if k in source.server_filters}
        )

        def work():
            try:
                items, error = source.search(page, server), ""
            except SourceError as e:
                items, error = [], str(e) or "unknown error"
            except Exception as e:
                log.exception("source %s crashed", source.name)
                items, error = [], f"unexpected error ({type(e).__name__})"
            self._loaded.emit(gen, page, items, error)

        net.EXECUTOR.submit(work)

    def _on_loaded(self, gen: int, page: int, items: list, error: str):
        if gen != self._gen:
            return
        self._set_busy(False)
        source = self._source(self.currentSource)
        if error:
            self._failed_page = page
            self._set_error(f"Couldn't load {source_label(source.name)}: {error}")
            return
        self._failed_page = 0
        self._page = page
        self._done = not items
        items = [self._known_sizes.get(i.page_url, i) for i in items]
        for item in items:
            if not item.colors and item.thumb_url in self._known_colors:
                item.colors = self._known_colors[item.thumb_url]
        self._set_all(items if page == 1 else self._all + items, source)
        fresh, waiting = [], []
        for item in items:
            verdict = _verdict(item, self._filters, source)
            if verdict == "yes":
                fresh.append(item)
            elif verdict != "no":
                waiting.append((verdict, item))
        sort = LOCAL_SORTS.get(self._filters.sort)
        if sort:
            key, reverse = sort
            fresh.sort(key=key, reverse=reverse)
        if page == 1:
            self._raw = []
            self._model.set_items([])
            self._featured_item = None
        self._admit(fresh)
        if self._featured_item is None:
            self._set_featured(None)
        self._set_waiting(self._waiting + waiting)
        for why, item in waiting:
            self._check(gen, why, item, source)
        self._maybe_fill()

    def _admit(self, items: list[Item]):
        if not self._hide:
            self._show(items)
            return
        self._held.extend(items)
        for item in items:
            self._want_fingerprint(item.thumb_url)
        self._drain(force=False)

    def _want_fingerprint(self, url: str):
        if not url or url in self._fps or url in self._fp_wanted:
            return
        self._fp_wanted.add(url)
        THUMB_EXECUTOR.submit(lambda: _safe_emit(self._fingerprinted, url, _fingerprint_or_none(url)))

    def _drain(self, force: bool):
        # Admits the held items together once all fingerprints are known, or at the deadline.
        if not force and any(it.thumb_url and it.thumb_url not in self._fps for it in self._held):
            if not self._hold_timer.isActive():
                self._hold_timer.start()
            return
        self._hold_timer.stop()
        ready, self._held = self._held, []
        registry = self._registry[self._mode]
        show: list[Item] = []
        for item in ready:
            winner, loser = registry.place(item, self._fps.get(item.thumb_url))
            if loser is None:
                show.append(item)
            elif loser is not item:
                self._swap(loser, winner, show)
        self._show(show)

    def _swap(self, loser: Item, winner: Item, pending: list[Item]):
        # A later copy with more pixels takes the earlier copy's place.
        for i, it in enumerate(pending):
            if it is loser:
                pending[i] = winner
                return
        row = self._model.row_of(loser)
        if row < 0:
            pending.append(winner)
            return
        self._raw[row] = winner
        self._model.replace(row, winner)
        if loser is self._featured_item:
            self._set_featured(winner)

    def _on_fingerprinted(self, url: str, fp):
        self._fp_wanted.discard(url)
        self._fps[url] = fp
        if not self._hide:
            return
        if any(it.thumb_url == url for it in self._held):
            self._drain(force=False)
        if fp is None:
            return
        registry = self._registry[self._mode]
        for item in [it for it in self._raw if it.thumb_url == url]:
            winner, loser = registry.place(item, fp)
            if loser is None:
                continue
            lost, won = self._model.row_of(loser), self._model.row_of(winner)
            if lost < 0:
                continue
            if won > lost:
                self._raw[lost] = winner
                self._model.replace(lost, winner)
                lost = won
            del self._raw[lost]
            self._model.remove(lost)
            if loser is self._featured_item:
                self._set_featured(winner if won >= 0 else pick_featured(self._raw))

    def _show(self, items: list[Item]):
        if not items:
            return
        self._raw.extend(items)
        self._model.append_items(items)
        if self._featured_item is None:
            self._set_featured(pick_featured(items))
        self._request_tags(self._gen, items)

    def _set_waiting(self, waiting: list[tuple[str, Item]]):
        before = self.checking
        self._waiting = waiting
        if self.checking != before:
            self.checkingChanged.emit()

    def _check(self, gen: int, why: str, item: Item, source: Source):
        if why == "size":
            self._sizes.request(item.page_url, lambda: source.details(item),
                                lambda url, found: _safe_emit(self._sizedUp, gen, url, found))
        else:
            url = item.thumb_url

            def work():
                try:
                    found = _thumb_palette(url)
                except Exception as e:
                    log.warning("palette for %s failed: %s", url, e)
                    found = []
                _safe_emit(self._coloured, gen, url, found)

            THUMB_EXECUTOR.submit(work)

    def _on_sized(self, gen: int, url: str, found):
        if gen != self._gen:
            return
        if found is not None and found.width > 0 and found.height > 0:
            self._known_sizes[url] = found
        self._resolve(lambda item: item.page_url == url,
                      lambda item: self._known_sizes.get(url) or replace(item, width=-1, height=-1))

    def _on_coloured(self, gen: int, url: str, colors: list):
        if gen != self._gen:
            return
        if colors:
            self._known_colors[url] = colors

        def update(item):
            item.colors = colors or ["#808080"]
            return item

        self._resolve(lambda item: item.thumb_url == url, update)

    def _resolve(self, hit, update):
        source = self._source(self.currentSource)
        keep, admit = [], []
        for why, item in self._waiting:
            if not hit(item):
                keep.append((why, item))
                continue
            item = update(item)
            # A failed size check leaves -1: it stays out instead of being fetched again.
            verdict = "no" if item.width < 0 else _verdict(item, self._filters, source)
            if verdict == "yes":
                admit.append(item)
            elif verdict != "no":
                keep.append((verdict, item))
                self._check(self._gen, verdict, item, source)
        self._admit(admit)
        self._set_waiting(keep)
        self._maybe_fill()

    def _maybe_fill(self):
        if (self._busy or self._done or self._error or self._waiting or not self._page
                or not _strict(self._filters) or self._model.rowCount() >= FILL_ROWS
                or self._auto_pages >= MAX_AUTO_PAGES):
            return
        self._auto_pages += 1
        self._request(self._page + 1)

    def _request_tags(self, gen: int, items: list[Item]):
        ids = [i.extra["id"] for i in items if i.source == "wallhaven" and not i.tags and i.extra.get("id")]
        if self._tags is not None and ids:
            self._tags.request(ids, lambda wid, tags: _safe_emit(self._tagged, gen, wid, tags))

    def _on_tagged(self, gen: int, wid: str, tags: list):
        if gen != self._gen:
            return
        for item in self._all:
            if item.source == "wallhaven" and item.extra.get("id") == wid:
                item.tags = list(tags)
        self._set_all(self._all, self._source(self.currentSource))
        title = title_from_tags(tags)
        if not title:
            return
        for row in range(self._model.rowCount()):
            item = self._model.item(row)
            if item.source == "wallhaven" and item.extra.get("id") == wid and item.title != title:
                self._model.update_title(row, title)
                if item is self._featured_item:
                    self._featured = {**self._featured, "title": title}
                    self.featuredChanged.emit()

    def _set_all(self, items: list[Item], source: Source | None):
        self._all = list(items)
        info = _filter_info(self._all, source)
        if info != self._info:
            self._info = info
            self.filterInfoChanged.emit()

    def _set_featured(self, item: Item | None):
        self._featured_item = item
        if item is None:
            self._featured = {}
        else:
            self._featured = {
                "title": item.title,
                "image": cover_url(item),
                "resolution": item.resolution(),
                "source": source_label(item.source),
                "author": item.author,
                "kind": item.kind,
                "duration": item.duration,
            }
        self.featuredChanged.emit()


RATIOS = {"16:9": 16 / 9, "16:10": 16 / 10, "21:9": 21 / 9, "32:9": 32 / 9, "4:3": 4 / 3,
          "5:4": 5 / 4, "3:2": 3 / 2, "1:1": 1, "9:16": 9 / 16}


def _aspect(w: int, h: int) -> str:
    if not w or not h:
        return ""
    value = w / h
    for name, want in RATIOS.items():
        if abs(value - want) <= want * 0.03:
            return name
    g = math.gcd(w, h)
    if w // g <= 50 and h // g <= 50:
        return f"{w // g}:{h // g}"
    return f"{value:.2f}:1"


def _mapped_fields(first: dict) -> list[str]:
    w, h = first.get("width") or 0, first.get("height") or 0
    rows = [
        ("Title", first.get("title")),
        ("Thumbnail", first.get("thumb_url")),
        ("Link", first.get("page_url")),
        ("Resolution", f"{w} × {h}" if w and h else ""),
        ("Tags", ", ".join(first.get("tags") or [])),
        ("Author", first.get("author")),
        ("Size", _size(first.get("file_size") or 0)),
    ]
    return [f"{label}: {value}" for label, value in rows if value]


def _size(n: int) -> str:
    if n <= 0:
        return ""
    value, unit = float(n), "B"
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1000 or unit == "GB":
            break
        value /= 1000
    return f"{value:.1f}".rstrip("0").rstrip(".") + f" {unit}"


def _format(file_type: str) -> str:
    return file_type.rsplit("/", 1)[-1].upper() if file_type else ""


def _duration(seconds: float) -> str:
    if seconds <= 0:
        return ""
    s = round(seconds)
    return f"{s // 60}:{s % 60:02d}"


def _date(value: str) -> str:
    m = re.match(r"\d{4}-\d{2}-\d{2}", value)
    return m.group(0) if m else value


def detail_rows(item: Item) -> list[dict]:
    if item.kind == "live":
        codec = " · ".join(p for p in (item.codec, _format(item.file_type)) if p)
        rows = [
            ("Resolution", item.resolution()),
            ("Duration", _duration(item.duration)),
            ("Frame rate", f"{item.fps:g} fps" if item.fps > 0 else ""),
            ("Codec", codec),
        ]
    else:
        rows = [
            ("Resolution", item.resolution()),
            ("Aspect ratio", _aspect(item.width, item.height)),
            ("Format", _format(item.file_type)),
        ]
    stats = f"{item.views:,} · {item.favorites:,}" if item.views or item.favorites else ""
    rows += [
        ("File size", _size(item.file_size)),
        ("Source", source_label(item.source)),
        ("Uploader", item.author),
        ("Views · Favourites", stats if item.kind == "static" else ""),
        ("Uploaded", _date(item.uploaded)),
    ]
    return [{"k": k, "v": v} for k, v in rows if v]


def _http(url: str) -> str:
    return url if urlparse(url).scheme.lower() in SAFE_SCHEMES else ""


def _preview_url(item: Item) -> str:
    # The sources' preview clips are a few MB; the download is the full 4K file.
    return _http(item.extra.get("preview_video") or item.download_url) if item.kind == "live" else ""


def _item_map(index: int, item: Item, colors: list[str], video: str) -> dict:
    data = asdict(item)
    data.update(
        index=index,
        sourceLabel=source_label(item.source),
        resolution=item.resolution(),
        thumb=thumb_url(item.thumb_url),
        fill=fill_url(item.thumb_url),
        image=thumb_url(_http(item.download_url)) if item.kind == "static" else "",
        video=video,
        rows=detail_rows(item),
        palette=colors,
    )
    return data


class DetailController(QObject):
    _detailed = pyqtSignal(int, int, object, list, str)
    _previewed = pyqtSignal(int, str, object)
    itemChanged = pyqtSignal()
    loadingChanged = pyqtSignal()
    previewReady = pyqtSignal(int, str)

    def __init__(self, model: WallpaperModel, sources: list[Source], parent=None):
        super().__init__(parent)
        self._model = model
        self._sources = {s.name: s for s in sources}
        self._item: dict = {}
        self._loading = False
        self._gen = 0
        self._previews: dict[str, str] = {}
        self._preview_pending: set[str] = set()
        self._open_item: Item | None = None
        model.rowsRemoved.connect(self._on_rows_removed)
        self._detailed.connect(self._on_detailed)
        self._previewed.connect(self._on_previewed)

    def set_sources(self, sources: list[Source]):
        self._sources = {s.name: s for s in sources}

    @pyqtProperty("QVariantMap", notify=itemChanged)
    def item(self):
        return self._item

    @pyqtProperty(bool, notify=loadingChanged)
    def loading(self):
        return self._loading

    def _set_loading(self, loading: bool):
        if loading != self._loading:
            self._loading = loading
            self.loadingChanged.emit()

    @pyqtSlot(int)
    def open(self, index: int):
        if not 0 <= index < self._model.rowCount():
            return
        self._gen += 1
        gen = self._gen
        item = self._model.item(index)
        self._open_item = item
        source = self._sources.get(item.source)
        self._item = _item_map(index, item, [], "")
        self.itemChanged.emit()
        self._set_loading(True)

        def work():
            full = item
            if source is not None:
                try:
                    full = source.details(item)
                except Exception as e:
                    log.warning("details for %s failed: %s", item.page_url, e)
            try:
                colors = palette(Image.open(io.BytesIO(cached_bytes(full.thumb_url))))
            except Exception as e:
                log.debug("palette for %s failed: %s", full.thumb_url, e)
                colors = list(full.colors)
            self._detailed.emit(gen, index, full, colors, _preview_url(full))

        net.EXECUTOR.submit(work)

    @pyqtSlot(int)
    def requestPreview(self, index: int):
        if not 0 <= index < self._model.rowCount():
            return
        item = self._model.item(index)
        key = item.page_url
        if item.kind != "live":
            return
        if key in self._previews:
            self._emit_preview(index, key)
            return
        if key in self._preview_pending:
            return
        self._preview_pending.add(key)
        source = self._sources.get(item.source)

        def work():
            url = None
            try:
                full = source.details(item) if source is not None else item
                url = _preview_url(full)
            except Exception as e:
                log.warning("preview for %s failed: %s", item.page_url, e)
            self._previewed.emit(index, key, url)

        net.EXECUTOR.submit(work)

    def _on_previewed(self, index: int, key: str, url):
        self._preview_pending.discard(key)
        # A failed fetch is not cached so the next visit retries.
        if url is not None:
            self._previews[key] = url
            self._emit_preview(index, key)

    def _emit_preview(self, index: int, key: str):
        url = self._previews[key]
        if url and 0 <= index < self._model.rowCount() and self._model.item(index).page_url == key:
            self.previewReady.emit(index, url)

    def _on_rows_removed(self, *_):
        # A hidden duplicate shifts the rows after it; -1 means the open item itself was hidden.
        if self._item and self._open_item is not None:
            index = self._model.row_of(self._open_item)
            if index != self._item.get("index"):
                self._item = {**self._item, "index": index}
                self.itemChanged.emit()

    def _on_detailed(self, gen: int, index: int, item: Item, colors: list, video: str):
        if gen != self._gen:
            return
        index = self._item.get("index", index)
        if 0 <= index < self._model.rowCount():
            row = self._model.item(index)
            if row.page_url == item.page_url and row.title != item.title:
                self._model.update_title(index, item.title)
        self._item = _item_map(index, item, colors, video)
        self.itemChanged.emit()
        self._set_loading(False)


class DownloadController(QObject):
    progress = pyqtSignal(str, "qint64", "qint64")
    # title, path, set as wallpaper, already in the Library
    finished = pyqtSignal(str, str, bool, bool)
    failed = pyqtSignal(str, str)
    editReady = pyqtSignal(str, str)

    PROGRESS_INTERVAL = 0.1

    def __init__(self, config: Config, model: WallpaperModel, sources: list[Source], parent=None):
        super().__init__(parent)
        self._config = config
        self._model = model
        self._sources = {s.name: s for s in sources}
        self._cancel = threading.Event()
        self._active: set[tuple[str, str]] = set()
        self._lock = threading.Lock()

    def cancel(self):
        self._cancel.set()

    def set_sources(self, sources: list[Source]):
        self._sources = {s.name: s for s in sources}

    @pyqtSlot(int)
    def setWallpaper(self, index: int):
        self.download(index, True)

    @pyqtSlot(int, bool)
    def download(self, index: int, setAfter: bool):
        self._submit(index, setAfter, False)

    @pyqtSlot(int)
    def edit(self, index: int):
        self._submit(index, False, True)

    def _submit(self, index: int, set_after: bool, edit: bool):
        if not 0 <= index < self._model.rowCount():
            self.failed.emit("", "That wallpaper is no longer listed")
            return
        item = self._model.item(index)
        source = self._sources.get(item.source)
        if source is None:
            self.failed.emit(item.title or source_label(item.source), "Its source is no longer enabled")
            return
        if edit and item.kind != "static":
            return
        key = (item.source, item.page_url)
        with self._lock:
            if key in self._active:
                return
            self._active.add(key)
        folder_key = "live_download_dir" if item.kind == "live" else "static_download_dir"
        folder = Path(self._config.get(folder_key)).expanduser()
        skip = edit or bool(self._config.get("skip_duplicates"))
        net.EXECUTOR.submit(self._work, item, source, folder, skip, set_after, key, edit)

    @staticmethod
    def _titled(item: Item, source: Source) -> Item:
        # Wallhaven titles arrive with the tags; without one the file would get a generic name.
        try:
            return source.details(item)
        except (SourceError, Stopped, requests.RequestException, OSError) as e:
            log.info("no title for %s: %s", item.page_url, e)
            return item

    @staticmethod
    def _existing(folder: Path, item: Item, fp: dupes.Fingerprint | None) -> Path | None:
        found = dupes.find_copy(folder, item.kind, fp, dupes.item_ratio(item, fp)) if fp is not None else None
        # Videos only carry fingerprints once seen, so they keep the name check too.
        if found is None and (fp is None or item.kind == "live"):
            found = already_downloaded(folder, item)
        return found

    def _work(self, item: Item, source: Source, folder: Path, skip: bool, set_after: bool, key, edit: bool):
        title = item.title or source_label(item.source)
        last = 0.0

        def report(done: int, total: int):
            nonlocal last
            now = time.monotonic()
            if now - last >= self.PROGRESS_INTERVAL or (total and done >= total):
                last = now
                self.progress.emit(title, done, total)

        try:
            if not item.title:
                item = self._titled(item, source)
            fp = _fingerprint_or_none(item.thumb_url)
            path = self._existing(folder, item, fp) if skip else None
            existing = path is not None
            if path is None:
                url = source.resolve_download(item)
                path = download(url, folder, item, report, self._cancel)
                if item.kind == "live" and fp is not None:
                    dupes.remember_file(path, fp)
            if set_after:
                (set_live if item.kind == "live" else set_static)(path)
            self.finished.emit(title, str(path), set_after, existing)
            if edit:
                self.editReady.emit(title, str(path))
        except DownloadCancelled:
            _safe_emit(self.failed, title, "Download cancelled")
        except (SourceError, WallpaperError, ValueError, OSError, requests.RequestException) as e:
            self.failed.emit(title, str(e) or type(e).__name__)
        except Exception as e:
            log.exception("download of %s crashed", item.page_url)
            self.failed.emit(title, f"unexpected error ({type(e).__name__})")
        finally:
            with self._lock:
                self._active.discard(key)


# mkstemp creates 0600 files; saved wallpapers should get the user's normal permissions.
_UMASK = os.umask(0o022)
os.umask(_UMASK)

LOG_LINES = 200
ERROR_LINES = 15
QUIT_WAIT_MS = 3000


def _safe_emit(signal, *args):
    # Worker threads may finish after the app has torn the controller down.
    try:
        signal.emit(*args)
    except RuntimeError:
        pass


class SvwrController(QObject):
    changed = pyqtSignal()
    finished = pyqtSignal(bool)
    _stepsReady = pyqtSignal(int, object, str)
    _stepDone = pyqtSignal(int, str, str)
    _progressed = pyqtSignal(int, float)
    _latestReady = pyqtSignal(str)
    _depsReady = pyqtSignal(list)

    def __init__(self, config: Config, parent=None):
        super().__init__(parent)
        self._config = config
        self._distro = svwr.distro()
        self._version = ""
        self._latest = ""
        self._missing: list[str] = []
        self._running = False
        self._action = ""
        self._stage = ""
        self._progress = 0.0
        self._lines: list[str] = []
        self._error = ""
        self._restart_hint = False
        self._gen = 0
        self._steps: list = []
        self._index = 0
        self._proc: QProcess | None = None
        self._stepsReady.connect(self._on_steps)
        self._stepDone.connect(self._on_step_done)
        self._progressed.connect(self._on_progress)
        self._latestReady.connect(self._on_latest)
        self._depsReady.connect(self._on_deps)
        self.detect()

    @pyqtProperty(bool, notify=changed)
    def installed(self):
        return bool(self._version)

    @pyqtProperty(str, notify=changed)
    def version(self):
        return self._version

    @pyqtProperty(str, notify=changed)
    def latest(self):
        return self._latest

    @pyqtProperty(bool, notify=changed)
    def updateAvailable(self):
        return self.installed and svwr.is_newer(self._latest, self._version)

    @pyqtProperty(bool, notify=changed)
    def running(self):
        return self._running

    @pyqtProperty(str, notify=changed)
    def action(self):
        return self._action

    @pyqtProperty(str, notify=changed)
    def stage(self):
        return self._stage

    @pyqtProperty(float, notify=changed)
    def progress(self):
        return self._progress

    @pyqtProperty(str, notify=changed)
    def log(self):
        return "\n".join(self._lines)

    @pyqtProperty(str, notify=changed)
    def error(self):
        return self._error

    @pyqtProperty(bool, notify=changed)
    def restartHint(self):
        return self._restart_hint

    @pyqtProperty(str, constant=True)
    def distro(self):
        return self._distro

    @pyqtProperty(list, notify=changed)
    def missingDeps(self):
        return self._missing

    def detect(self):
        self._version = svwr.installed_version() or ""
        self.changed.emit()

    @pyqtSlot()
    def checkDeps(self):
        net.EXECUTOR.submit(lambda: _safe_emit(self._depsReady, svwr.missing_runtime_deps()))

    def _on_deps(self, missing: list):
        self._missing = missing
        self.changed.emit()

    def checkForUpdates(self):
        if not self.installed:
            return
        if self._distro in ("arch", "other") and not svwr.archive_install():
            return

        def work():
            try:
                latest = svwr.latest_available() or ""
            except Exception as e:
                log.warning("SVWR update check failed: %s", e)
                latest = ""
            _safe_emit(self._latestReady, latest)

        net.EXECUTOR.submit(work)

    def _on_latest(self, latest: str):
        if not latest:
            return
        self._latest = latest
        self.changed.emit()

    @pyqtSlot()
    @pyqtSlot(bool)
    def install(self, allowRepo: bool = False):
        self._start("install", lambda: svwr.install_steps(False, allow_repo=allowRepo))

    @pyqtSlot()
    def update(self):
        self._start("update", lambda: svwr.install_steps(True))

    def shutdown(self):
        self._gen += 1
        proc, self._proc = self._proc, None
        if proc is None or proc.state() == QProcess.ProcessState.NotRunning:
            return
        log.warning("quitting while %s is running; terminating it", proc.program())
        proc.terminate()
        if not proc.waitForFinished(QUIT_WAIT_MS):
            log.warning("%s did not exit; killing it", proc.program())
            proc.kill()
            proc.waitForFinished(QUIT_WAIT_MS)

    @pyqtSlot()
    def installDeps(self):
        missing = list(self._missing)
        if missing:
            self._start("deps", lambda: [svwr.deps_step(missing)])

    @pyqtSlot()
    def copyLog(self):
        QGuiApplication.clipboard().setText(self.log)

    def _start(self, action: str, plan):
        if self._running:
            return
        self._gen += 1
        gen = self._gen
        self._running = True
        self._action = action
        self._error = ""
        self._restart_hint = False
        self._lines = []
        self._progress = 0.0
        self._stage = "Preparing"
        self.changed.emit()

        def work():
            try:
                steps, error = plan(), ""
            except Exception as e:
                steps, error = [], str(e) or type(e).__name__
            _safe_emit(self._stepsReady, gen, steps, error)

        net.EXECUTOR.submit(work)

    def _append(self, text: str):
        lines = [line for line in text.splitlines() if line.strip()]
        if not lines:
            return
        self._lines = (self._lines + lines)[-LOG_LINES:]
        self._stage = lines[-1]
        self.changed.emit()

    def _on_steps(self, gen: int, steps: list, error: str):
        if gen != self._gen:
            return
        if error:
            self._fail(error)
            return
        self._steps = steps
        self._index = 0
        self._next()

    def _next(self):
        if self._index >= len(self._steps):
            self._succeed()
            return
        self._progress = self._index / len(self._steps)
        step = self._steps[self._index]
        self._index += 1
        if step[0] == "download":
            _, url, sha256, name = step
            self._append(f"Downloading {name}")
            net.EXECUTOR.submit(self._download, self._gen, url, sha256, name)
        elif step[0] == "install":
            self._append(f"Installing {step[1]}")
            net.EXECUTOR.submit(self._install_archive, self._gen, step[1])
        else:
            self._run(step[1])

    def _download(self, gen: int, url: str, sha256: str, name: str):
        def report(done: int, total: int):
            if total:
                _safe_emit(self._progressed, gen, done / total)

        try:
            svwr.download_archive(url, sha256, name, report)
            error = ""
        except svwr.SvwrError as e:
            error = str(e)
        except Exception as e:
            log.exception("SVWR download crashed")
            error = f"unexpected error ({type(e).__name__})"
        _safe_emit(self._stepDone, gen, error, "Download verified")

    def _install_archive(self, gen: int, name: str):
        try:
            svwr.install_archive(name)
            error = ""
        except svwr.SvwrError as e:
            error = str(e)
        except Exception as e:
            log.exception("SVWR install crashed")
            error = f"unexpected error ({type(e).__name__})"
        _safe_emit(self._stepDone, gen, error, "Installed into " + str(kpackage.USER_DIR))

    def _on_progress(self, gen: int, fraction: float):
        if gen == self._gen and self._steps:
            self._progress = (self._index - 1 + fraction) / len(self._steps)
            self.changed.emit()

    def _on_step_done(self, gen: int, error: str, done: str):
        if gen != self._gen:
            return
        if error:
            self._fail(error)
        else:
            self._append(done)
            self._next()

    def _run(self, argv: list[str]):
        self._append("$ " + " ".join(argv))
        proc = QProcess(self)
        proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        proc.readyReadStandardOutput.connect(
            lambda: self._append(bytes(proc.readAllStandardOutput()).decode(errors="replace"))
        )
        proc.finished.connect(lambda code, status: self._on_finished(proc, code, status))
        proc.errorOccurred.connect(lambda err: self._on_proc_error(proc, err))
        self._proc = proc
        proc.start(argv[0], argv[1:])

    def _on_proc_error(self, proc: QProcess, err):
        if err == QProcess.ProcessError.FailedToStart and proc is self._proc:
            self._proc = None
            proc.deleteLater()
            self._fail(f"{proc.program()} could not be started")

    def _on_finished(self, proc: QProcess, code: int, status):
        if proc is not self._proc:
            return
        self._proc = None
        proc.deleteLater()
        if status != QProcess.ExitStatus.NormalExit or code != 0:
            self._fail(f"{proc.program()} exited with {code}")
        else:
            self._next()

    def _fail(self, summary: str):
        self._append(summary)
        self._error = "\n".join(self._lines[-ERROR_LINES:])
        self._running = False
        self._stage = ""
        self.detect()
        self.finished.emit(False)

    def _succeed(self):
        action = self._action
        self._running = False
        self._progress = 1.0
        self.detect()
        if action == "deps":
            self._stage = "Packages installed"
            self.checkDeps()
        else:
            self._stage = f"Updated to {self._version}" if action == "update" else f"Installed {self._version}"
            self._latest = self._version if action == "update" else self._latest
            self._restart_hint = True
        self.changed.emit()
        self.finished.emit(True)


BUILTIN_URLS = {
    "wallhaven": "wallhaven.cc/api/v1/search?q={query}&page={page}",
    "4kwallpapers": "4kwallpapers.com/search/?text={query}",
    "moewalls": "moewalls.com/page/{page}/?s={query}",
    "motionbgs": "motionbgs.com/{page}/?s={query}",
}
DIR_KEYS = {"static": "static_download_dir", "live": "live_download_dir"}
SLIDE_OPTIONS = {
    "slideshowMinutes": ("slideshow_minutes", slideshow.clamp_minutes),
    "slideshowOrder": ("slideshow_order", lambda v: v if v in slideshow.ORDERS else None),
    "slideshowTransition": ("slideshow_transition", lambda v: v if v in slideshow.TRANSITIONS else None),
    "slideshowTransitionMs": ("slideshow_transition_ms", slideshow.clamp_ms),
}


class AppUpdateController(QObject):
    changed = pyqtSignal()
    failed = pyqtSignal(str)
    _found = pyqtSignal(object)
    _progressed = pyqtSignal(float)
    _done = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._target = update.running_appimage()
        self._info: update.UpdateInfo | None = None
        self._running = False
        self._progress = 0.0
        self._found.connect(self._on_found)
        self._progressed.connect(self._on_progress)
        self._done.connect(self._on_done)

    @pyqtProperty(bool, notify=changed)
    def available(self):
        return self._info is not None

    @pyqtProperty(str, notify=changed)
    def version(self):
        return self._info.version if self._info else ""

    @pyqtProperty(bool, notify=changed)
    def running(self):
        return self._running

    @pyqtProperty(float, notify=changed)
    def progress(self):
        return self._progress

    def check(self):
        if self._target is not None:
            net.EXECUTOR.submit(lambda: _safe_emit(self._found, update.check()))

    def _on_found(self, info):
        self._info = info
        self.changed.emit()

    @pyqtSlot()
    def install(self):
        info, target = self._info, self._target
        if info is None or target is None or self._running:
            return
        self._running = True
        self._progress = 0.0
        self.changed.emit()

        def work():
            try:
                update.install(info, target, lambda fraction: _safe_emit(self._progressed, fraction))
                error = ""
            except update.UpdateError as e:
                error = str(e) or "unknown error"
            _safe_emit(self._done, error)

        net.EXECUTOR.submit(work)

    def _on_progress(self, fraction: float):
        self._progress = fraction
        self.changed.emit()

    def _on_done(self, error: str):
        if error:
            self._running = False
            self.changed.emit()
            self.failed.emit(error)
            return
        update.relaunch_after_exit(self._target)
        QGuiApplication.quit()


class SettingsController(QObject):
    liveEnabledChanged = pyqtSignal()
    dirsChanged = pyqtSignal()
    togglesChanged = pyqtSignal()
    sourcesChanged = pyqtSignal()
    matchScreenChanged = pyqtSignal()
    hideDuplicatesChanged = pyqtSignal()
    setupRequested = pyqtSignal()
    cacheCleared = pyqtSignal(str)
    testResult = pyqtSignal("QVariantMap")
    slideshowChanged = pyqtSignal()
    confirmSlideshowOverLive = pyqtSignal()
    slideshowFailed = pyqtSignal(str)
    _tested = pyqtSignal(int, "QVariantMap")
    _cleared = pyqtSignal(int)
    _slideApplied = pyqtSignal(int, bool, str)
    _slideNeedsConfirm = pyqtSignal(int)
    _slideSynced = pyqtSignal(bool)
    _singleWallpaperSet = pyqtSignal(str)

    def __init__(self, config: Config, svwr_ctrl: SvwrController, parent=None):
        super().__init__(parent)
        self._config = config
        self._svwr = svwr_ctrl
        self._test_gen = 0
        self._cleared.connect(lambda freed: self.cacheCleared.emit(_size(freed) or "0 B"))
        set_disk_cap(self.cacheSizeMb)
        self._tested.connect(self._on_tested)
        self._live = self._get_live()
        svwr_ctrl.changed.connect(self._sync_live)
        self._slide_gen = 0
        self._slide_busy = False
        self._confirm_gen = None
        # appletsrc is saved lazily, so remember live wallpapers set from this app.
        self._last_set_live = False
        self._slide_available, self._slide_reason = slideshow.available()
        self._slideApplied.connect(self._on_slide_applied)
        self._slideNeedsConfirm.connect(self._on_slide_needs_confirm)
        self._slideSynced.connect(self._on_slide_synced)
        self._singleWallpaperSet.connect(self._on_single_wallpaper_set)
        wallpaper.listeners.append(weakref.WeakMethod(self._wallpaper_set))
        if self._slide_available:
            folder = self.staticDir
            slideshow.EXECUTOR.submit(self._read_slide_state, folder)

    def _get_live(self):
        return bool(self._config.get("live_enabled")) and self._svwr.installed

    def _sync_live(self):
        if self._get_live() != self._live:
            self._live = self._get_live()
            self.liveEnabledChanged.emit()

    def _set_live(self, value: bool):
        value = bool(value)
        if value and not self._svwr.installed:
            log.info("refusing to enable live wallpapers: SVWR is not installed")
            value = False
        if value != bool(self._config.get("live_enabled")):
            self._config.set("live_enabled", value)
        self._live = self._get_live()
        self.liveEnabledChanged.emit()

    liveEnabled = pyqtProperty(bool, _get_live, _set_live, notify=liveEnabledChanged)

    @pyqtProperty(str, notify=dirsChanged)
    def staticDir(self):
        return self._config.get("static_download_dir")

    @pyqtProperty(str, notify=dirsChanged)
    def liveDir(self):
        return self._config.get("live_download_dir")

    @pyqtSlot(str, str)
    def setDir(self, kind: str, url: str):
        key = DIR_KEYS.get(kind)
        path = QUrl(url).toLocalFile() if url.startswith("file:") else url
        if key and path:
            changed = path != self._config.get(key)
            self._config.set(key, path)
            self.dirsChanged.emit()
            if changed and kind == "static" and self.slideshowEnabled:
                self._apply_slideshow(not self.slideshowFolderProblem)

    def _set_toggle(self, key: str, value: bool):
        self._config.set(key, bool(value))
        self.togglesChanged.emit()

    skipDuplicates = pyqtProperty(
        bool, lambda self: bool(self._config.get("skip_duplicates")),
        lambda self, v: self._set_toggle("skip_duplicates", v), notify=togglesChanged,
    )

    def _set_hide(self, value: bool):
        if bool(value) != bool(self._config.get("hide_duplicates")):
            self._set_toggle("hide_duplicates", value)
            self.hideDuplicatesChanged.emit()

    hideDuplicates = pyqtProperty(
        bool, lambda self: bool(self._config.get("hide_duplicates")), _set_hide, notify=togglesChanged,
    )

    def _set_safe(self, value: bool):
        if bool(value) != bool(self._config.get("safe_content")):
            self._set_toggle("safe_content", value)
            self.sourcesChanged.emit()

    safeContent = pyqtProperty(
        bool, lambda self: bool(self._config.get("safe_content")), _set_safe, notify=togglesChanged,
    )

    def _set_match(self, value: bool):
        if bool(value) != bool(self._config.get("match_screen")):
            self._set_toggle("match_screen", value)
            self.matchScreenChanged.emit()

    matchScreen = pyqtProperty(
        bool, lambda self: bool(self._config.get("match_screen")), _set_match, notify=togglesChanged,
    )

    def _get_cache_size(self) -> int:
        size = self._config.get("cache_size_mb")
        return size if size in CACHE_SIZES_MB else 500

    def _set_cache_size(self, value: int):
        if value not in CACHE_SIZES_MB:
            return
        self._config.set("cache_size_mb", int(value))
        set_disk_cap(int(value))
        THUMB_EXECUTOR.submit(evict, cache_dir())
        self.togglesChanged.emit()

    cacheSizeMb = pyqtProperty(int, _get_cache_size, _set_cache_size, notify=togglesChanged)

    def _read_slide_state(self, folder: str):
        try:
            state = slideshow.current_state()
        except Exception:
            log.exception("reading the Plasma wallpaper state failed")
            return
        ours = bool(state["folder"]) and Path(state["folder"]).resolve() == Path(folder).resolve()
        _safe_emit(self._slideSynced, state["plugin"] == slideshow.ID and ours)

    def _on_slide_synced(self, on: bool):
        if not self._slide_busy and on != bool(self._config.get("slideshow_enabled")):
            self._config.set("slideshow_enabled", on)
            self.slideshowChanged.emit()

    def _wallpaper_set(self, kind: str):
        _safe_emit(self._singleWallpaperSet, kind)

    def _on_single_wallpaper_set(self, kind: str):
        self._last_set_live = kind == "live"
        if self._config.get("slideshow_enabled"):
            self._config.set("slideshow_enabled", False)
            self.slideshowChanged.emit()

    def _apply_slideshow(self, on: bool, confirmed: bool = True):
        self._slide_gen += 1
        gen = self._slide_gen
        self._confirm_gen = None
        self._slide_busy = True
        self.slideshowChanged.emit()
        live_hint = self._last_set_live
        args = (
            Path(self.staticDir), self.slideshowMinutes, self.slideshowOrder,
            self.slideshowTransition, self.slideshowTransitionMs,
        )

        def work():
            try:
                if not on:
                    slideshow.disable_to_static()
                elif not confirmed and (live_hint or slideshow.current_state()["plugin"] == svwr.ID):
                    _safe_emit(self._slideNeedsConfirm, gen)
                    return
                else:
                    slideshow.enable(*args)
                error = ""
            except WallpaperError as e:
                error = str(e)
            except Exception as e:
                log.exception("slideshow change crashed")
                error = f"unexpected error ({type(e).__name__})"
            _safe_emit(self._slideApplied, gen, on, error)

        slideshow.EXECUTOR.submit(work)

    def _on_slide_needs_confirm(self, gen: int):
        if gen == self._slide_gen:
            self._confirm_gen = gen
            self.confirmSlideshowOverLive.emit()

    def _on_slide_applied(self, gen: int, on: bool, error: str):
        if gen != self._slide_gen:
            return
        self._slide_busy = False
        if error:
            log.warning("slideshow change failed: %s", error)
            self.slideshowFailed.emit(error)
        else:
            self._last_set_live = False
            if on != bool(self._config.get("slideshow_enabled")):
                self._config.set("slideshow_enabled", on)
        self.slideshowChanged.emit()

    @pyqtSlot()
    def confirmSlideshow(self):
        if self._confirm_gen is not None and self._confirm_gen == self._slide_gen:
            self._apply_slideshow(True)

    @pyqtSlot()
    def cancelSlideshow(self):
        self._confirm_gen = None
        self._slide_gen += 1
        self._slide_busy = False
        self.slideshowChanged.emit()

    def _get_slideshow(self) -> bool:
        return self._slide_available and bool(self._config.get("slideshow_enabled"))

    def _set_slideshow(self, value: bool):
        value = bool(value)
        if not self._slide_available or value == self._get_slideshow() or (value and self.slideshowFolderProblem):
            self.slideshowChanged.emit()
            return
        self._apply_slideshow(value, confirmed=False)

    slideshowEnabled = pyqtProperty(bool, _get_slideshow, _set_slideshow, notify=slideshowChanged)

    def _set_slide_option(self, prop: str, value):
        key, normalize = SLIDE_OPTIONS[prop]
        try:
            value = normalize(value)
        except (TypeError, ValueError):
            value = None
        if value is not None and value != self._config.get(key):
            self._config.set(key, value)
            if self.slideshowEnabled:
                self._apply_slideshow(True)
        self.slideshowChanged.emit()

    slideshowMinutes = pyqtProperty(
        int, lambda self: self._config.get("slideshow_minutes"),
        lambda self, v: self._set_slide_option("slideshowMinutes", v), notify=slideshowChanged,
    )
    slideshowOrder = pyqtProperty(
        str, lambda self: self._config.get("slideshow_order"),
        lambda self, v: self._set_slide_option("slideshowOrder", v), notify=slideshowChanged,
    )
    slideshowTransition = pyqtProperty(
        str, lambda self: self._config.get("slideshow_transition"),
        lambda self, v: self._set_slide_option("slideshowTransition", v), notify=slideshowChanged,
    )
    slideshowTransitionMs = pyqtProperty(
        int, lambda self: self._config.get("slideshow_transition_ms"),
        lambda self, v: self._set_slide_option("slideshowTransitionMs", v), notify=slideshowChanged,
    )

    @pyqtProperty(bool, notify=slideshowChanged)
    def slideshowBusy(self):
        return self._slide_busy

    @pyqtProperty(str, notify=dirsChanged)
    def slideshowFolderProblem(self):
        return slideshow.folder_problem(self.staticDir)

    @pyqtProperty(str, constant=True)
    def slideshowShaderDir(self):
        shaders = slideshow.BUNDLED / "contents" / "ui" / "shaders"
        return QUrl.fromLocalFile(str(shaders) + "/").toString() if shaders.is_dir() else ""

    @pyqtProperty(bool, constant=True)
    def slideshowAvailable(self):
        return self._slide_available

    @pyqtProperty(str, constant=True)
    def slideshowReason(self):
        return self._slide_reason

    @pyqtSlot()
    def clearCache(self):
        THUMB_EXECUTOR.submit(lambda: _safe_emit(self._cleared, clear_cache(cache_dir())))

    @pyqtProperty(bool, notify=togglesChanged)
    def firstRunDone(self):
        return bool(self._config.get("first_run_done"))

    @pyqtSlot()
    def runSetupAgain(self):
        self.setupRequested.emit()

    @pyqtSlot()
    def skipSetup(self):
        self._set_toggle("first_run_done", True)

    @pyqtSlot("QVariantMap")
    def finishSetup(self, choices: dict):
        for kind in ("static", "live"):
            if choices.get(kind + "Dir"):
                self.setDir(kind, str(choices[kind + "Dir"]))
        for prop in ("liveEnabled", "safeContent", "matchScreen", "skipDuplicates", "cacheSizeMb"):
            if prop in choices:
                setattr(self, prop, choices[prop])
        self.skipSetup()

    @pyqtProperty(list, notify=sourcesChanged)
    def sources(self):
        disabled = set(self._config.get("disabled_sources"))
        rows = [
            {"name": cls.name, "label": source_label(cls.name), "kind": cls.kind,
             "url": BUILTIN_URLS.get(cls.name, ""), "enabled": cls.name not in disabled, "builtin": True}
            for cls in BUILTINS
        ]
        rows += [
            {"name": c.get("name", ""), "label": c.get("name", ""), "kind": c.get("kind", ""),
             "url": c.get("search_url", ""), "enabled": c.get("name") not in disabled, "builtin": False}
            for c in self._config.get("custom_sources") if isinstance(c, dict)
        ]
        return rows

    @pyqtSlot(str, bool)
    def setSourceEnabled(self, name: str, enabled: bool):
        disabled = [n for n in self._config.get("disabled_sources") if n != name]
        if not enabled:
            disabled.append(name)
        self._config.set("disabled_sources", disabled)
        self.sourcesChanged.emit()

    def _errors(self, cfg: dict) -> list[str]:
        errors = validate_custom(cfg)
        if not errors and any(s["name"] == cfg["name"] for s in self.sources):
            errors = [f"name {cfg['name']!r} is already in use"]
        return errors

    @pyqtSlot("QVariantMap", result=list)
    def addCustomSource(self, cfg: dict) -> list:
        errors = self._errors(cfg)
        if errors:
            return errors
        self._config.set("custom_sources", self._config.get("custom_sources") + [cfg])
        self.sourcesChanged.emit()
        return []

    @pyqtSlot("QVariantMap", result="QVariantMap")
    def testCustomSource(self, cfg: dict) -> dict:
        errors = validate_custom(cfg)
        if errors:
            return {"errors": errors}
        self._test_gen += 1
        gen = self._test_gen

        def work():
            try:
                count, first = custom.test(cfg)
                result = {"ok": True, "count": count, "fields": _mapped_fields(first), "message": ""}
            except SourceError as e:
                result = {"ok": False, "count": 0, "fields": [], "message": str(e)}
            except Exception as e:
                log.exception("custom source test crashed")
                result = {"ok": False, "count": 0, "fields": [], "message": f"unexpected error ({type(e).__name__})"}
            _safe_emit(self._tested, gen, result)

        net.EXECUTOR.submit(work)
        return {}

    def _on_tested(self, gen: int, result: dict):
        if gen == self._test_gen:
            self.testResult.emit(result)

    @pyqtSlot(str)
    def removeCustomSource(self, name: str):
        kept = [c for c in self._config.get("custom_sources") if not (isinstance(c, dict) and c.get("name") == name)]
        self._config.set("custom_sources", kept)
        self.setSourceEnabled(name, True)


def _library_row(p: Path, kind: str, current: set[str]) -> dict:
    url = QUrl.fromLocalFile(str(p)).toString()
    return {
        "path": str(p),
        "url": url,
        "name": p.name,
        "isCurrent": str(p) in current,
        "fill": fill_url(url, local=True) if kind == "static" else "",
    }


def _scan_library(folder: Path, kind: str, current: set[str], compute: bool, hide: bool) -> tuple[list, list]:
    files = library.list_media(folder, kind)
    entries = []
    for p in files:
        fp = dupes.for_file(p, compute=compute)
        try:
            size = p.stat().st_size
        except OSError:
            size = 0
        pixels = fp.pixels if fp is not None and kind == "static" else 0
        entries.append((str(p), fp, (str(p) in current, pixels, size)))
    kept, extras = dupes.collapse(entries)
    shown = set(kept) if hide else {e[0] for e in entries}
    rows = [_library_row(p, kind, current) for p in files if str(p) in shown]
    copies = [{**_library_row(Path(x), kind, current), "keep": Path(k).name} for x, k in extras.items()]
    return rows, copies


class LibraryController(QObject):
    itemsChanged = pyqtSignal()
    busyChanged = pyqtSignal()
    wallpaperSet = pyqtSignal(str)
    failed = pyqtSignal(str)
    trashed = pyqtSignal(str, str)
    tidyProposed = pyqtSignal(list)
    tidyDone = pyqtSignal(int)
    tidyingChanged = pyqtSignal()
    duplicatesTrashed = pyqtSignal(int, list)
    _scanned = pyqtSignal(int, object, object)
    _applied = pyqtSignal(str, str)
    _restored = pyqtSignal(str)
    _framed = pyqtSignal()
    _proposed = pyqtSignal(int, str, list)
    _tidied = pyqtSignal(int, int, str)

    def __init__(self, config: Config, tags=None, parent=None):
        super().__init__(parent)
        self._config = config
        self._tags = tags
        self._tidying = False
        self._tidy_gen = 0
        self._proposal: dict[str, set[tuple[str, str]]] = {}
        self._items: dict[str, list[dict]] = {"static": [], "live": []}
        self._copies: dict[str, list[dict]] = {"static": [], "live": []}
        self._busy = False
        self._gen = 0
        self._in_trash: dict[str, str] = {}
        self._scanned.connect(self._on_scanned)
        self._applied.connect(self._on_applied)
        self._restored.connect(self._on_restored)
        self._proposed.connect(self._on_proposed)
        self._tidied.connect(self._on_tidied)
        self._regroup = QTimer(self)
        self._regroup.setSingleShot(True)
        self._regroup.setInterval(500)
        self._regroup.timeout.connect(self.refresh)
        self._framed.connect(self._regroup.start)

    @pyqtProperty(list, notify=itemsChanged)
    def staticItems(self):
        return self._items["static"]

    @pyqtProperty(list, notify=itemsChanged)
    def liveItems(self):
        return self._items["live"]

    @pyqtProperty(list, notify=itemsChanged)
    def staticDuplicates(self):
        return self._copies["static"]

    @pyqtProperty(list, notify=itemsChanged)
    def liveDuplicates(self):
        return self._copies["live"]

    @pyqtProperty(bool, notify=busyChanged)
    def busy(self):
        return self._busy

    @pyqtProperty(bool, notify=tidyingChanged)
    def tidying(self):
        return self._tidying

    def _set_tidying(self, tidying: bool):
        if tidying != self._tidying:
            self._tidying = tidying
            self.tidyingChanged.emit()

    def _folder(self, kind: str) -> Path:
        return Path(self._config.get(DIR_KEYS[kind])).expanduser()

    def _set_busy(self, busy: bool):
        if busy != self._busy:
            self._busy = busy
            self.busyChanged.emit()

    @pyqtSlot()
    def refresh(self):
        self._gen += 1
        gen = self._gen
        folders = {kind: self._folder(kind) for kind in DIR_KEYS}
        hide = bool(self._config.get("hide_duplicates"))
        self._set_busy(True)

        def work():
            # Show the folder from cached fingerprints first, then again once new images are hashed.
            rows, copies = {"static": [], "live": []}, {"static": [], "live": []}
            try:
                current = library.read_current()
                for compute in (False, True):
                    scans = {kind: _scan_library(f, kind, current, compute, hide) for kind, f in folders.items()}
                    rows = {kind: scan[0] for kind, scan in scans.items()}
                    copies = {kind: scan[1] for kind, scan in scans.items()}
                    if not compute:
                        _safe_emit(self._scanned, -gen, rows, copies)
            except Exception:
                log.exception("library scan failed")
            finally:
                _safe_emit(self._scanned, gen, rows, copies)

        net.EXECUTOR.submit(work)

    def _on_scanned(self, gen: int, rows: dict, copies: dict):
        if abs(gen) != self._gen:
            return
        if rows != self._items or copies != self._copies:
            self._items, self._copies = rows, copies
            self.itemsChanged.emit()
        if gen > 0:
            self._set_busy(False)

    @pyqtSlot(str, "QVariant")
    def frameGrabbed(self, path: str, image):
        if not isinstance(image, QImage) or image.isNull() or self._kind_of(path) != "live":
            return
        frame = image.copy()

        def work():
            buf = QBuffer()
            buf.open(QBuffer.OpenModeFlag.WriteOnly)
            frame.save(buf, "PNG")
            try:
                fp = dupes.fingerprint_bytes(bytes(buf.data()))
            except (OSError, ValueError):
                return
            known = dupes.for_file(Path(path), compute=False)
            dupes.remember_file(Path(path), fp)
            if fp != known:
                _safe_emit(self._framed)

        THUMB_EXECUTOR.submit(work)

    @pyqtSlot(list)
    def removeDuplicates(self, paths: list):
        allowed = {c["path"] for kind in DIR_KEYS for c in self._copies[kind]}
        moved = []
        for path in (str(p) for p in paths):
            if path not in allowed:
                continue
            ok, in_trash = QFile.moveToTrash(path)
            if not ok:
                self.failed.emit(f"Couldn't move {Path(path).name} to the Trash")
                continue
            if in_trash:
                self._in_trash[path] = in_trash
            moved.append(path)
        if moved:
            self.duplicatesTrashed.emit(len(moved), moved)
            self.refresh()

    @pyqtSlot(list)
    def undoRemoveDuplicates(self, paths: list):
        self._restore([str(p) for p in paths])

    def _kind_of(self, path: str) -> str | None:
        p = Path(path)
        for kind in DIR_KEYS:
            if p.parent == self._folder(kind) and any(i["path"] == path for i in self._items[kind]):
                return kind
        return None

    @pyqtSlot(str)
    def setWallpaper(self, path: str):
        kind = self._kind_of(path)
        if kind is None:
            return

        def work():
            try:
                (set_live if kind == "live" else set_static)(Path(path))
                error = ""
            except (WallpaperError, OSError) as e:
                error = str(e) or type(e).__name__
            _safe_emit(self._applied, path, error)

        net.EXECUTOR.submit(work)

    def _on_applied(self, path: str, error: str):
        name = Path(path).name
        if error:
            self.failed.emit(f"Couldn't set {name}: {error}")
            return
        self.wallpaperSet.emit(name)
        self.refresh()

    @pyqtSlot(str)
    def delete(self, path: str):
        kind = self._kind_of(path)
        if kind is None:
            return
        ok, in_trash = QFile.moveToTrash(path)
        name = Path(path).name
        if not ok:
            self.failed.emit(f"Couldn't move {name} to the Trash")
            return
        if in_trash:
            self._in_trash[path] = in_trash
        self._items[kind] = [i for i in self._items[kind] if i["path"] != path]
        self.itemsChanged.emit()
        self.trashed.emit(name, path)

    @pyqtSlot(str)
    def undoDelete(self, path: str):
        self._restore([path])

    def _restore(self, paths: list[str]):
        pairs = [(p, self._in_trash.pop(p)) for p in paths if p in self._in_trash]
        if not pairs:
            return

        def work():
            errors = []
            for path, in_trash in pairs:
                try:
                    library.restore_from_trash(Path(in_trash), Path(path))
                except OSError as e:
                    errors.append(f"Couldn't restore {Path(path).name}: {str(e) or type(e).__name__}")
            _safe_emit(self._restored, "; ".join(errors))

        net.EXECUTOR.submit(work)

    def _on_restored(self, error: str):
        if error:
            self.failed.emit(error)
        self.refresh()

    @pyqtSlot(str)
    def openFolder(self, kind: str):
        if kind not in DIR_KEYS:
            return
        folder = self._folder(kind)
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            self.failed.emit(f"Couldn't open {folder}: {e}")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    @pyqtSlot(str)
    def proposeTidy(self, kind: str):
        if kind not in DIR_KEYS:
            return
        self._tidy_gen += 1
        gen = self._tidy_gen
        folder = self._folder(kind)
        lookup = self._tags.tags if self._tags is not None else None
        self._set_tidying(True)

        def work():
            rows = []
            try:
                pairs = propose_renames(folder, kind, lookup, net.STOP)
                rows = [{"old": old.name, "new": new.name} for old, new in pairs]
            except Exception:
                log.exception("tidy proposal failed")
            _safe_emit(self._proposed, gen, kind, rows)

        net.EXECUTOR.submit(work)

    def _on_proposed(self, gen: int, kind: str, rows: list):
        if gen != self._tidy_gen:
            return
        self._proposal[kind] = {(r["old"], r["new"]) for r in rows}
        self._set_tidying(False)
        self.tidyProposed.emit(rows)

    @pyqtSlot(str, list)
    def applyTidy(self, kind: str, pairs: list):
        if kind not in DIR_KEYS:
            return
        proposal = self._proposal.pop(kind, set())
        folder = self._folder(kind)
        wanted = {(str(p.get("old", "")), str(p.get("new", ""))) for p in pairs if isinstance(p, dict)}
        chosen = [(folder / old, folder / new) for old, new in sorted(proposal & wanted)]
        self._tidy_gen += 1
        gen = self._tidy_gen
        self._set_tidying(True)

        def work():
            count, errors = 0, []
            try:
                current = library.read_current()
                done = apply_renames(chosen)
                count = len(done)
                for old, new in done:
                    if str(old) not in current:
                        continue
                    try:
                        (set_live if kind == "live" else set_static)(new)
                    except (WallpaperError, OSError) as e:
                        errors.append(f"Couldn't re-apply {new.name}: {e}")
            except Exception:
                log.exception("tidy rename failed")
                errors.append("Renaming failed, see the log for details")
            _safe_emit(self._tidied, gen, count, "; ".join(errors))

        net.EXECUTOR.submit(work)

    def _on_tidied(self, gen: int, count: int, error: str):
        if gen == self._tidy_gen:
            self._set_tidying(False)
        if error:
            self.failed.emit(error)
        self.tidyDone.emit(count)
        self.refresh()


METHOD_MODELS = {"esrgan": "realesrgan-x4plus", "anime": "realesrgan-x4plus-anime"}
METHOD_HINTS = {
    "lanczos": "Classic resampling. Fast, best for small changes.",
    "esrgan": "AI super-resolution ×4, then a Lanczos fit to the exact size. Keeps edges and texture sharp.",
    "anime": "AI model tuned for anime and illustrations, then a Lanczos fit to the exact size.",
}
AI_SCALE = 4
MAX_OUTPUT = 16384
VULKAN_ERRORS = ("vkCreateInstance failed", "invalid gpu device", "vkEnumeratePhysicalDevices")


def _dims(w: int, h: int) -> str:
    return f"{w} × {h}"


class _Cancelled(Exception):
    pass


class EditorController(QObject):
    changed = pyqtSignal()
    saved = pyqtSignal(str, bool)
    failed = pyqtSignal(str)
    downloadConfirm = pyqtSignal()
    _opened = pyqtSignal(int, str, int, int, str)
    _stepped = pyqtSignal(int, str, float)
    _aiReady = pyqtSignal(int, str)
    _finished = pyqtSignal(int, str, str, str, bool)
    _gpuProbed = pyqtSignal(bool, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._esrgan = upscale.RealEsrgan()
        self._source = ""
        self._src = (0, 0)
        self._ratio = "Original"
        self._crop = (0, 0, 0, 0)
        self._out = (0, 0)
        self._method = "lanczos"
        self._denoise = 0.3
        self._sharpen = 0.18
        self._running = False
        self._progress = 0.0
        self._stage = ""
        self._open_gen = 0
        self._gen = 0
        self._job: dict = {}
        self._cancel = threading.Event()
        self._pending: bool | None = None
        self._consented = False
        self._proc: QProcess | None = None
        self._ai_log = ""
        self._ai: bool | None = None
        self._ai_reason = ""
        self._opened.connect(self._on_opened)
        self._stepped.connect(self._on_step)
        self._aiReady.connect(self._on_ai_ready)
        self._finished.connect(self._on_finished)
        self._gpuProbed.connect(self._on_gpu)
        net.EXECUTOR.submit(self._probe_gpu)

    def _probe_gpu(self):
        index, reason = upscale.gpu_probe()
        _safe_emit(self._gpuProbed, index is not None, reason)

    def _on_gpu(self, discrete: bool, reason: str):
        self._ai = discrete
        self._ai_reason = reason
        if not discrete:
            self._method = "lanczos"
        self.changed.emit()

    @pyqtProperty(bool, notify=changed)
    def aiAvailable(self):
        return self._ai is True

    @pyqtProperty(str, notify=changed)
    def aiUnavailableReason(self):
        if self._ai is None:
            return "Checking for a dedicated GPU"
        return "" if self._ai else self._ai_reason

    @pyqtProperty(str, notify=changed)
    def source(self):
        return self._source

    @pyqtProperty(str, notify=changed)
    def sourceUrl(self):
        return QUrl.fromLocalFile(self._source).toString() if self._source else ""

    @pyqtProperty(str, notify=changed)
    def fileName(self):
        return Path(self._source).name if self._source else ""

    @pyqtProperty(int, notify=changed)
    def srcW(self):
        return self._src[0]

    @pyqtProperty(int, notify=changed)
    def srcH(self):
        return self._src[1]

    @pyqtProperty(str, notify=changed)
    def ratio(self):
        return self._ratio

    @pyqtProperty("QVariantMap", notify=changed)
    def cropRect(self):
        x, y, w, h = self._crop
        return {"x": x, "y": y, "w": w, "h": h}

    @pyqtProperty(int, notify=changed)
    def outW(self):
        return self._out[0]

    @pyqtProperty(int, notify=changed)
    def outH(self):
        return self._out[1]

    @pyqtProperty(str, notify=changed)
    def method(self):
        return self._method

    @pyqtProperty(str, notify=changed)
    def hint(self):
        return METHOD_HINTS[self._method]

    def _set_amount(self, name: str, value: float):
        value = max(0.0, min(1.0, float(value)))
        if getattr(self, name) != value:
            setattr(self, name, value)
            self.changed.emit()

    denoise = pyqtProperty(float, lambda self: self._denoise,
                           lambda self, v: self._set_amount("_denoise", v), notify=changed)
    sharpen = pyqtProperty(float, lambda self: self._sharpen,
                           lambda self, v: self._set_amount("_sharpen", v), notify=changed)

    @pyqtProperty("QVariantMap", notify=changed)
    def summary(self):
        _, _, cw, ch = self._crop
        ow, oh = self._out
        scale = max(ow / cw, oh / ch) if cw and ch else 0
        note = upscale.plan_upscale(cw, ch, ow, oh)[1] if cw and ch else ""
        return {
            "source": _dims(*self._src),
            "crop": _dims(cw, ch),
            "output": _dims(ow, oh),
            "scale": f"×{scale:.2f}",
            "note": note if self._method in METHOD_MODELS else "",
        }

    @pyqtProperty(bool, notify=changed)
    def running(self):
        return self._running

    @pyqtProperty(float, notify=changed)
    def progress(self):
        return self._progress

    @pyqtProperty(str, notify=changed)
    def stage(self):
        return self._stage

    @pyqtSlot(str)
    def open(self, path: str):
        self.cancel()
        self._open_gen += 1
        gen = self._open_gen

        def work():
            try:
                with Image.open(path) as im:
                    w, h = im.size
                error = ""
            except Exception as e:
                w, h, error = 0, 0, str(e) or type(e).__name__
            _safe_emit(self._opened, gen, path, w, h, error)

        net.EXECUTOR.submit(work)

    def _on_opened(self, gen: int, path: str, w: int, h: int, error: str):
        if gen != self._open_gen:
            return
        if error:
            self.failed.emit(f"Couldn't open {Path(path).name}: {error}")
            return
        self._source = path
        self._src = (w, h)
        self._ratio = "Original"
        self._crop = (0, 0, w, h)
        self._out = (w, h)
        self._stage = ""
        self._progress = 0.0
        self.changed.emit()

    @pyqtSlot(str)
    def setRatio(self, ratio: str):
        if not self._src[0]:
            return
        try:
            self._crop = upscale.crop_rect(*self._src, ratio)
        except ValueError:
            return
        self._ratio = ratio
        self.changed.emit()

    @pyqtSlot(int, int, int, int)
    def setCrop(self, x: int, y: int, w: int, h: int):
        sw, sh = self._src
        if not sw:
            return
        w, h = max(1, min(w, sw)), max(1, min(h, sh))
        x, y = max(0, min(x, sw - w)), max(0, min(y, sh - h))
        if (x, y, w, h) != self._crop:
            self._crop = (x, y, w, h)
            self.changed.emit()

    @pyqtSlot(int, int)
    def setOutput(self, w: int, h: int):
        out = (max(1, min(w, MAX_OUTPUT)), max(1, min(h, MAX_OUTPUT)))
        if out != self._out:
            self._out = out
            self.changed.emit()

    @pyqtSlot(str)
    def setMethod(self, method: str):
        if method in METHOD_MODELS and not self.aiAvailable:
            return
        if method in METHOD_HINTS and method != self._method:
            self._method = method
            self.changed.emit()

    def _plan_ai(self) -> tuple[str | None, str]:
        model = METHOD_MODELS.get(self._method) if self.aiAvailable else None
        _, _, cw, ch = self._crop
        if model is None or upscale.plan_upscale(cw, ch, *self._out)[0] is None:
            return None, ""
        if upscale.ai_input_size(cw, ch, *self._out) is None:
            limit = upscale.MAX_AI_PIXELS // 1_000_000
            return None, f"Real-ESRGAN skipped: the result would be too large (over {limit} MP). Used Lanczos instead"
        return model, ""

    @pyqtSlot(bool)
    def apply(self, setAfter: bool):
        if self._running or not self._source:
            return
        if self._method in METHOD_MODELS and not self.aiAvailable:
            self._method = "lanczos"
            self.changed.emit()
        model, note = self._plan_ai()
        if model and not self._consented and not self._esrgan.available():
            self._pending = setAfter
            self.downloadConfirm.emit()
            return
        self._start(setAfter, model, note)

    @pyqtSlot(bool)
    def confirmDownload(self, ok: bool):
        pending, self._pending = self._pending, None
        if pending is None or not ok:
            return
        self._consented = True
        self._start(pending, *self._plan_ai())

    def _start(self, set_after: bool, model: str | None, note: str):
        self._gen += 1
        self._cancel = threading.Event()
        self._job = {
            "src": Path(self._source), "crop": self._crop, "out": self._out, "model": model,
            "denoise": self._denoise, "sharpen": self._sharpen, "set_after": set_after,
        }
        self._running = True
        self._progress = 0.0
        self._stage = "Preparing"
        self.changed.emit()
        if model:
            net.EXECUTOR.submit(self._prepare, self._gen, self._job, self._cancel)
        else:
            net.EXECUTOR.submit(self._render, self._gen, self._job, self._cancel, None, note)

    def _step(self, gen: int, cancel: threading.Event, stage: str, progress: float):
        if cancel.is_set():
            raise _Cancelled()
        _safe_emit(self._stepped, gen, stage, progress)

    def _on_step(self, gen: int, stage: str, progress: float):
        if gen == self._gen and self._running:
            self._stage = stage
            self._progress = progress
            self.changed.emit()

    @staticmethod
    def _box(job: dict) -> tuple[int, int, int, int]:
        x, y, w, h = job["crop"]
        return x, y, x + w, y + h

    def _prepare(self, gen: int, job: dict, cancel: threading.Event):
        def report(done: int, total: int):
            pct = done / total if total else 0
            self._step(gen, cancel, f"Downloading Real-ESRGAN {round(pct * 100)}%", 0.05 + 0.2 * pct)

        work = None
        try:
            if not self._esrgan.available():
                self._esrgan.ensure(report)
            self._esrgan.verify()
            self._step(gen, cancel, "Cropping", 0.28)
            base = Path(paths.CACHE_DIR) / "upscale"
            base.mkdir(parents=True, exist_ok=True)
            work = Path(tempfile.mkdtemp(prefix="job-", dir=base))
            with Image.open(job["src"]) as im:
                img = im.crop(self._box(job)).convert("RGB")
            # Shrink only when the ×4 result of the full crop would exceed the pixel cap.
            size = upscale.ai_input_size(*img.size, *job["out"])
            if size and size != img.size:
                img = img.resize(size, Image.Resampling.LANCZOS)
            img.save(work / "in.png")
            _safe_emit(self._aiReady, gen, str(work))
            return
        except _Cancelled:
            if work:
                shutil.rmtree(work, ignore_errors=True)
            return
        except (upscale.UpscaleError, OSError, requests.RequestException) as e:
            log.warning("Real-ESRGAN unavailable: %s", e)
            note = f"Real-ESRGAN unavailable ({e}). Used Lanczos instead"
        except Exception as e:
            log.exception("Real-ESRGAN preparation crashed")
            note = f"Real-ESRGAN unavailable ({type(e).__name__}). Used Lanczos instead"
        if work:
            shutil.rmtree(work, ignore_errors=True)
        self._render(gen, job, cancel, None, note)

    def _on_ai_ready(self, gen: int, work: str):
        if gen != self._gen:
            shutil.rmtree(work, ignore_errors=True)
            return
        self._job["work"] = work
        self._ai_log = ""
        try:
            argv = self._esrgan.command(str(Path(work) / "in.png"), str(Path(work) / "out.png"),
                                        AI_SCALE, self._job["model"])
        except upscale.UpscaleError as e:
            net.EXECUTOR.submit(self._render, gen, self._job, self._cancel, None, f"{e}. Used Lanczos instead")
            return
        proc = QProcess(self)
        proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        proc.readyReadStandardOutput.connect(lambda: self._on_ai_output(proc))
        proc.finished.connect(lambda code, status: self._on_ai_finished(proc, code, status))
        proc.errorOccurred.connect(lambda err: self._on_ai_error(proc, err))
        self._proc = proc
        self._stage = f"Real-ESRGAN ×{AI_SCALE}"
        self._progress = 0.3
        self.changed.emit()
        proc.start(argv[0], argv[1:])

    def _on_ai_output(self, proc: QProcess):
        text = bytes(proc.readAllStandardOutput()).decode(errors="replace")
        if proc is not self._proc:
            return
        self._ai_log = (self._ai_log + text)[-4000:]
        pct = upscale.parse_progress(text)
        if pct is not None:
            self._stage = f"Real-ESRGAN ×{AI_SCALE} · {round(pct * 100)}%"
            self._progress = 0.3 + 0.55 * pct
            self.changed.emit()

    def _on_ai_error(self, proc: QProcess, err):
        if err == QProcess.ProcessError.FailedToStart and proc is self._proc:
            self._ai_done(proc, False)

    def _on_ai_finished(self, proc: QProcess, code: int, status):
        if proc is self._proc:
            self._ai_done(proc, status == QProcess.ExitStatus.NormalExit and code == 0)

    def _ai_done(self, proc: QProcess, ok: bool):
        self._proc = None
        proc.deleteLater()
        out = Path(self._job["work"]) / "out.png"
        if ok and out.is_file():
            net.EXECUTOR.submit(self._render, self._gen, self._job, self._cancel, out, "")
            return
        reason = "Vulkan is unavailable" if any(e in self._ai_log for e in VULKAN_ERRORS) else "the run failed"
        log.warning("Real-ESRGAN failed (%s): %s", reason, self._ai_log.strip()[-500:])
        net.EXECUTOR.submit(self._render, self._gen, self._job, self._cancel, None,
                            f"Real-ESRGAN failed ({reason}). Used Lanczos instead")

    def _render(self, gen: int, job: dict, cancel: threading.Event, ai_out: Path | None, note: str):
        out_w, out_h = job["out"]
        path, error, was_set = "", "", False
        try:
            if ai_out is not None:
                self._step(gen, cancel, "Reading Real-ESRGAN output", 0.86)
                # Our own ×4 output may pass Pillow's decompression-bomb warning size.
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", Image.DecompressionBombWarning)
                    img = Image.open(ai_out)
                    img.load()
                img = img.convert("RGB")
            else:
                self._step(gen, cancel, "Cropping", 0.1)
                with Image.open(job["src"]) as im:
                    img = im.crop(self._box(job)).convert("RGB")
                if job["denoise"] > 0:
                    self._step(gen, cancel, "Denoising", 0.3)
                    img = upscale.denoise(img, job["denoise"])
            self._step(gen, cancel, f"Lanczos fit to {_dims(out_w, out_h)}", 0.9)
            img = upscale.sharpen(upscale.lanczos(img, out_w, out_h), job["sharpen"])
            self._step(gen, cancel, "Saving PNG", 0.95)
            fd, tmp = tempfile.mkstemp(prefix=".", suffix=".png.part", dir=job["src"].parent)
            os.close(fd)
            part = Path(tmp)
            try:
                with contextlib.suppress(OSError):
                    # CIFS and similar mounts may refuse; the save must still go through.
                    os.chmod(part, 0o666 & ~_UMASK)
                img.save(part, "PNG")
            except BaseException:
                part.unlink(missing_ok=True)
                raise
            dest = upscale.publish(part, job["src"], out_w, out_h)
            path = str(dest)
            if job["set_after"]:
                try:
                    set_static(dest)
                    was_set = True
                except WallpaperError as e:
                    error = f"Saved, but couldn't set it as wallpaper: {e}"
        except _Cancelled:
            return
        except OSError as e:
            error = str(e) or type(e).__name__
        except Exception as e:
            log.exception("upscale render crashed")
            error = f"unexpected error ({type(e).__name__})"
        finally:
            if job.get("work"):
                shutil.rmtree(job["work"], ignore_errors=True)
        _safe_emit(self._finished, gen, path, note, error, was_set)

    def _on_finished(self, gen: int, path: str, note: str, error: str, was_set: bool):
        if gen != self._gen:
            return
        self._running = False
        self._job = {}
        if path:
            self._progress = 1.0
            self._stage = f"Saved {Path(path).name}" + (f". {note}" if note else "")
        else:
            self._progress = 0.0
            self._stage = f"Failed: {error}"
        self.changed.emit()
        if path:
            self.saved.emit(path, was_set)
        if error:
            self.failed.emit(error)

    @pyqtSlot()
    def cancel(self):
        self._pending = None
        if not self._running:
            return
        self._gen += 1
        self._cancel.set()
        proc, self._proc = self._proc, None
        if proc is not None and proc.state() != QProcess.ProcessState.NotRunning:
            proc.kill()
            proc.waitForFinished(QUIT_WAIT_MS)
        if proc is not None:
            proc.deleteLater()
        if self._job.get("work"):
            shutil.rmtree(self._job["work"], ignore_errors=True)
        self._job = {}
        self._running = False
        self._progress = 0.0
        self._stage = "Cancelled"
        self.changed.emit()
