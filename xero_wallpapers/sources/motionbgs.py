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
_TAG = re.compile(r"/tag:([a-z0-9-]+)")
CATEGORIES = (
    ("anime", "Anime"),
    ("games", "Games"),
    ("superhero", "Superhero"),
    ("nature", "Nature"),
    ("car", "Car"),
    ("tv", "TV & Movie"),
    ("holiday", "Holiday"),
    ("animal", "Animal"),
    ("fantasy", "Fantasy"),
    ("space", "Space"),
    ("horror", "Horror"),
    ("technology", "Technology"),
    ("football", "Football"),
    ("japan", "Japan"),
)
_LABELS = dict(CATEGORIES)


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
        # Sub-category tiles link to /tag: pages, not wallpapers.
        if page_url in seen or "/tag:" in page_url:
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
    tags = _post_tags(soup)
    if tags:
        fields["tags"] = list(dict.fromkeys([*item.tags, *tags]))
    return replace(item, **fields)


def _post_tags(soup: BeautifulSoup) -> list[str]:
    # The post's own tags sit between its title and the download links; the menus also link /tag: pages.
    title = soup.select_one("h1")
    tags = []
    for a in title.find_all_next("a", href=True) if title else []:
        if "/dl/" in a["href"]:
            break
        m = _TAG.search(a["href"])
        if m:
            tags.append(m.group(1).replace("-", " "))
    return tags


class MotionBGsSource(Source):
    name = NAME
    kind = "live"
    server_filters = frozenset({"query", "category"})
    sizes = "details"
    categories = CATEGORIES
    tags_in_details = True

    def server_keys(self, f: Filters) -> frozenset[str]:
        if f.category in _LABELS:
            return self.server_filters - {"query"}
        return self.server_filters

    def search(self, page: int, f: Filters) -> list[Item]:
        label = _LABELS.get(f.category)
        if label:
            url = f"{BASE}/tag:{f.category}/" + (f"{page}/" if page > 1 else "")
            tag = label.lower()
            return [replace(i, tags=[*i.tags, tag]) for i in parse_list(fetch_html("MotionBGs", url))]
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
