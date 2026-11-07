import re
from dataclasses import replace
from urllib.parse import quote, urljoin

from bs4 import BeautifulSoup

from ..naming import clean_title
from ._html import fetch_html, parse_resolution, parse_size
from .base import Filters, Item, Source, SourceError

BASE = "https://motionbgs.com"
NAME = "motionbgs"
_MEDIA_ID = re.compile(r"/media/(\d+)/")


def parse_list(html: str) -> list[Item]:
    items = []
    seen = set()
    for link in BeautifulSoup(html, "html.parser").select("a[href]"):
        img = link.select_one("img")
        if not img:
            continue
        thumb = img.get("src") or img.get("data-src") or ""
        if "/media/" not in thumb and "/i/" not in thumb:
            continue
        page_url = urljoin(BASE, link["href"])
        if page_url in seen:
            continue
        seen.add(page_url)
        ttl = link.select_one(".ttl")
        m = _MEDIA_ID.search(thumb)
        items.append(
            Item(
                source=NAME,
                kind="live",
                title=clean_title(
                    (ttl.get_text(strip=True) if ttl else "")
                    or img.get("alt")
                    or link.get_text(strip=True)
                ),
                thumb_url=urljoin(BASE, thumb),
                page_url=page_url,
                extra={"media_id": m.group(1)} if m else {},
            )
        )
    return items


def parse_detail(html: str, item: Item) -> Item:
    fields: dict = {}
    soup = BeautifulSoup(html, "html.parser")
    dl = soup.select_one("a[href*='/dl/4k/']") or soup.select_one("a[href*='/dl/']")
    if dl:
        fields["download_url"] = urljoin(BASE, dl["href"])
        w, h = parse_resolution(dl.get_text(" "))
        if w and h:
            fields["width"], fields["height"] = w, h
        fields["file_size"] = parse_size(dl.get_text(" "))
    preview = soup.select_one("video source[src]")
    if preview:
        fields["extra"] = {**item.extra, "preview_video": urljoin(BASE, preview["src"])}
    return replace(item, **fields)


class MotionBGsSource(Source):
    name = NAME
    kind = "live"
    server_filters = frozenset({"query"})
    sizes = "details"

    def search(self, page: int, f: Filters) -> list[Item]:
        if f.query.strip():
            url = f"{BASE}/{page}/?s={quote(f.query.strip())}"
        else:
            url = f"{BASE}/{page}/" if page > 1 else f"{BASE}/"
        return parse_list(fetch_html("MotionBGs", url))

    def details(self, item: Item) -> Item:
        return parse_detail(fetch_html("MotionBGs", item.page_url), item)

    def resolve_download(self, item: Item) -> str:
        media_id = item.extra.get("media_id")
        if media_id:
            return f"{BASE}/dl/4k/{media_id}"
        url = self.details(item).download_url
        if not url:
            raise SourceError("MotionBGs download link not found")
        return url
