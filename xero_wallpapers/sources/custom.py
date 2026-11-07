import json
from dataclasses import replace
from urllib.parse import quote, urljoin, urlparse

from bs4 import BeautifulSoup
from soupsieve import SelectorSyntaxError

from ..naming import clean_title
from ._html import fetch_html, parse_resolution, parse_size
from .base import Filters, Item, Source, SourceError

KINDS = ("static", "live")
PARSERS = ("json", "html")
REQUIRED_FIELDS = ("title", "thumb", "link")


def _walk(node, path: str):
    if not path:
        return node
    head, _, rest = path.partition(".")
    many = head.endswith("[]")
    key = head[:-2] if many else head
    if key:
        if not isinstance(node, dict) or key not in node:
            return None
        node = node[key]
    if not many:
        return _walk(node, rest)
    if not isinstance(node, list):
        return None
    out = []
    for el in node:
        value = _walk(el, rest)
        if isinstance(value, list) and rest:
            out.extend(value)
        elif value is not None:
            out.append(value)
    return out


def _json_field(item, path: str, name: str):
    if "[]." in path:
        path = path.rsplit("[].", 1)[1]
    return _walk(item, path)


def _css(root, selector: str, name: str, first: bool = False):
    try:
        return root.select_one(selector) if first else root.select(selector)
    except SelectorSyntaxError as e:
        raise SourceError(f"{name}: invalid selector: {e}") from e


def _http(base: str, url: str) -> str:
    if not url:
        return ""
    url = urljoin(base, url)
    parts = urlparse(url)
    return url if parts.scheme in ("http", "https") and parts.netloc else ""


def _html_field(el, spec: str, name: str):
    selector, _, attr = spec.partition("@")
    target = _css(el, selector.strip(), name, first=True) if selector.strip() else el
    if target is None:
        return None
    if attr:
        return target.get(attr.strip())
    return target.get_text(strip=True)


def _text(value) -> str:
    if value is None or isinstance(value, (dict, list)):
        return ""
    return str(value).strip()


def _int(value) -> int:
    try:
        return int(float(_text(value)))
    except (ValueError, OverflowError):
        return 0


def _tags(value) -> list[str]:
    if isinstance(value, list):
        return [t for t in (_text(v) for v in value) if t]
    return [t.strip() for t in _text(value).split(",") if t.strip()]


def _size(value) -> int:
    text = _text(value)
    return int(float(text)) if text.replace(".", "", 1).isdigit() else parse_size(text)


def _map(base: str, cfg: dict, raw, read) -> Item | None:
    fields = cfg["fields"]

    def get(key):
        spec = fields.get(key)
        return read(raw, spec, cfg["name"]) if spec else None

    thumb = _http(base, _text(get("thumb")))
    link = _http(base, _text(get("link")))
    if not thumb or not link:
        return None
    width, height = _int(get("width")), _int(get("height"))
    if not (width and height):
        width, height = parse_resolution(_text(get("resolution")))
    return Item(
        source=cfg["name"],
        kind=cfg["kind"],
        title=clean_title(_text(get("title"))),
        thumb_url=thumb,
        page_url=link,
        width=width,
        height=height,
        tags=_tags(get("tags")),
        author=_text(get("author")),
        file_size=_size(get("size")),
    )


class CustomSource(Source):
    server_filters = frozenset({"query"})

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.name = cfg["name"]
        self.kind = cfg["kind"]
        fields = cfg.get("fields") or {}
        self.sizes = "listed" if fields.get("resolution") or (fields.get("width") and fields.get("height")) else "none"

    def _url(self, page: int, f: Filters) -> str:
        return self.cfg["search_url"].replace("{query}", quote(f.query.strip())).replace(
            "{page}", str(page)
        )

    def search(self, page: int, f: Filters) -> list[Item]:
        if page > 1 and "{page}" not in self.cfg["search_url"]:
            return []
        url = self._url(page, f)
        body = fetch_html(self.name, url)
        if self.cfg["parser"] == "json":
            try:
                data = json.loads(body)
            except ValueError as e:
                raise SourceError(f"{self.name} returned invalid JSON: {e}") from e
            raw = _walk(data, self.cfg["items"])
            if not isinstance(raw, list):
                raise SourceError(f"{self.name}: items path {self.cfg['items']!r} is not a list")
            read = _json_field
        else:
            raw = _css(BeautifulSoup(body, "html.parser"), self.cfg["items"], self.name)
            read = _html_field
        items = (_map(url, self.cfg, r, read) for r in raw)
        return [i for i in items if i]

    def details(self, item: Item) -> Item:
        selector = self.cfg.get("detail_download")
        if not selector or item.download_url:
            return item
        soup = BeautifulSoup(fetch_html(self.name, item.page_url), "html.parser")
        el = _css(soup, selector, self.name, first=True)
        link = _http(item.page_url, (el.get("href") or el.get("src") or "") if el else "")
        if not link:
            raise SourceError(f"{self.name} download link not found")
        return replace(item, download_url=link)

    def resolve_download(self, item: Item) -> str:
        return self.details(item).download_url or item.page_url


def validate_custom(cfg) -> list[str]:
    if not isinstance(cfg, dict):
        return ["entry is not an object"]
    errors = []
    if not str(cfg.get("name", "")).strip():
        errors.append("name is required")
    if cfg.get("kind") not in KINDS:
        errors.append("kind must be static or live")
    if cfg.get("parser") not in PARSERS:
        errors.append("parser must be json or html")
    url = cfg.get("search_url")
    if not isinstance(url, str) or not url.strip():
        errors.append("search_url is required")
    else:
        parts = urlparse(url)
        if parts.scheme not in ("http", "https") or not parts.netloc:
            errors.append("search_url must be a valid http:// or https:// URL")
        if "{query}" not in url:
            errors.append("search_url must contain {query}")
    if not isinstance(cfg.get("items"), str) or not cfg["items"].strip():
        errors.append("items is required")
    fields = cfg.get("fields")
    if not isinstance(fields, dict):
        fields = {}
    for key in REQUIRED_FIELDS:
        spec = fields.get(key)
        if not isinstance(spec, str) or not spec.strip():
            errors.append(f"fields.{key} is required")
    for key, spec in fields.items():
        if key not in REQUIRED_FIELDS and not isinstance(spec, str):
            errors.append(f"fields.{key} must be a string")
    if not isinstance(cfg.get("detail_download", ""), str):
        errors.append("detail_download must be a string")
    return errors


def test(cfg: dict) -> tuple[int, dict]:
    errors = validate_custom(cfg)
    if errors:
        raise SourceError("; ".join(errors))
    items = CustomSource(cfg).search(1, Filters())
    if not items:
        raise SourceError("no items found, check the items selector and fields")
    first = items[0]
    mapped = {
        "title": first.title,
        "thumb_url": first.thumb_url,
        "page_url": first.page_url,
        "width": first.width,
        "height": first.height,
        "tags": first.tags,
        "author": first.author,
        "file_size": first.file_size,
    }
    return len(items), mapped
