import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Literal

_SCREEN = re.compile(r"(\d+)x(\d+)")
# Width / height at or above this counts as ultra-wide (21:9 is 2.33, 32:9 is 3.56).
ULTRAWIDE_RATIO = 2.3
# Resolution tiers in ascending order: each runs from its size up to (not including) the next one; 4K is open-ended.
RES_TIERS = {"1080p": (1920, 1080), "1440p": (2560, 1440), "4k": (3840, 2160)}


def in_tier(width: int, height: int, tier: str) -> bool:
    sizes = list(RES_TIERS.values())
    i = list(RES_TIERS).index(tier)
    low_w, low_h = sizes[i]
    if width < low_w or height < low_h:
        return False
    return i + 1 == len(sizes) or not (width >= sizes[i + 1][0] and height >= sizes[i + 1][1])


class SourceError(Exception):
    pass


class PageNotFound(SourceError):
    # Sites (WordPress especially) answer a page past the last one with 404 instead of an empty page.
    pass


@dataclass
class Item:
    source: str
    kind: Literal["static", "live"]
    title: str
    thumb_url: str
    page_url: str
    download_url: str = ""
    width: int = 0
    height: int = 0
    tags: list[str] = field(default_factory=list)
    colors: list[str] = field(default_factory=list)
    author: str = ""
    file_size: int = 0
    file_type: str = ""
    views: int = 0
    favorites: int = 0
    uploaded: str = ""
    duration: float = 0
    fps: float = 0
    codec: str = ""
    extra: dict = field(default_factory=dict)

    def resolution(self) -> str:
        if self.width and self.height:
            return f"{self.width} × {self.height}"
        return ""


@dataclass
class Filters:
    query: str = ""
    sort: Literal["popular", "newest", "res_desc", "res_asc", "size"] = "popular"
    tags: list[str] = field(default_factory=list)
    hue: int | None = None
    # "any", a RES_TIERS key, or "<W>x<H>" for wallpapers that fit that screen.
    min_res: str = "any"
    # "any", "W:H" or "ultrawide".
    ratio: str = "any"
    # A slug from the source's categories; "" browses everything.
    category: str = ""


def screen_size(min_res: str) -> tuple[int, int] | None:
    m = _SCREEN.fullmatch(min_res)
    if not m or not int(m[1]) or not int(m[2]):
        return None
    return int(m[1]), int(m[2])


class Source(ABC):
    name: str
    kind: str
    server_filters: frozenset[str] = frozenset()
    # Where item sizes come from: "listed" (search results), "details" (detail pages) or "none".
    sizes: Literal["listed", "details", "none"] = "listed"
    # Detail pages carry the site's tags; No anime checks them before showing an item.
    tags_in_details: bool = False
    # (slug, label) pairs the site can be browsed by; empty when it only has tags.
    categories: tuple[tuple[str, str], ...] = ()

    def server_keys(self, f: Filters) -> frozenset[str]:
        return self.server_filters

    @abstractmethod
    def search(self, page: int, f: Filters) -> list[Item]: ...

    @abstractmethod
    def resolve_download(self, item: Item) -> str: ...

    def details(self, item: Item) -> Item:
        return item
