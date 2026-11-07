import copy
import json
import os
from pathlib import Path

from . import paths


def _defaults():
    return {
        "static_download_dir": os.path.expanduser("~/Pictures/Wallpapers"),
        "live_download_dir": os.path.expanduser("~/Videos/Live Wallpapers"),
        "live_enabled": False,
        "first_run_done": False,
        "skip_duplicates": True,
        "hide_duplicates": True,
        "disabled_sources": [],
        "custom_sources": [],
        "safe_content": True,
        "match_screen": True,
        "cache_size_mb": 500,
        "slideshow_enabled": False,
        "slideshow_minutes": 60,
        "slideshow_order": "random",
        "slideshow_transition": "fade",
        "slideshow_transition_ms": 1200,
    }


class Config:
    def __init__(self, data):
        self._data = data

    @classmethod
    def load(cls):
        data = _defaults()
        path = Path(paths.CONFIG_FILE)
        try:
            raw = json.loads(path.read_text())
            if not isinstance(raw, dict):
                raise ValueError("config root is not an object")
        except OSError:
            return cls(data)
        except ValueError:
            try:
                os.replace(path, path.with_name(path.name + ".bad"))
            except OSError:
                pass
            return cls(data)
        data.update({k: v for k, v in raw.items() if k in data})
        return cls(data)

    def get(self, key):
        return copy.deepcopy(self._data[key])

    def set(self, key, value):
        if key not in self._data:
            raise KeyError(key)
        self._data[key] = value
        self.save()

    def save(self):
        path = Path(paths.CONFIG_FILE)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(self._data, indent=2))
        os.replace(tmp, path)
