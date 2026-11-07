import colorsys
import threading
from dataclasses import replace

import requests

from .. import net, paths
from ..naming import title_from_tags
from ..tags import RateLimiter, TagCache, TagFetcher
from .base import Filters, Item, Source, SourceError, screen_size

API = "https://wallhaven.cc/api/v1"

_CHROMATIC = (
    "660000 990000 cc0000 cc3333 ea4c88 993399 663399 333399 0066cc 0099cc "
    "66cccc 77cc33 669900 336600 666600 999900 cccc33 ffff00 ffcc33 ff9900 "
    "ff6600 cc6633 996633 663300"
).split()


def _hsv(hexcode: str) -> tuple[float, float, float]:
    r, g, b = (int(hexcode[i:i + 2], 16) / 255 for i in (0, 2, 4))
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    return h * 360, s, v


_HSV = {code: _hsv(code) for code in _CHROMATIC}

_SORT = {"newest": "date_added"}
_MIN_RES = {"1440p": "2560x1440", "4k": "3840x2160", "8k": "7680x4320"}
def nearest_color(hue: int) -> str:
    def rank(code: str) -> tuple[float, float]:
        h, s, v = _HSV[code]
        d = abs(h - hue % 360)
        return round(min(d, 360 - d)), -s * v

    return min(_CHROMATIC, key=rank)


def _get(url: str, **kwargs) -> dict:
    try:
        r = net.SESSION.get(url, timeout=net.TIMEOUT, **kwargs)
        r.raise_for_status()
        payload = r.json()
    except (requests.RequestException, ValueError) as e:
        raise SourceError(f"Wallhaven request failed: {e}") from e
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), (list, dict)):
        raise SourceError("Wallhaven returned an unexpected response")
    return payload


def _detail(wid: str) -> tuple[list[str], str]:
    data = _get(f"{API}/w/{wid}")["data"]
    if not isinstance(data, dict):
        raise SourceError("Wallhaven returned an unexpected response")
    try:
        tags = [t["name"] for t in data.get("tags") or []]
        author = (data.get("uploader") or {}).get("username", "")
    except (KeyError, TypeError, AttributeError) as e:
        raise SourceError(f"Wallhaven response could not be parsed: {e}") from e
    return tags, author


_FETCHERS: dict = {}
_FETCHERS_LOCK = threading.Lock()


def tag_fetcher() -> TagFetcher:
    cache_dir = paths.CACHE_DIR
    with _FETCHERS_LOCK:
        fetcher = _FETCHERS.get(cache_dir)
        if fetcher is None:
            fetcher = _FETCHERS[cache_dir] = TagFetcher(
                _detail,
                TagCache(cache_dir / "wallhaven-tags.json"),
                RateLimiter(state=cache_dir / "wallhaven-rate.json", stop=net.STOP),
            )
        return fetcher


def _int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


class WallhavenSource(Source):
    name = "wallhaven"
    kind = "static"
    server_filters = frozenset({"query", "sort", "min_res", "ratio", "hue"})

    def __init__(self, safe: bool = True):
        self.safe = safe

    def params(self, page: int, f: Filters) -> dict:
        query = " ".join(p for p in [f.query.strip(), *f.tags] if p)
        params = {
            "purity": "100" if self.safe else "110",
            "sorting": _SORT.get(f.sort, "toplist"),
            "page": page,
        }
        if query:
            params["q"] = query
        screen = screen_size(f.min_res)
        if screen:
            params["resolutions"] = f"{screen[0]}x{screen[1]}"
        elif f.min_res in _MIN_RES:
            params["atleast"] = _MIN_RES[f.min_res]
        if f.ratio == "ultrawide":
            params["ratios"] = "21x9,32x9"
        elif f.ratio != "any":
            params["ratios"] = f.ratio.replace(":", "x")
        if f.hue is not None:
            params["colors"] = nearest_color(f.hue)
        return params

    def search(self, page: int, f: Filters) -> list[Item]:
        payload = _get(f"{API}/search", params=self.params(page, f))
        data = payload["data"]
        if not isinstance(data, list):
            raise SourceError("Wallhaven returned an unexpected response")
        try:
            return [self._parse(raw) for raw in data]
        except (KeyError, TypeError, AttributeError) as e:
            raise SourceError(f"Wallhaven response could not be parsed: {e}") from e

    def _parse(self, raw: dict) -> Item:
        return Item(
            source=self.name,
            kind="static",
            title="",
            # "original" keeps the full frame; "small" and "large" are centre crops.
            thumb_url=raw["thumbs"].get("original") or raw["thumbs"]["small"],
            page_url=raw["url"],
            download_url=raw["path"],
            width=_int(raw.get("dimension_x")),
            height=_int(raw.get("dimension_y")),
            colors=list(raw.get("colors") or []),
            file_size=_int(raw.get("file_size")),
            file_type=raw.get("file_type", ""),
            views=_int(raw.get("views")),
            favorites=_int(raw.get("favorites")),
            uploaded=raw.get("created_at", ""),
            extra={"id": raw["id"]},
        )

    def resolve_download(self, item: Item) -> str:
        return item.download_url

    def details(self, item: Item) -> Item:
        tags, author = tag_fetcher().detail(item.extra["id"])
        return replace(item, tags=tags, author=author, title=title_from_tags(tags) or item.title)
