import re
import threading
import time
from urllib.parse import urljoin

import requests

from .. import net
from ..naming import clean_title
from ._html import parse_size
from .base import Filters, Item, Source, SourceError

BASE = "https://livelywallpaper.app/live-wallpapers/"
CATALOG = "https://livelywallpaper.app/data/wallpaper-cards.json"
CDN = "https://cdn.livelywallpaper.app/wallpapers/"
NAME = "lively"
PER_PAGE = 36
TTL = 3600
CATEGORIES = (
    ("anime", "Anime"),
    ("games", "Games"),
    ("nature", "Nature"),
    ("art-fantasy", "Art & Fantasy"),
    ("cars", "Cars"),
    ("space", "Space"),
)
_LABELS = dict(CATEGORIES)

_lock = threading.Lock()
_cache: tuple[float, list[dict]] = (0.0, [])


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[-_]+", " ", text.lower())).strip()


def _num(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _catalog() -> list[dict]:
    global _cache
    with _lock:
        if _cache[1] and time.monotonic() - _cache[0] < TTL:
            return _cache[1]
        try:
            r = net.SESSION.get(CATALOG, timeout=net.TIMEOUT)
            r.raise_for_status()
            cards = r.json().get("wallpapers")
        except (requests.RequestException, ValueError, AttributeError) as e:
            raise SourceError(f"Lively request failed: {e}") from e
        if not isinstance(cards, list):
            raise SourceError("Lively catalog format changed")
        _cache = (time.monotonic(), [c for c in cards if isinstance(c, dict) and c.get("slug")])
        return _cache[1]


def to_item(card: dict) -> Item:
    slug = str(card["slug"])
    cdn = f"{CDN}{slug}/"
    tags = [
        str(t).lower()
        for key in ("categories", "tags")
        if isinstance(card.get(key), list)
        for t in card[key]
    ]
    return Item(
        source=NAME,
        kind="live",
        title=clean_title(str(card.get("title") or slug.replace("-", " "))),
        thumb_url=str(card.get("cover_url") or ""),
        page_url=urljoin(BASE, f"{slug}/"),
        download_url=str(card.get("download_url") or cdn + "download.mp4"),
        width=int(_num(card.get("width"))),
        height=int(_num(card.get("height"))),
        tags=list(dict.fromkeys(tags)),
        file_size=parse_size(str(card.get("size") or "")),
        file_type="video/mp4",
        duration=_num(card.get("duration")),
        extra={"preview_video": str(card.get("preview_url") or cdn + "preview.mp4")},
    )


class LivelySource(Source):
    name = NAME
    kind = "live"
    server_filters = frozenset({"query", "category"})
    sizes = "listed"
    categories = CATEGORIES

    def search(self, page: int, f: Filters) -> list[Item]:
        cards = _catalog()
        label = _LABELS.get(f.category)
        if label:
            cards = [
                c
                for c in cards
                if isinstance(c.get("categories"), list) and f.category in c["categories"]
            ]
        words = _norm(f.query).split()
        if words:
            cards = [
                c
                for c in cards
                if all(w in _norm(str(c.get("search") or c.get("title") or "")) for w in words)
            ]
        start = (page - 1) * PER_PAGE
        items = [to_item(c) for c in cards[start : start + PER_PAGE]]
        if label:
            for item in items:
                if label.lower() not in item.tags:
                    item.tags.append(label.lower())
        return items

    def resolve_download(self, item: Item) -> str:
        slug = item.page_url.rstrip("/").rsplit("/", 1)[-1]
        return item.download_url or f"{CDN}{slug}/download.mp4"
