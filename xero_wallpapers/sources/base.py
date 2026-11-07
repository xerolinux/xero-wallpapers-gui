import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Literal

_SCREEN = re.compile(r"(\d+)x(\d+)")


class SourceError(Exception):
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
    # "any", "1440p", "4k", "8k", or "<W>x<H>" for an exact screen size.
    min_res: str = "any"
    # "any", "W:H" or "ultrawide".
    ratio: str = "any"


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

    @abstractmethod
    def search(self, page: int, f: Filters) -> list[Item]: ...

    @abstractmethod
    def resolve_download(self, item: Item) -> str: ...

    def details(self, item: Item) -> Item:
        return item
