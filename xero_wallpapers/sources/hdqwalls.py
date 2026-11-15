import re
from dataclasses import replace
from urllib.parse import quote, urljoin

from bs4 import BeautifulSoup

from ..naming import clean_title
from ._html import fetch_html, parse_resolution
from .base import RES_TIERS, Filters, Item, Source, SourceError

BASE = "https://hdqwalls.com"
NAME = "hdqwalls"
LABEL = "HDQWalls"
CATEGORIES = (
    ("3d", "3D"),
    ("abstract", "Abstract"),
    ("animals", "Animals"),
    ("anime", "Anime"),
    ("artist", "Art"),
    ("bikes", "Bikes"),
    ("birds", "Birds"),
    ("cars", "Cars"),
    ("cartoons", "Cartoons"),
    ("celebrities", "Celebrities"),
    ("computer", "Computer"),
    ("flowers", "Flowers"),
    ("games", "Games"),
    ("logo", "Logo"),
    ("movies", "Movies"),
    ("music", "Music"),
    ("nature", "Nature"),
    ("photography", "Photography"),
    ("space", "Space"),
    ("sports", "Sports"),
    ("superheroes", "Superheroes"),
    ("tv-shows", "TV Shows"),
    ("typography", "Typography"),
    ("world", "World"),
)
_LABELS = dict(CATEGORIES)
_PATHS = {"space": "digital-universe"}
_TEMPLATE = re.compile(r"dynamic_resolution\s*=\s*'([^']*\{res\}[^']*)'")


def parse_list(html: str) -> list[Item]:
    items = []
    for el in BeautifulSoup(html, "html.parser").select("div.wall-resp"):
        img = el.select_one("img")
        link = img.find_parent("a") if img else None
        if not link or not link.get("href") or not img.get("src"):
            continue
        items.append(
            Item(
                source=NAME,
                kind="static",
                title=clean_title(img.get("alt") or link.get("title") or ""),
                thumb_url=urljoin(BASE, img["src"]),
                page_url=urljoin(BASE, link["href"]),
            )
        )
    return items


def _tags(soup: BeautifulSoup) -> list[str]:
    names = [a.get_text(strip=True) for a in soup.select("ol.breadcrumb a[href*='/category/']")]
    for heading in soup.select("div.panel-heading"):
        if heading.get_text(strip=True).lower() == "tags":
            names += [a.get_text(strip=True) for a in heading.find_next_siblings("a")]
    tags: list[str] = []
    for name in names:
        tag = name.lower()
        if tag and tag not in tags:
            tags.append(tag)
    return tags


def _best(soup: BeautifulSoup, html: str) -> tuple[str, int, int]:
    for a in soup.select("footer a[href*='/wallpapers/']"):
        w, h = parse_resolution(a.get_text())
        if w >= h > 0:
            return urljoin(BASE, a["href"]), w, h
    template = _TEMPLATE.search(html)
    if not template:
        return "", 0, 0
    best = (0, 0)
    for a in soup.select("a.resolution_links[href]"):
        w, h = parse_resolution(a["href"])
        if w >= h and w * h > best[0] * best[1]:
            best = (w, h)
    if not best[0]:
        return "", 0, 0
    return template.group(1).replace("{res}", f"{best[0]}x{best[1]}"), *best


def parse_detail(html: str, item: Item) -> Item:
    soup = BeautifulSoup(html, "html.parser")
    url, w, h = _best(soup, html)
    tags = list(dict.fromkeys(_tags(soup) + item.tags))
    if not url:
        return replace(item, tags=tags)
    return replace(item, download_url=url, width=w, height=h, tags=tags)


# The site renders every wallpaper at this ultra-wide size and at each RES_TIERS size too.
ULTRAWIDE = (3440, 1440)


def variant(item: Item, w: int, h: int) -> Item | None:
    file = item.thumb_url.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    if not file:
        return None
    url = f"https://images.hdqwalls.com/download/{file}-{w}x{h}.jpg"
    return replace(item, download_url=url, width=w, height=h, extra={**item.extra, "variant": True})


class HDQWallsSource(Source):
    name = NAME
    kind = "static"
    server_filters = frozenset({"query", "category", "ratio", "min_res"})
    sizes = "details"
    categories = CATEGORIES
    tags_in_details = True

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
            url = f"{BASE}/category/{_PATHS.get(f.category, f.category)}-wallpapers"
            if page > 1:
                url += f"/page/{page}"
            tag = _LABELS[f.category].lower()
            return [replace(i, tags=[tag]) for i in parse_list(fetch_html(LABEL, url))]
        if query:
            url = f"{BASE}/search?q={quote(query)}"
            if page > 1:
                url += f"&page={page}"
        else:
            url = f"{BASE}/popular-wallpapers"
            if page > 1:
                url += f"/page/{page}"
        return parse_list(fetch_html(LABEL, url))

    def details(self, item: Item) -> Item:
        full = parse_detail(fetch_html(LABEL, item.page_url), item)
        if item.extra.get("variant"):
            # Keep the ultra-wide file picked at listing time; the page only adds tags.
            return replace(full, download_url=item.download_url, width=item.width, height=item.height)
        return full

    def resolve_download(self, item: Item) -> str:
        url = self.details(item).download_url
        if not url:
            raise SourceError(f"{LABEL} download link not found")
        return url
