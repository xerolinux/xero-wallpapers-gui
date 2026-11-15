import re
from dataclasses import replace
from urllib.parse import quote, urljoin

from bs4 import BeautifulSoup

from ..naming import clean_title
from ._html import fetch_html, parse_resolution, parse_size
from .base import ULTRAWIDE_RATIO, Filters, Item, Source, SourceError

BASE = "https://livewallpapers4free.com"
NAME = "livewallpapers4free"
ULTRAWIDE_CATEGORY = "5k2k-5120x2160"
_RES_CATEGORIES = {
    "2560x1440": (2560, 1440),
    "4k": (3840, 2160),
    "5k2k-5120x2160": (5120, 2160),
    "8k-7680x4320": (7680, 4320),
    "qhd-ultrawide-3440x1440": (3440, 1440),
    "dqhd-ultrawide-5120x1440": (5120, 1440),
}
CATEGORIES = (
    ("anime", "Anime"),
    ("games", "Games"),
    ("nature", "Nature"),
    ("animals", "Animals"),
    ("abstract", "Abstract"),
    ("cars", "Cars"),
    ("fantasy", "Fantasy"),
    ("sci-fi", "Sci-Fi"),
    ("movies-tv", "Movies & TV"),
    ("technology", "Technology"),
    ("3d", "3D"),
    ("people", "People"),
    ("world", "World"),
    ("holidays", "Holidays"),
)
_CATEGORY_LABELS = dict(CATEGORIES)
_LABELS = {"hd": 1920 * 1080, "2k": 2560 * 1440, "4k": 3840 * 2160, "8k": 7680 * 4320}
_LABEL = re.compile(r"(?<![a-z0-9])(hd|2k|4k|8k)(?![a-z0-9])", re.I)
_TITLE_NOISE = re.compile(
    r"(?:\s*[–|/-])?(?:\s*\b(?:\d+k|live|desktop|theme|background|quality)\b)+\s*$", re.I
)
# Some older titles were double-encoded (UTF-8 read as cp1252), e.g. "Khaâ€™Zix".
_MOJIBAKE = re.compile(
    "[\u00c2-\u00f4][" + re.escape(bytes(range(0x80, 0xC0)).decode("cp1252", "ignore")) + "]{1,3}"
)


def _unmangle(m: re.Match) -> str:
    try:
        return m.group(0).encode("cp1252").decode("utf-8")
    except UnicodeError:
        return m.group(0)


def _title(raw: str) -> str:
    raw = _MOJIBAKE.sub(_unmangle, raw)
    return clean_title(_TITLE_NOISE.sub("", raw.replace(" / ", " | ")))


def _categories(el) -> list[str]:
    return [c[len("category-"):] for c in el.get("class", []) if c.startswith("category-")]


def _category_tag(slug: str) -> str:
    return slug.removesuffix("-live-wallpapers").replace("-", " ").lower()


def parse_list(html: str) -> list[Item]:
    items = []
    for el in BeautifulSoup(html, "html.parser").select(".content-loop > div.post"):
        link = el.select_one(".entry-title a") or el.select_one("a[href]")
        img = el.select_one("img")
        if not link or not img or not link.get("href"):
            continue
        items.append(
            Item(
                source=NAME,
                kind="live",
                title=_title(link.get_text(strip=True) or img.get("alt") or ""),
                thumb_url=urljoin(BASE, img.get("src") or img.get("data-src") or ""),
                page_url=urljoin(BASE, link["href"]),
            )
        )
    return items


def _option(index: int, a) -> tuple[int, int, int, int, str]:
    box = a.find_parent(class_="wpz-sc-box") or a
    text = box.get_text(" ").replace("×", "x")
    w, h = parse_resolution(text)
    rank = w * h
    if not rank:
        m = _LABEL.search(text)
        rank = _LABELS[m.group(1).lower()] if m else 0
    return rank, index, w, h, text


def parse_detail(html: str, item: Item) -> Item:
    soup = BeautifulSoup(html, "html.parser")
    post = soup.select_one("article.post") or soup
    fields: dict = {"download_url": ""}
    links = post.select('a[href*="/download/"]')
    if links:
        options = [_option(i, a) for i, a in enumerate(links)]
        if item.extra.get("ultrawide"):
            options = [o for o in options if o[2] and o[3] and o[2] / o[3] >= ULTRAWIDE_RATIO] or options
        _, i, w, h, text = max(options)
        fields["download_url"] = urljoin(BASE, links[i]["href"])
        if w and h:
            fields["width"], fields["height"] = w, h
        size = parse_size(text)
        if size:
            fields["file_size"] = size
    if not fields.get("width"):
        sizes = [_RES_CATEGORIES[c] for c in _categories(post) if c in _RES_CATEGORIES]
        if len(sizes) == 1:
            fields["width"], fields["height"] = sizes[0]
    preview = post.select_one("video source[src]") or post.select_one("video[src]")
    if preview:
        fields["extra"] = {**item.extra, "preview_video": urljoin(BASE, preview["src"])}
    tags = [a.get_text(strip=True).lower() for a in post.select('a[rel~="tag"]')]
    tags += [_category_tag(c) for c in _categories(post) if c not in _RES_CATEGORIES]
    tags = list(dict.fromkeys(t for t in tags + item.tags if t))
    if tags:
        fields["tags"] = tags
    date = post.select_one('meta[itemprop="uploadDate"]')
    if date and date.get("content"):
        fields["uploaded"] = date["content"][:10]
    return replace(item, **fields)


class LW4FreeSource(Source):
    name = NAME
    kind = "live"
    server_filters = frozenset({"query", "category", "ratio"})
    sizes = "details"
    categories = CATEGORIES
    tags_in_details = True

    def search(self, page: int, f: Filters) -> list[Item]:
        label = _CATEGORY_LABELS.get(f.category)
        query = f.query.strip()
        slug = f"{f.category}-live-wallpapers"
        ultrawide = f.ratio == "ultrawide"
        if query:
            url = f"{BASE}/page/{page}/?s={quote(query)}"
            if label:
                url += f"&category_name={slug}"
        elif label:
            url = f"{BASE}/category/{slug}/page/{page}/"
        elif ultrawide:
            url = f"{BASE}/category/{ULTRAWIDE_CATEGORY}/page/{page}/"
        else:
            url = f"{BASE}/page/{page}/"
        items = parse_list(fetch_html("LiveWallpapers4Free", url))
        if ultrawide:
            # Posts offer several sizes; the detail check then picks the ultra-wide one.
            items = [replace(i, extra={**i.extra, "ultrawide": True}) for i in items]
        if label:
            for item in items:
                item.tags.append(label.lower())
        return items

    def details(self, item: Item) -> Item:
        return parse_detail(fetch_html("LiveWallpapers4Free", item.page_url), item)

    def resolve_download(self, item: Item) -> str:
        url = self.details(item).download_url
        if not url:
            raise SourceError("LiveWallpapers4Free download link not found")
        return url
