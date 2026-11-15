import re
from dataclasses import replace
from functools import lru_cache
from urllib.parse import quote, urljoin

from bs4 import BeautifulSoup

from ..naming import clean_title
from ._html import fetch_html
from .base import Filters, Item, Source, SourceError

BASE = "https://wallpapercave.com"
NAME = "wallpapercave"
LABEL = "WallpaperCave"
PER_PAGE = 30
MIN_WIDTH = 1920
MAX_TITLE = 48
CATEGORIES = (
    ("abstract", "Abstract"),
    ("aircraft", "Aircraft"),
    ("animals", "Animals"),
    ("anime", "Anime"),
    ("cars", "Cars"),
    ("design", "Design"),
    ("fantasy", "Fantasy"),
    ("games", "Games"),
    ("holidays", "Holidays"),
    ("landscapes", "Landscapes"),
    ("motorcycles", "Motorcycles"),
    ("movies", "Movies"),
    ("music", "Music"),
    ("nature", "Nature"),
    ("places", "Places"),
    ("science", "Science"),
    ("space", "Space"),
    ("sports", "Sports"),
    ("technology", "Technology"),
    ("tv-shows", "TV Shows"),
)
_LABELS = dict(CATEGORIES)
_PATHS = {
    "aircraft": "vehicles/aircraft",
    "animals": "nature/animals",
    "anime": "anime-manga",
    "cars": "vehicles/cars",
    "landscapes": "nature/landscapes",
    "motorcycles": "vehicles/motorcycles",
    "space": "universe",
}
SKIP_ALBUMS = re.compile(r"(?:^|-)(?:phone|iphone|mobile|vertical|calendar)(?:-|$)")


def _int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0



def _title(alt: str, album: str) -> str:
    # Uploaders often paste news headlines as alt text; the album name reads better then.
    title = clean_title(alt)
    return title if title and len(title) <= MAX_TITLE else album or title


def parse_albums(html: str, by_size: bool = False) -> list[str]:
    links = BeautifulSoup(html, "html.parser").select("a.albumthumbnail[href], a.falbumthumbnail[href]")
    if by_size:
        # Category pages list albums alphabetically; biggest first surfaces the popular ones.
        links.sort(key=lambda a: -_int(a.get("title", "").partition(" ")[0]))
    urls = []
    for a in links:
        url = urljoin(BASE, a["href"])
        if url.startswith(BASE + "/") and url not in urls and not SKIP_ALBUMS.search(url.rsplit("/", 1)[-1]):
            urls.append(url)
    return urls


def parse_album(html: str) -> list[Item]:
    soup = BeautifulSoup(html, "html.parser")
    h1 = soup.select_one("#albuminfo h1") or soup.select_one("h1")
    album = clean_title(h1.get_text(" ", strip=True) if h1 else "")
    tags = [album.lower()] if album else []
    items = []
    for el in soup.select("div.wallpaper[id]"):
        img = el.select_one("img.wimg[src]")
        src = img["src"] if img else ""
        if not src.startswith("/wp/"):
            continue
        width, height = _int(img.get("width")), _int(img.get("height"))
        # Albums mix phone and low-res uploads; this is a desktop app.
        if width < MIN_WIDTH or width <= height:
            continue
        file = src.removeprefix("/wp/")
        items.append(
            Item(
                source=NAME,
                kind="static",
                title=_title(img.get("alt", ""), album),
                thumb_url=f"{BASE}/dwp1x/{file}",
                page_url=f"{BASE}/w/{el['id']}",
                download_url=f"{BASE}/wp/{file}",
                width=width,
                height=height,
                tags=list(tags),
                file_type=file.rpartition(".")[2].lower(),
            )
        )
    return items


@lru_cache(maxsize=128)
def _album(url: str) -> tuple[Item, ...]:
    return tuple(parse_album(fetch_html(LABEL, url)))


class WallpaperCaveSource(Source):
    name = NAME
    kind = "static"
    server_filters = frozenset({"query", "category"})
    sizes = "listed"
    categories = CATEGORIES

    def server_keys(self, f: Filters) -> frozenset[str]:
        if f.category in _LABELS:
            return self.server_filters - {"query"}
        return self.server_filters

    def search(self, page: int, f: Filters) -> list[Item]:
        query = f.query.strip()
        category = f.category if f.category in _LABELS else ""
        if category:
            url = f"{BASE}/categories/{_PATHS.get(category, category)}"
        else:
            url = f"{BASE}/search?q={quote(query)}" if query else f"{BASE}/top"
        albums = parse_albums(fetch_html(LABEL, url), by_size=bool(category))
        want = page * PER_PAGE
        items, seen = [], set()
        for album in albums:
            if len(items) >= want:
                break
            for item in _album(album):
                if item.page_url not in seen:
                    seen.add(item.page_url)
                    items.append(item)
        extra = [_LABELS[category].lower()] if category else []
        return [
            replace(i, tags=list(dict.fromkeys(i.tags + extra))) for i in items[want - PER_PAGE : want]
        ]

    def resolve_download(self, item: Item) -> str:
        if not item.download_url:
            raise SourceError(f"{LABEL} download link not found")
        return item.download_url
