import json
import logging
import os
from dataclasses import asdict, fields
from pathlib import Path

from . import paths
from .sources.base import Item

log = logging.getLogger("xero_wallpapers.checkcache")

FILE = Path(paths.CACHE_DIR) / "checks.json"
# Newest entries win; a few thousand keeps the file around a couple of MB.
LIMIT = 5000
_FIELDS = {f.name for f in fields(Item)}


class CheckCache:
    """Detail-page lookups, A.I verdicts and palettes kept across runs, so wallpapers seen once show instantly."""

    def __init__(self, path: Path = FILE):
        self._path = path
        self.details: dict[str, Item] = {}
        self.vision: dict[str, bool] = {}
        self.colors: dict[str, list[str]] = {}
        try:
            data = json.loads(path.read_text())
            self.details = {
                url: Item(**{k: v for k, v in raw.items() if k in _FIELDS})
                for url, raw in data.get("details", {}).items()
            }
            self.vision = {url: bool(v) for url, v in data.get("vision", {}).items()}
            self.colors = {url: list(v) for url, v in data.get("colors", {}).items()}
        except (OSError, ValueError, TypeError) as e:
            if not isinstance(e, FileNotFoundError):
                log.warning("ignoring the check cache: %s", e)

    def snapshot(self) -> dict:
        details = list(self.details.items())[-LIMIT:]
        vision = list(self.vision.items())[-LIMIT:]
        colors = list(self.colors.items())[-LIMIT:]
        return {
            "details": {url: asdict(item) for url, item in details},
            "vision": dict(vision),
            "colors": dict(colors),
        }

    def save(self, snapshot: dict):
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_name(self._path.name + ".tmp")
            tmp.write_text(json.dumps(snapshot))
            os.replace(tmp, self._path)
        except OSError as e:
            log.warning("couldn't save the check cache: %s", e)
