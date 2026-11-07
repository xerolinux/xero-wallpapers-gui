import os
from pathlib import Path


def _xdg(var, fallback):
    return Path(os.environ.get(var) or Path.home() / fallback)


CONFIG_FILE = _xdg("XDG_CONFIG_HOME", ".config") / "xero-wallpaper-browser" / "config.json"
CACHE_DIR = _xdg("XDG_CACHE_HOME", ".cache") / "xero-wallpaper-browser"
DATA_DIR = _xdg("XDG_DATA_HOME", ".local/share") / "xero-wallpapers"
LOG_FILE = CACHE_DIR / "log.txt"
