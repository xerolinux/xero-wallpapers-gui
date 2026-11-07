import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from PyQt6.QtCore import QTimer, QUrl
from PyQt6.QtGui import QGuiApplication, QIcon
from PyQt6.QtQml import QQmlApplicationEngine

from . import VERSION, net, paths, slideshow, theme
from .config import Config
from .sources.registry import build_sources
from .sources.wallhaven import tag_fetcher
from .ui.controllers import (
    AppUpdateController,
    BrowseController,
    DetailController,
    DownloadController,
    EditorController,
    LibraryController,
    SettingsController,
    SvwrController,
    screen_res,
)
from .ui.thumbs import THUMB_EXECUTOR, ThumbProvider

PACKAGE_DIR = Path(__file__).resolve().parent
LOGO = PACKAGE_DIR.parent / "xero_logo.png"

log = logging.getLogger("xero_wallpapers")
QUIT_GRACE = 2.0


def _setup_logging():
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    try:
        Path(paths.LOG_FILE).parent.mkdir(parents=True, exist_ok=True)
        handlers.append(RotatingFileHandler(paths.LOG_FILE, maxBytes=1024 * 1024, backupCount=3))
    except OSError:
        pass
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
    )


def _excepthook(exc_type, exc, tb):
    # PyQt6 aborts on exceptions escaping slots unless sys.excepthook is replaced.
    log.error("unhandled exception", exc_info=(exc_type, exc, tb))


def _screen_res(app: QGuiApplication) -> str:
    screen = app.primaryScreen()
    if screen is None:
        return "any"
    size, ratio = screen.size(), screen.devicePixelRatio()
    return screen_res(round(size.width() * ratio), round(size.height() * ratio))


def coalesced(fn):
    timer = QTimer()
    timer.setSingleShot(True)
    timer.setInterval(0)
    timer.timeout.connect(fn)
    return timer.start


def main():
    _setup_logging()
    sys.excepthook = _excepthook

    # Kirigami's built-in fallback theme is light-only; the desktop style follows the Layan fallback scheme.
    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "org.kde.desktop")
    app = QGuiApplication(sys.argv)
    app.setApplicationName("xero-wallpaper-browser")
    app.setApplicationDisplayName("Xero Wallpapers")
    app.setApplicationVersion(VERSION)
    app.setDesktopFileName("xero-wallpaper-browser")
    app.setWindowIcon(QIcon(str(LOGO)))
    theme.apply(app)

    config = Config.load()
    sources = build_sources(config)
    svwr = SvwrController(config)
    settings = SettingsController(config, svwr)
    tags = tag_fetcher()
    native_res = _screen_res(app)
    browse = BrowseController(
        sources, settings.liveEnabled, tags=tags, screen=native_res,
        min_res=native_res if config.get("match_screen") else "any",
        hide_duplicates=settings.hideDuplicates,
    )
    detail = DetailController(browse.model, sources)
    downloads = DownloadController(config, browse.model, sources)
    lib = LibraryController(config, tags=tags)
    editor = EditorController()
    settings.dirsChanged.connect(lib.refresh)
    downloads.finished.connect(lambda *_: lib.refresh())
    editor.saved.connect(lambda *_: lib.refresh())
    app.aboutToQuit.connect(net.STOP.set)
    app.aboutToQuit.connect(downloads.cancel)
    app.aboutToQuit.connect(svwr.shutdown)
    app.aboutToQuit.connect(editor.cancel)

    def rebuild_sources():
        fresh = build_sources(config)
        browse.set_sources(fresh, settings.liveEnabled)
        detail.set_sources(fresh)
        downloads.set_sources(fresh)

    # finishSetup can change several settings at once; rebuild the sources only once.
    request_rebuild = coalesced(rebuild_sources)
    settings.sourcesChanged.connect(request_rebuild)
    settings.liveEnabledChanged.connect(request_rebuild)

    settings.matchScreenChanged.connect(lambda: browse.set_match_screen(settings.matchScreen))
    settings.hideDuplicatesChanged.connect(lambda: browse.set_hide_duplicates(settings.hideDuplicates))
    settings.hideDuplicatesChanged.connect(lib.refresh)
    svwr.checkDeps()
    svwr.checkForUpdates()
    app_update = AppUpdateController()
    app_update.check()

    engine = QQmlApplicationEngine()
    engine.addImageProvider("thumb", ThumbProvider())
    ctx = engine.rootContext()
    ctx.setContextProperty("browse", browse)
    ctx.setContextProperty("detail", detail)
    ctx.setContextProperty("downloads", downloads)
    ctx.setContextProperty("editor", editor)
    ctx.setContextProperty("library", lib)
    ctx.setContextProperty("settings", settings)
    ctx.setContextProperty("svwr", svwr)
    ctx.setContextProperty("appUpdate", app_update)
    ctx.setContextProperty("appVersion", VERSION)
    engine.setInitialProperties({"logoUrl": QUrl.fromLocalFile(str(LOGO))})
    engine.load(QUrl.fromLocalFile(str(PACKAGE_DIR / "qml" / "Main.qml")))
    if not engine.rootObjects():
        log.error("failed to load Main.qml")
        sys.exit(1)

    code = app.exec()
    # Destroy QML before the context-property controllers so bindings never see them as null.
    del engine
    if not net.shutdown([net.EXECUTOR, THUMB_EXECUTOR], QUIT_GRACE, drain=[slideshow.EXECUTOR]):
        # A worker is stuck in a network or D-Bus call; don't keep an invisible process alive for it.
        log.warning("background work still running at quit, exiting without it")
        logging.shutdown()
        os._exit(code)
    sys.exit(code)
