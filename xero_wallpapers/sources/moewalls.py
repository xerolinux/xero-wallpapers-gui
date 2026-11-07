from dataclasses import replace
from urllib.parse import quote, urljoin

from bs4 import BeautifulSoup

from ..naming import clean_title
from ._html import fetch_html, parse_resolution, parse_size
from .base import Filters, Item, Source, SourceError

BASE = "https://moewalls.com"
NAME = "moewalls"
DOWNLOAD = "https://go.moewalls.com/download.php?video="


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
        fields["tags"] = tags
    return replace(item, **fields)


class MoeWallsSource(Source):
    name = NAME
    kind = "live"
    server_filters = frozenset({"query"})
    sizes = "details"

    def search(self, page: int, f: Filters) -> list[Item]:
        url = f"{BASE}/page/{page}/"
        if f.query.strip():
            url += f"?s={quote(f.query.strip())}"
        return parse_list(fetch_html("MoeWalls", url))

    def details(self, item: Item) -> Item:
        return parse_detail(fetch_html("MoeWalls", item.page_url), item)

    def resolve_download(self, item: Item) -> str:
        url = self.details(item).download_url
        if not url:
            raise SourceError("MoeWalls download link not found")
        return url
