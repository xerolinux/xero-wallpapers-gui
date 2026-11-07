import re

import requests

from .. import net
from .base import SourceError

_RES = re.compile(r"(\d{3,5})x(\d{3,5})")
_SIZE = re.compile(r"([\d.]+)\s*([KMG])B", re.I)
_UNITS = {"K": 1024, "M": 1024**2, "G": 1024**3}


def fetch_html(name: str, url: str) -> str:
    try:
        r = net.SESSION.get(url, timeout=net.TIMEOUT)
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
