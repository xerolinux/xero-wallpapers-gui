from dataclasses import replace
from urllib.parse import quote, urljoin

from bs4 import BeautifulSoup

from ..naming import clean_title
from ._html import fetch_html, parse_resolution, parse_size
from .base import Filters, Item, Source, SourceError

BASE = "https://moewalls.com"
NAME = "moewalls"
# The ultra-wide size with by far the most clips on the site.
ULTRAWIDE_RESOLUTION = "3440x1440"
DOWNLOAD = "https://go.moewalls.com/download.php?video="
CATEGORIES = (
    ("anime", "Anime"),
    ("games", "Games"),
    ("fantasy", "Fantasy"),
    ("landscape", "Landscape"),
    ("sci-fi", "Sci-Fi"),
    ("lifestyle", "Lifestyle"),
    ("movies", "Movies"),
    ("abstract", "Abstract"),
    ("vehicle", "Vehicle"),
    ("pixel-art", "Pixel Art"),
    ("animal", "Animal"),
    ("others", "Others"),
)
_LABELS = dict(CATEGORIES)


def parse_list(html: str) -> list[Item]:
    items = []
    for el in BeautifulSoup(html, "html.parser").select("article"):
        link = el.select_one("a")
        img = el.select_one("img")
        if not link or not img or not link.get("href"):
            continue
        title_el = el.select_one(".entry-title")
        res = el.select_one(".entry-resolutions a")
        w, h = parse_resolution(res.get_text()) if res else (0, 0)
        items.append(
            Item(
                source=NAME,
                kind="live",
                title=clean_title(
                    (title_el.get_text(strip=True) if title_el else "") or link.get("title") or ""
                ),
                thumb_url=urljoin(BASE, img.get("src") or img.get("data-src") or ""),
                page_url=urljoin(BASE, link["href"]),
                width=w,
                height=h,
            )
        )
    return items


def _meta(soup: BeautifulSoup, label: str):
    for em in soup.select("ul.list-inline li em"):
        if em.get_text(strip=True) == label:
            return em.parent
    return None


def parse_detail(html: str, item: Item) -> Item:
    soup = BeautifulSoup(html, "html.parser")
    fields: dict = {"download_url": ""}
    extra = dict(item.extra)
    button = soup.select_one("#moe-download")
    if button and button.get("data-url"):
        fields["download_url"] = DOWNLOAD + button["data-url"]
        extra["data_id"] = button.get("data-id", "")
    preview = soup.select_one("video source[src]")
    if preview:
        extra["preview_video"] = urljoin(BASE, preview["src"])
    if extra != item.extra:
        fields["extra"] = extra
    res = _meta(soup, "Resolution")
    if res:
        w, h = parse_resolution(res.get_text())
        if w and h:
            fields["width"], fields["height"] = w, h
    size = _meta(soup, "File Size")
    if size:
        fields["file_size"] = parse_size(size.get_text())
    date = _meta(soup, "Date")
    if date:
        fields["uploaded"] = date.get_text().replace("Date", "", 1).strip()
    tags = [a.get_text(strip=True) for a in soup.select(".tag-items a")]
    if tags:
        fields["tags"] = list(dict.fromkeys([*tags, *item.tags]))
    return replace(item, **fields)


class MoeWallsSource(Source):
    name = NAME
    kind = "live"
    server_filters = frozenset({"query", "category", "ratio"})
    sizes = "details"
    categories = CATEGORIES
    tags_in_details = True

    def search(self, page: int, f: Filters) -> list[Item]:
        label = _LABELS.get(f.category)
        query = f.query.strip()
        if label:
            url = f"{BASE}/category/{f.category}/page/{page}/"
        elif f.ratio == "ultrawide" and not query:
            url = f"{BASE}/resolution/{ULTRAWIDE_RESOLUTION}/page/{page}/"
        else:
            url = f"{BASE}/page/{page}/"
        if query:
            url += f"?s={quote(query)}"
        items = parse_list(fetch_html("MoeWalls", url))
        if label:
            items = [replace(i, tags=[*i.tags, label.lower()]) for i in items]
        return items

    def details(self, item: Item) -> Item:
        return parse_detail(fetch_html("MoeWalls", item.page_url), item)

    def resolve_download(self, item: Item) -> str:
        url = self.details(item).download_url
        if not url:
            raise SourceError("MoeWalls download link not found")
        return url
