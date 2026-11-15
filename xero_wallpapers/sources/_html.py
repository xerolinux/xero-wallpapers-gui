import re
import threading
import time
from collections import OrderedDict

import requests

from .. import net
from .base import PageNotFound, SourceError

_RES = re.compile(r"(\d{3,5})x(\d{3,5})")
_SIZE = re.compile(r"([\d.]+)\s*([KMG])B", re.I)
_UNITS = {"K": 1024, "M": 1024**2, "G": 1024**3}
# Every filter change and repeated search lists page 1 onward again; reuse pages fetched in the last few minutes.
PAGE_TTL = 600
PAGE_LIMIT = 60
_pages: OrderedDict[str, tuple[float, str]] = OrderedDict()
_pages_lock = threading.Lock()


def fetch_html(name: str, url: str) -> str:
    with _pages_lock:
        hit = _pages.get(url)
        if hit and time.monotonic() - hit[0] < PAGE_TTL:
            _pages.move_to_end(url)
            return hit[1]
    text = _download(name, url)
    with _pages_lock:
        _pages[url] = (time.monotonic(), text)
        _pages.move_to_end(url)
        while len(_pages) > PAGE_LIMIT:
            _pages.popitem(last=False)
    return text


def _download(name: str, url: str) -> str:
    try:
        r = net.SESSION.get(url, timeout=net.TIMEOUT)
        if r.status_code == 404:
            raise PageNotFound(f"{name} has no page at {url}")
        r.raise_for_status()
        return r.text
    except requests.RequestException as e:
        raise SourceError(f"{name} request failed: {e}") from e


def parse_resolution(text: str) -> tuple[int, int]:
    m = _RES.search(text)
    return (int(m.group(1)), int(m.group(2))) if m else (0, 0)


def parse_size(text: str) -> int:
    m = _SIZE.search(text)
    return int(float(m.group(1)) * _UNITS[m.group(2).upper()]) if m else 0
