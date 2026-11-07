from dataclasses import replace
from urllib.parse import quote, urljoin

from bs4 import BeautifulSoup

from ..naming import clean_title
from ._html import fetch_html, parse_resolution
from .base import Filters, Item, Source, SourceError

BASE = "https://4kwallpapers.com"
NAME = "4kwallpapers"


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


class FourKSource(Source):
    name = NAME
    kind = "static"
    server_filters = frozenset({"query"})
    sizes = "details"

    def search(self, page: int, f: Filters) -> list[Item]:
        query = f.query.strip()
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
        return parse_detail(fetch_html("4K Wallpapers", item.page_url), item)

    def resolve_download(self, item: Item) -> str:
        url = self.details(item).download_url
        if not url:
            raise SourceError("4K Wallpapers download link not found")
        return url
