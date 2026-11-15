import re
from dataclasses import replace
from urllib.parse import quote, unquote, urljoin

from bs4 import BeautifulSoup

from ..naming import clean_title
from ._html import fetch_html, parse_resolution, parse_size
from .base import Filters, Item, Source, SourceError

BASE = "https://www.desktophut.com"
NAME = "desktophut"
_ALT_SUFFIX = re.compile(r"\s*-\s*Free Live Wallpaper\s*$", re.I)
_VIDEO = re.compile(r"\.(mp4|webm|mkv)$", re.I)
_CATEGORY_SUFFIX = re.compile(r"-?(?:live-)?wallpapers?$", re.I)
CATEGORIES = (
    ("anime", "Anime"),
    ("games", "Games"),
    ("nature", "Nature"),
    ("landscape", "Landscape"),
    ("animals", "Animals"),
    ("abstract", "Abstract"),
    ("cars", "Cars"),
    ("vehicles", "Vehicles"),
    ("sci-fi", "Sci-Fi & Fantasy"),
    ("movies-tv", "Movies & TV"),
    ("comics", "Comics"),
    ("tech", "Tech"),
    ("pixel-art", "Pixel Art"),
    ("3d", "3D Animation"),
    ("people", "People"),
    ("lofi", "Lofi"),
    ("world", "World"),
    ("holidays", "Holidays"),
    ("rgb", "RGB"),
)
_PATHS = {
    "cars": "cars-motorcycles-live-wallpapers",
    "sci-fi": "sci-fi-fantasy-live-wallpapers",
    "movies-tv": "movies-and-tv-live-wallpapers",
    "3d": "3d-animation-live-wallpapers",
    "lofi": "Lofi",
}
_LABELS = dict(CATEGORIES)


def parse_list(html: str) -> list[Item]:
    items = []
    seen = set()
    for card in BeautifulSoup(html, "html.parser").select("a.wallpaper-card[href]"):
        if "dh-wotd-card" in card.get("class", []):
            continue
        img = card.select_one("img")
        res = card.select_one(".badge-res")
        w, h = parse_resolution(res.get_text()) if res else (0, 0)
        page_url = urljoin(BASE, card["href"])
        # Video cards show their resolution; Wallpaper Engine scenes and web packages show
        # "Scene" / "WEB" and download as zips the video player cannot use.
        if not img or not w or page_url in seen:
            continue
        seen.add(page_url)
        title_el = card.select_one(".card-title")
        preview = card.select_one("video[data-src]")
        items.append(
            Item(
                source=NAME,
                kind="live",
                title=clean_title(
                    (title_el.get_text(strip=True) if title_el else "")
                    or _ALT_SUFFIX.sub("", img.get("alt") or "")
                ),
                thumb_url=urljoin(BASE, img.get("src") or img.get("data-src") or ""),
                page_url=page_url,
                width=w,
                height=h,
                extra={"preview_video": urljoin(BASE, preview["data-src"])} if preview else {},
            )
        )
    return items


def _tag(a) -> str:
    href = unquote(a["href"])
    if "/category/" in href:
        slug = _CATEGORY_SUFFIX.sub("", href.rsplit("/category/", 1)[1].strip("/"))
        return re.sub(r"[-\s]+", " ", slug).strip().lower()
    return re.sub(r"^[^\w]+", "", a.get_text(" ", strip=True)).strip().lower()


def parse_detail(html: str, item: Item) -> Item:
    soup = BeautifulSoup(html, "html.parser")
    fields: dict = {"download_url": ""}
    dl = soup.select_one("#primaryDownloadBtn[href]")
    video = _VIDEO.search(dl["href"]) if dl else None
    if video:
        fields["download_url"] = urljoin(BASE, dl["href"])
        fields["file_type"] = video.group(1).lower()
        label = dl.get_text(" ", strip=True)
        w, h = parse_resolution(label)
        if w and h:
            fields["width"], fields["height"] = w, h
        size = parse_size(label)
        if size:
            fields["file_size"] = size
    preview = soup.select_one("video source[src]")
    if preview:
        fields["extra"] = {**item.extra, "preview_video": urljoin(BASE, preview["src"])}
    tags = list(item.tags)
    for a in soup.select("a.hover-yellow-text[href], a.tag-link[href]"):
        if "/tag/" in a["href"] or "/category/" in a["href"]:
            tag = _tag(a)
            if tag and tag not in tags:
                tags.append(tag)
    if tags:
        fields["tags"] = tags
    return replace(item, **fields)


class DesktopHutSource(Source):
    name = NAME
    kind = "live"
    server_filters = frozenset({"query", "category", "ratio"})
    sizes = "listed"
    categories = CATEGORIES
    tags_in_details = True

    def server_keys(self, f: Filters) -> frozenset[str]:
        if f.category in _LABELS:
            return self.server_filters - {"query"}
        return self.server_filters

    def search(self, page: int, f: Filters) -> list[Item]:
        label = _LABELS.get(f.category)
        query = f.query.strip()
        if label:
            url = f"{BASE}/category/{_PATHS.get(f.category, f.category + '-live-wallpapers')}"
        else:
            if not query and f.ratio == "ultrawide":
                query = "ultrawide"
            url = f"{BASE}/search/{quote(query, safe='')}" if query else BASE
        if page > 1:
            url += f"?page={page}"
        items = parse_list(fetch_html("DesktopHut", url))
        if label:
            for item in items:
                if label.lower() not in item.tags:
                    item.tags.append(label.lower())
        return items

    def details(self, item: Item) -> Item:
        return parse_detail(fetch_html("DesktopHut", item.page_url), item)

    def resolve_download(self, item: Item) -> str:
        url = self.details(item).download_url
        if not url:
            raise SourceError("DesktopHut video download link not found")
        return url
