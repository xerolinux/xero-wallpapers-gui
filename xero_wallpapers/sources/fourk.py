import re
from dataclasses import replace
from urllib.parse import quote, urljoin

from bs4 import BeautifulSoup

from ..naming import clean_title
from ._html import fetch_html, parse_resolution
from .base import RES_TIERS, Filters, Item, Source, SourceError

BASE = "https://4kwallpapers.com"
NAME = "4kwallpapers"
CATEGORIES = (
    ("abstract", "Abstract"),
    ("animals", "Animals"),
    ("anime", "Anime"),
    ("architecture", "Architecture"),
    ("bikes", "Bikes"),
    ("cars", "Cars"),
    ("cgi", "CGI"),
    ("dark", "Dark"),
    ("fantasy", "Fantasy"),
    ("flowers", "Flowers"),
    ("games", "Games"),
    ("minimal", "Minimal"),
    ("movies", "Movies"),
    ("music", "Music"),
    ("nature", "Nature"),
    ("photography", "Photography"),
    ("sci-fi", "Sci-Fi"),
    ("space", "Space"),
    ("sports", "Sports"),
    ("technology", "Technology"),
    ("world", "World"),
)
_LABELS = dict(CATEGORIES)
_PATHS = {"cgi": "graphics-cgi", "dark": "black-dark"}


def parse_list(html: str) -> list[Item]:
    items = []
    for el in BeautifulSoup(html, "html.parser").select("p.wallpapers__item"):
        link = el.select_one("a.wallpapers__canvas_image")
        img = el.select_one("img[itemprop='thumbnail']")
        if not link or not img or not link.get("href"):
            continue
        items.append(
            Item(
                source=NAME,
                kind="static",
                title=clean_title(img.get("alt") or link.get("title") or ""),
                thumb_url=urljoin(BASE, img.get("src", "")),
                page_url=urljoin(BASE, link["href"]),
            )
        )
    return items


def parse_detail(html: str, item: Item) -> Item:
    best, best_pixels, best_size = "", 0, (0, 0)
    for a in BeautifulSoup(html, "html.parser").select("a[href*='/images/wallpapers/']"):
        href = urljoin(BASE, a["href"])
        w, h = parse_resolution(href)
        if w * h > best_pixels:
            best, best_pixels, best_size = href, w * h, (w, h)
    if not best:
        return item
    return replace(item, download_url=best, width=best_size[0], height=best_size[1])


# The site renders every wallpaper at this ultra-wide size and at each RES_TIERS size too.
ULTRAWIDE = (5120, 2160)
_PAGE_ID = re.compile(r"/([a-z0-9-]+)-(\d+)\.html$")


def variant(item: Item, w: int, h: int) -> Item | None:
    m = _PAGE_ID.search(item.page_url)
    if not m:
        return None
    url = f"{BASE}/images/wallpapers/{m[1]}-{w}x{h}-{m[2]}.jpg"
    return replace(item, download_url=url, width=w, height=h, extra={**item.extra, "variant": True})


class FourKSource(Source):
    name = NAME
    kind = "static"
    server_filters = frozenset({"query", "category", "ratio", "min_res"})
    sizes = "details"
    categories = CATEGORIES

    def server_keys(self, f: Filters) -> frozenset[str]:
        if f.category in _LABELS:
            return self.server_filters - {"query"}
        return self.server_filters

    def search(self, page: int, f: Filters) -> list[Item]:
        items = self._search(page, f)
        if f.ratio == "ultrawide":
            size = ULTRAWIDE
        else:
            # The tier sizes are all 16:9; another aspect ratio needs the original's real size instead.
            size = RES_TIERS.get(f.min_res) if f.ratio in ("any", "16:9") else None
        if size:
            items = [v for v in (variant(i, *size) for i in items) if v]
        return items

    def _search(self, page: int, f: Filters) -> list[Item]:
        query = f.query.strip()
        if f.category in _LABELS:
            url = f"{BASE}/{_PATHS.get(f.category, f.category)}/"
            if page > 1:
                url += f"?page={page}"
            tag = _LABELS[f.category].lower()
            return [replace(i, tags=[tag]) for i in parse_list(fetch_html("4K Wallpapers", url))]
        if query:
            url = f"{BASE}/search/?q={quote(query.replace(' ', '-'))}&text={quote(query)}"
            if page > 1:
                url += f"&page={page}"
        else:
            url = f"{BASE}/most-popular-4k-wallpapers/"
            if page > 1:
                url += f"?page={page}"
        return parse_list(fetch_html("4K Wallpapers", url))

    def details(self, item: Item) -> Item:
        full = parse_detail(fetch_html("4K Wallpapers", item.page_url), item)
        if item.extra.get("variant"):
            # Keep the ultra-wide file picked at listing time; the page only adds tags.
            return replace(full, download_url=item.download_url, width=item.width, height=item.height)
        return full

    def resolve_download(self, item: Item) -> str:
        url = self.details(item).download_url
        if not url:
            raise SourceError("4K Wallpapers download link not found")
        return url
