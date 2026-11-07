import logging

from ..config import Config
from .base import Source
from .custom import CustomSource, validate_custom
from .fourk import FourKSource
from .moewalls import MoeWallsSource
from .motionbgs import MotionBGsSource
from .wallhaven import WallhavenSource

log = logging.getLogger("xero_wallpapers.sources")

BUILTINS = (WallhavenSource, FourKSource, MoeWallsSource, MotionBGsSource)


def build_sources(config: Config) -> list[Source]:
    disabled = set(config.get("disabled_sources"))
    safe = bool(config.get("safe_content"))
    sources: list[Source] = [cls(safe=safe) if cls is WallhavenSource else cls() for cls in BUILTINS]
    for cfg in config.get("custom_sources"):
        errors = validate_custom(cfg)
        if not errors and any(s.name == cfg["name"] for s in sources):
            errors = [f"name {cfg['name']!r} is already in use"]
        if errors:
            label = cfg.get("name", "?") if isinstance(cfg, dict) else "?"
            log.warning("skipping custom source %s: %s", label, "; ".join(errors))
            continue
        sources.append(CustomSource(cfg))
    return [s for s in sources if s.name not in disabled]
