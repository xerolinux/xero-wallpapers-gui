import configparser
import logging
import os
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QFontDatabase, QIcon, QPalette
from PyQt6.QtWidgets import QApplication, QStyleFactory

DATA = Path(__file__).resolve().parent / "data"
SCHEME = DATA / "Layan.colors"
# Holds Kvantum/kvantum.kvconfig (theme=LayanDark) and the LayanDark theme, laid out like ~/.config.
KVANTUM_CONFIG = DATA / "kvantum"
FONTS = DATA / "fonts"
FONT_FAMILY = "Noto Sans"
FONT_POINTS = 10
# Kirigami takes its small font from the desktop, which only Plasma provides; this keeps it the same everywhere.
SMALL_POINTS = 8
ICON_THEME = "breeze-dark"
DISABLED_FADE = 0.55

log = logging.getLogger("xero_wallpapers.theme")


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


def _kvantum():
    # Kvantum reads its theme from $XDG_CONFIG_HOME/Kvantum only while the style is created, so point it at
    # the bundled LayanDark for that moment; the user's own Kvantum setup (if any) is never touched.
    previous = os.environ.get("XDG_CONFIG_HOME")
    os.environ["XDG_CONFIG_HOME"] = str(KVANTUM_CONFIG)
    try:
        return QStyleFactory.create("kvantum")
    finally:
        if previous is None:
            del os.environ["XDG_CONFIG_HOME"]
        else:
            os.environ["XDG_CONFIG_HOME"] = previous


def _font() -> QFont:
    if FONT_FAMILY not in QFontDatabase.families():
        for path in sorted(FONTS.glob("*.ttf")):
            QFontDatabase.addApplicationFont(str(path))
    return QFont(FONT_FAMILY, FONT_POINTS)


def apply(app: QApplication):
    style = _kvantum()
    if style is None:
        log.warning("Kvantum is not installed; controls fall back to Fusion")
        style = QStyleFactory.create("Fusion")
    app.setStyle(style)
    # Read by KColorScheme, so Kirigami's org.kde.desktop theme and KDE icon recolouring use Layan too.
    app.setProperty("KDE_COLOR_SCHEME_PATH", str(SCHEME))
    app.setPalette(_palette(_read(SCHEME)))
    app.setFont(_font())
    app.styleHints().setColorScheme(Qt.ColorScheme.Dark)
    QIcon.setThemeName(ICON_THEME)
    QIcon.setFallbackThemeName(ICON_THEME)
