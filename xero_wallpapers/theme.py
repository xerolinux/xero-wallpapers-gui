import configparser
import os
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QGuiApplication, QIcon, QPalette

from . import paths

FALLBACK = "Layan.colors"
BUNDLED = Path(__file__).resolve().parent / "data" / FALLBACK
ICON_THEME = "breeze-dark"
DISABLED_FADE = 0.55


def _read(path: Path) -> configparser.ConfigParser:
    cfg = configparser.ConfigParser(interpolation=None, strict=False)
    cfg.optionxform = str
    try:
        cfg.read(path, encoding="utf-8")
    except (OSError, configparser.Error):
        pass
    return cfg


def _rgb(value: str) -> tuple[int, int, int] | None:
    try:
        r, g, b = (int(part) for part in value.split(",")[:3])
    except ValueError:
        return None
    return r, g, b


def _plasma() -> bool:
    return "KDE" in os.environ.get("XDG_CURRENT_DESKTOP", "").split(":")


def _system_is_dark() -> bool:
    if not _plasma():
        return False
    kdeglobals = _read(Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "kdeglobals")
    # KColorScheme reads the active colours from kdeglobals; with none written Plasma uses light Breeze defaults.
    rgb = _rgb(kdeglobals.get("Colors:Window", "BackgroundNormal", fallback=""))
    return rgb is not None and QColor(*rgb).lightnessF() < 0.5


def _fallback_scheme() -> Path:
    for base in (paths.DATA_HOME, *paths.SYSTEM_DATA_DIRS):
        candidate = base / "color-schemes" / FALLBACK
        if candidate.is_file():
            return candidate
    return BUNDLED


def _palette(scheme: configparser.ConfigParser) -> QPalette:
    def color(group: str, key: str) -> QColor:
        rgb = _rgb(scheme.get(f"Colors:{group}", key, fallback="")) or (128, 128, 128)
        return QColor(*rgb)

    window = color("Window", "BackgroundNormal")
    roles = {
        QPalette.ColorRole.Window: window,
        QPalette.ColorRole.WindowText: color("Window", "ForegroundNormal"),
        QPalette.ColorRole.Base: color("View", "BackgroundNormal"),
        QPalette.ColorRole.AlternateBase: color("View", "BackgroundAlternate"),
        QPalette.ColorRole.Text: color("View", "ForegroundNormal"),
        QPalette.ColorRole.PlaceholderText: color("View", "ForegroundInactive"),
        QPalette.ColorRole.Button: color("Button", "BackgroundNormal"),
        QPalette.ColorRole.ButtonText: color("Button", "ForegroundNormal"),
        QPalette.ColorRole.Highlight: color("Selection", "BackgroundNormal"),
        QPalette.ColorRole.HighlightedText: color("Selection", "ForegroundNormal"),
        QPalette.ColorRole.Accent: color("Selection", "BackgroundNormal"),
        QPalette.ColorRole.ToolTipBase: color("Tooltip", "BackgroundNormal"),
        QPalette.ColorRole.ToolTipText: color("Tooltip", "ForegroundNormal"),
        QPalette.ColorRole.Link: color("View", "ForegroundLink"),
        QPalette.ColorRole.LinkVisited: color("View", "ForegroundVisited"),
        QPalette.ColorRole.BrightText: color("Window", "ForegroundNegative"),
        QPalette.ColorRole.Light: window.lighter(150),
        QPalette.ColorRole.Midlight: window.lighter(125),
        QPalette.ColorRole.Mid: window.darker(150),
        QPalette.ColorRole.Dark: window.darker(200),
        QPalette.ColorRole.Shadow: QColor(0, 0, 0),
    }
    pal = QPalette()
    for role, value in roles.items():
        pal.setColor(role, value)
    for fg, bg in (
        (QPalette.ColorRole.WindowText, QPalette.ColorRole.Window),
        (QPalette.ColorRole.Text, QPalette.ColorRole.Base),
        (QPalette.ColorRole.ButtonText, QPalette.ColorRole.Button),
    ):
        a, b = roles[fg], roles[bg]
        faded = QColor.fromRgbF(*(x + (y - x) * DISABLED_FADE for x, y in zip(a.getRgbF()[:3], b.getRgbF()[:3])))
        pal.setColor(QPalette.ColorGroup.Disabled, fg, faded)
    return pal


def apply(app: QGuiApplication):
    QIcon.setFallbackThemeName(ICON_THEME)
    if _system_is_dark():
        return
    scheme = _fallback_scheme()
    # Read by KColorScheme, so Kirigami's org.kde.desktop theme and KDE icon recolouring use this scheme.
    app.setProperty("KDE_COLOR_SCHEME_PATH", str(scheme))
    app.setPalette(_palette(_read(scheme)))
    app.styleHints().setColorScheme(Qt.ColorScheme.Dark)
    # Only Plasma recolours symbolic icons to the forced palette; elsewhere a light theme's glyphs would vanish.
    if not _plasma() or QIcon.themeName() in ("", "hicolor"):
        QIcon.setThemeName(ICON_THEME)
