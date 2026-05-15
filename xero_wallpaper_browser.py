#!/usr/bin/env python3
"""Xero Wallpaper Browser & Downloader - Browse, preview and download wallpapers."""

import sys
import os

# Suppress Qt/GStreamer/OpenGL runtime warnings
os.environ["QT_LOGGING_RULES"] = (
    "qt.multimedia.gstreamer.warning=false;"
    "qt.core.qfuture.continuations.warning=false;"
    "qt.multimedia.gstreamer=false;"
    "qt.core.qfuture.continuations=false"
)
os.environ.setdefault("LIBGL_ALWAYS_SOFTWARE", "0")
# Force EGL to avoid glGetString errors on some drivers
os.environ.setdefault("QT_QPA_PLATFORM", "xcb")
os.environ.setdefault("QSG_RHI_BACKEND", "opengl")
import re
import json
import hashlib
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urljoin, urlparse, quote

import requests
from bs4 import BeautifulSoup

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QLabel, QPushButton, QComboBox, QFileDialog,
    QScrollArea, QFrame, QProgressBar, QStatusBar, QLineEdit,
    QDialog, QMessageBox, QSizePolicy, QTabWidget
)
from PyQt6.QtCore import (
    Qt, QThread, pyqtSignal, QSize, QTimer, QPoint
)
from PyQt6.QtGui import (
    QPixmap, QImage, QIcon, QPainter, QColor, QCursor, QBrush, QPen
)


HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
}

CACHE_DIR = Path.home() / ".cache" / "xero-wallpaper-browser"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

CONFIG_FILE = Path.home() / ".config" / "xero-wallpaper-browser" / "config.json"
CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)


def load_config():
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            return json.load(f)
    return {}


def save_config(cfg):
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)


def cached_download(url, session=None):
    """Download with disk caching for thumbnails."""
    url_hash = hashlib.md5(url.encode()).hexdigest()
    cache_path = CACHE_DIR / url_hash
    if cache_path.exists():
        return cache_path.read_bytes()
    try:
        s = session or requests.Session()
        r = s.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        cache_path.write_bytes(r.content)
        return r.content
    except Exception:
        return None


def bytes_to_qpixmap(data, size=None):
    """Convert image bytes to QPixmap, optionally scaled."""
    if not data:
        return None
    img = QImage()
    if img.loadFromData(data):
        px = QPixmap.fromImage(img)
        if size:
            px = px.scaled(size, Qt.AspectRatioMode.KeepAspectRatio,
                           Qt.TransformationMode.SmoothTransformation)
        return px
    return None


# ---------------------------------------------------------------------------
# Source Scrapers
# ---------------------------------------------------------------------------

class WallpaperSource:
    name = ""
    url = ""
    source_type = "static"  # or "live"

    def fetch_wallpapers(self, page=1, search=""):
        """Return list of dicts: {thumb_url, full_url, title, resolution}"""
        raise NotImplementedError


class WallhavenSource(WallpaperSource):
    name = "Wallhaven"
    url = "https://wallhaven.cc"
    source_type = "static"

    def fetch_wallpapers(self, page=1, search=""):
        try:
            params = {"page": page, "purity": "100", "sorting": "favorites", "order": "desc"}
            if search:
                params["q"] = search
            api = "https://wallhaven.cc/api/v1/search"
            r = requests.get(api, params=params, headers=HEADERS, timeout=15)
            r.raise_for_status()
            data = r.json()
            results = []
            for item in data.get("data", []):
                results.append({
                    "thumb_url": item.get("thumbs", {}).get("small", ""),
                    "full_url": item.get("path", ""),
                    "title": item.get("id", "wallhaven"),
                    "resolution": item.get("resolution", ""),
                })
            return results
        except Exception as e:
            print(f"Wallhaven error: {e}")
            return []


class FourKWallpapersSource(WallpaperSource):
    name = "4K Wallpapers"
    url = "https://4kwallpapers.com"
    source_type = "static"

    def fetch_wallpapers(self, page=1, search=""):
        try:
            if search:
                query = search.strip().replace(" ", "-")
                url = f"https://4kwallpapers.com/search/?q={quote(query)}&text={quote(search)}"
                if page > 1:
                    url += f"&page={page}"
            else:
                url = "https://4kwallpapers.com/most-popular-4k-wallpapers/"
                if page > 1:
                    url += f"?page={page}"
            r = requests.get(url, headers=HEADERS, timeout=15)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")
            results = []
            for item in soup.select("p.wallpapers__item"):
                link = item.select_one("a.wallpapers__canvas_image")
                img = item.select_one("img[itemprop='thumbnail']")
                if not link or not img:
                    continue
                page_url = link.get("href", "")
                if page_url and not page_url.startswith("http"):
                    page_url = urljoin("https://4kwallpapers.com", page_url)
                # Use 2x thumbnail for better quality
                srcset = img.get("srcset", "")
                thumb = ""
                if srcset:
                    thumb = srcset.split()[0]
                if not thumb:
                    thumb = img.get("src", "")
                if thumb and not thumb.startswith("http"):
                    thumb = urljoin("https://4kwallpapers.com", thumb)
                title = img.get("alt", "4K Wallpaper")
                results.append({
                    "thumb_url": thumb,
                    "full_url": page_url,
                    "title": title,
                    "resolution": "",
                    "page_url": page_url,
                    "needs_resolve": True,
                })
            return results
        except Exception as e:
            print(f"4KWallpapers error: {e}")
            return []

    def resolve_download_url(self, page_url):
        """Get the highest resolution download link from the detail page."""
        try:
            r = requests.get(page_url, headers=HEADERS, timeout=15)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")
            # Find download links — prefer 3840x2160, then largest available
            best_url = ""
            best_pixels = 0
            for a in soup.select("a[href*='/images/wallpapers/']"):
                href = a.get("href", "")
                if not href:
                    continue
                if not href.startswith("http"):
                    href = urljoin("https://4kwallpapers.com", href)
                # Extract resolution from URL like slug-3840x2160-ID.jpg
                m = re.search(r'(\d{3,5})x(\d{3,5})', href)
                if m:
                    pixels = int(m.group(1)) * int(m.group(2))
                    if pixels > best_pixels:
                        best_pixels = pixels
                        best_url = href
            if best_url:
                return best_url
        except Exception as e:
            print(f"4KWallpapers resolve error: {e}")
        return page_url


class MoeWallsSource(WallpaperSource):
    name = "MoeWalls"
    url = "https://moewalls.com"
    source_type = "live"

    def fetch_wallpapers(self, page=1, search=""):
        try:
            if search:
                url = f"https://moewalls.com/page/{page}/?s={quote(search)}"
            else:
                url = f"https://moewalls.com/page/{page}/"
            r = requests.get(url, headers=HEADERS, timeout=15)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")
            results = []
            for article in soup.select("article"):
                link = article.select_one("a")
                img = article.select_one("img")
                if not link or not img:
                    continue
                page_url = link.get("href", "")
                thumb = img.get("src") or img.get("data-src") or ""
                if not thumb.startswith("http") and thumb:
                    thumb = urljoin("https://moewalls.com", thumb)
                title = img.get("alt", "Live Wallpaper")
                results.append({
                    "thumb_url": thumb,
                    "full_url": page_url,
                    "title": title,
                    "resolution": "",
                    "page_url": page_url,
                    "needs_resolve": True,
                })
            return results
        except Exception as e:
            print(f"MoeWalls error: {e}")
            return []

    def resolve_download_url(self, page_url):
        """Get the actual video download link from a detail page."""
        try:
            r = requests.get(page_url, headers=HEADERS, timeout=15)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")
            video = soup.select_one("video source")
            if video and video.get("src"):
                src = video["src"]
                if not src.startswith("http"):
                    src = urljoin(page_url, src)
                return src
            for a in soup.select("a[href]"):
                href = a["href"]
                if any(ext in href.lower() for ext in (".mp4", ".webm")):
                    if not href.startswith("http"):
                        href = urljoin(page_url, href)
                    return href
        except Exception as e:
            print(f"MoeWalls resolve error: {e}")
        return page_url


class MotionBGsSource(WallpaperSource):
    name = "MotionBGs"
    url = "https://motionbgs.com"
    source_type = "live"

    def fetch_wallpapers(self, page=1, search=""):
        try:
            if search:
                url = f"https://motionbgs.com/{page}/?s={quote(search)}"
            else:
                url = f"https://motionbgs.com/{page}/" if page > 1 else "https://motionbgs.com/"
            r = requests.get(url, headers=HEADERS, timeout=15)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")
            results = []
            # MotionBGs uses <a> tags with <img> children for cards
            for link in soup.select("a[href]"):
                img = link.select_one("img")
                if not img:
                    continue
                thumb = img.get("src") or img.get("data-src") or ""
                # Thumbnails are at /i/c/364x205/media/{ID}/...
                if "/media/" not in thumb and "/i/" not in thumb:
                    continue
                if thumb and not thumb.startswith("http"):
                    thumb = urljoin("https://motionbgs.com", thumb)
                page_url = link.get("href", "")
                if not page_url.startswith("http"):
                    page_url = urljoin("https://motionbgs.com", page_url)
                title = img.get("alt", "") or link.get_text(strip=True) or "Live Wallpaper"
                # Extract media ID from thumbnail path for download
                media_id = ""
                m = re.search(r'/media/(\d+)/', thumb)
                if m:
                    media_id = m.group(1)
                results.append({
                    "thumb_url": thumb,
                    "full_url": page_url,
                    "title": title,
                    "resolution": "",
                    "page_url": page_url,
                    "media_id": media_id,
                    "needs_resolve": True,
                })
            return results
        except Exception as e:
            print(f"MotionBGs error: {e}")
            return []

    def resolve_download_url(self, page_url, media_id=""):
        # Direct download via /dl/4k/{ID} or /dl/hd/{ID}
        if media_id:
            return f"https://motionbgs.com/dl/4k/{media_id}"
        # Fallback: visit detail page to extract ID
        try:
            r = requests.get(page_url, headers=HEADERS, timeout=15)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")
            for a in soup.select("a[href*='/dl/']"):
                href = a["href"]
                if not href.startswith("http"):
                    href = urljoin("https://motionbgs.com", href)
                return href
        except Exception as e:
            print(f"MotionBGs resolve error: {e}")
        return page_url


STATIC_SOURCES = [WallhavenSource(), FourKWallpapersSource()]
LIVE_SOURCES = [MoeWallsSource(), MotionBGsSource()]


# ---------------------------------------------------------------------------
# Worker Threads
# ---------------------------------------------------------------------------

class FetchWorker(QThread):
    finished = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, source, page=1, search=""):
        super().__init__()
        self.source = source
        self.page = page
        self.search = search

    def run(self):
        try:
            results = self.source.fetch_wallpapers(self.page, self.search)
            self.finished.emit(results)
        except Exception as e:
            self.error.emit(str(e))


class ThumbnailWorker(QThread):
    thumbnail_ready = pyqtSignal(int, QPixmap)

    def __init__(self, index, url, size):
        super().__init__()
        self.index = index
        self.url = url
        self.size = size
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        if self._cancelled:
            return
        data = cached_download(self.url)
        if self._cancelled or not data:
            return
        px = bytes_to_qpixmap(data, self.size)
        if px and not self._cancelled:
            self.thumbnail_ready.emit(self.index, px)


class LocalThumbnailWorker(QThread):
    thumbnail_ready = pyqtSignal(int, QPixmap)

    def __init__(self, index, filepath, size):
        super().__init__()
        self.index = index
        self.filepath = filepath
        self.size = size
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        if self._cancelled:
            return
        try:
            img = QImage(self.filepath)
            if not img.isNull() and not self._cancelled:
                px = QPixmap.fromImage(img)
                if self.size:
                    px = px.scaled(self.size, Qt.AspectRatioMode.KeepAspectRatio,
                                   Qt.TransformationMode.SmoothTransformation)
                if not self._cancelled:
                    self.thumbnail_ready.emit(self.index, px)
        except Exception:
            pass


class VideoThumbnailWorker(QThread):
    thumbnail_ready = pyqtSignal(int, QPixmap)

    def __init__(self, index, filepath, size):
        super().__init__()
        self.index = index
        self.filepath = filepath
        self.size = size
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        if self._cancelled:
            return
        try:
            result = subprocess.run(
                ["ffmpeg", "-ss", "00:00:02", "-i", self.filepath,
                 "-vframes", "1", "-f", "image2", "-vcodec", "png", "pipe:1"],
                capture_output=True, timeout=15
            )
            if not result.stdout or self._cancelled:
                return
            px = bytes_to_qpixmap(result.stdout, self.size)
            if not px or self._cancelled:
                return
            painter = QPainter(px)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            cx, cy = px.width() // 2, px.height() // 2
            painter.setBrush(QBrush(QColor(0, 0, 0, 140)))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(QPoint(cx, cy), 22, 22)
            painter.setBrush(QBrush(QColor(255, 255, 255, 220)))
            triangle = [QPoint(cx - 8, cy - 12), QPoint(cx - 8, cy + 12), QPoint(cx + 14, cy)]
            painter.drawPolygon(triangle)
            painter.end()
            if not self._cancelled:
                self.thumbnail_ready.emit(self.index, px)
        except Exception:
            pass



class DownloadWorker(QThread):
    progress = pyqtSignal(int, int)  # current, total
    file_done = pyqtSignal(str)
    all_done = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, items, dest_dir, source=None):
        super().__init__()
        self.items = items
        self.dest_dir = dest_dir
        self.source = source
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        total = len(self.items)
        for i, item in enumerate(self.items):
            if self._cancelled:
                break
            try:
                url = item["full_url"]
                if item.get("needs_resolve") and self.source and hasattr(self.source, "resolve_download_url"):
                    if isinstance(self.source, MotionBGsSource):
                        url = self.source.resolve_download_url(
                            item.get("page_url", url), item.get("media_id", ""))
                    else:
                        url = self.source.resolve_download_url(item.get("page_url", url))

                r = requests.get(url, headers=HEADERS, timeout=60, stream=True)
                r.raise_for_status()

                content_type = r.headers.get("content-type", "")
                ext = Path(urlparse(url).path).suffix
                if not ext or len(ext) > 6:
                    if "video" in content_type or "mp4" in content_type:
                        ext = ".mp4"
                    elif "webm" in content_type:
                        ext = ".webm"
                    elif "png" in content_type:
                        ext = ".png"
                    elif "webp" in content_type:
                        ext = ".webp"
                    else:
                        ext = ".jpg"

                safe_title = re.sub(r'[^\w\-.]', '_', item.get("title", f"wallpaper_{i}"))
                if not safe_title.lower().endswith(ext.lower()):
                    safe_title += ext
                filepath = os.path.join(self.dest_dir, safe_title)

                # Avoid overwriting
                base, extension = os.path.splitext(filepath)
                counter = 1
                while os.path.exists(filepath):
                    filepath = f"{base}_{counter}{extension}"
                    counter += 1

                with open(filepath, "wb") as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if self._cancelled:
                            break
                        f.write(chunk)

                self.file_done.emit(filepath)
            except Exception as e:
                self.error.emit(f"Failed: {item.get('title', '?')} - {e}")

            self.progress.emit(i + 1, total)

        self.all_done.emit()


# ---------------------------------------------------------------------------
# Wallpaper Card Widget
# ---------------------------------------------------------------------------

class WallpaperCard(QFrame):
    clicked = pyqtSignal(int)
    double_clicked = pyqtSignal(int)

    def __init__(self, index, title="", resolution="", parent=None):
        super().__init__(parent)
        self.index = index
        self.selected = False
        self.setFixedSize(220, 195)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setProperty("class", "wallpaper-card")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        self.thumb_label = QLabel()
        self.thumb_label.setFixedSize(208, 140)
        self.thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumb_label.setStyleSheet("background: rgba(0,0,0,0.2); border-radius: 6px;")
        self.thumb_label.setText("Loading...")
        layout.addWidget(self.thumb_label)

        self.title_label = QLabel(title[:30] + "..." if len(title) > 30 else title)
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_label.setToolTip(title)
        font = self.title_label.font()
        font.setPointSize(9)
        self.title_label.setFont(font)
        layout.addWidget(self.title_label)

        if resolution:
            res_label = QLabel(resolution)
            res_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            font2 = res_label.font()
            font2.setPointSize(8)
            res_label.setFont(font2)
            res_label.setStyleSheet("color: gray;")
            layout.addWidget(res_label)

        self._update_style()

    def set_thumbnail(self, pixmap):
        self.thumb_label.setPixmap(pixmap)
        self.thumb_label.setText("")

    def set_selected(self, selected):
        self.selected = selected
        self._update_style()

    def _update_style(self):
        if self.selected:
            self.setStyleSheet("""
                WallpaperCard {
                    border: 2px solid #5b8bd4;
                    border-radius: 8px;
                    background: rgba(91, 139, 212, 0.15);
                }
            """)
        else:
            self.setStyleSheet("""
                WallpaperCard {
                    border: 1px solid rgba(128, 128, 128, 0.3);
                    border-radius: 8px;
                    background: rgba(0, 0, 0, 0.05);
                }
                WallpaperCard:hover {
                    border: 1px solid rgba(91, 139, 212, 0.5);
                    background: rgba(91, 139, 212, 0.08);
                }
            """)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.index)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit(self.index)
        super().mouseDoubleClickEvent(event)


# ---------------------------------------------------------------------------
# Preview Dialog
# ---------------------------------------------------------------------------

class PreviewDialog(QDialog):
    def __init__(self, item, parent=None):
        super().__init__(parent)
        self.setWindowTitle(item.get("title", "Preview"))
        self.setMinimumSize(800, 600)
        self.item = item
        self._load_thread = None

        layout = QVBoxLayout(self)

        self.image_label = QLabel("Loading preview...")
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self.image_label)

        info = QLabel(f"{item.get('title', '')}  |  {item.get('resolution', '')}")
        info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(info)

        btn_layout = QHBoxLayout()
        dl_btn = QPushButton("Download This")
        dl_btn.clicked.connect(self.accept)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.reject)
        btn_layout.addStretch()
        btn_layout.addWidget(dl_btn)
        btn_layout.addWidget(close_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # Show cached thumbnail immediately while full-res loads
        thumb_url = item.get("thumb_url", "")
        if thumb_url:
            thumb_hash = hashlib.md5(thumb_url.encode()).hexdigest()
            cache_path = CACHE_DIR / thumb_hash
            if cache_path.exists():
                px = bytes_to_qpixmap(cache_path.read_bytes(), QSize(1200, 900))
                if px:
                    self.image_label.setPixmap(px)
                    self.image_label.setText("")

        self._load_thread = ThumbnailWorker(0, item["full_url"], QSize(1200, 900))
        self._load_thread.thumbnail_ready.connect(self._on_loaded)
        self._load_thread.start()

    def _on_loaded(self, _, pixmap):
        if not self.isVisible():
            return
        self.image_label.setPixmap(pixmap.scaled(
            self.image_label.size().expandedTo(QSize(400, 300)),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        ))

    def closeEvent(self, event):
        if self._load_thread and self._load_thread.isRunning():
            self._load_thread.cancel()
            self._load_thread.wait(2000)
        super().closeEvent(event)


class LocalPreviewDialog(QDialog):
    """Preview a local image file with option to set as wallpaper."""

    def __init__(self, filepath, parent=None):
        super().__init__(parent)
        self.filepath = filepath
        self.setWindowTitle(os.path.basename(filepath))
        self.setMinimumSize(900, 650)
        self.resize(1000, 720)

        layout = QVBoxLayout(self)

        self.image_label = QLabel("Loading...")
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self.image_label)

        info = QLabel(os.path.basename(filepath))
        info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(info)

        btn_layout = QHBoxLayout()
        set_btn = QPushButton("Set as Wallpaper")
        set_btn.setStyleSheet(
            "QPushButton { background-color: #5b8bd4; color: white; border: none;"
            " padding: 6px 16px; border-radius: 4px; font-weight: bold; }"
            "QPushButton:hover { background-color: #4a7bc3; }"
        )
        set_btn.clicked.connect(self.accept)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.reject)
        btn_layout.addStretch()
        btn_layout.addWidget(set_btn)
        btn_layout.addWidget(close_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        self._img_worker = LocalThumbnailWorker(0, self.filepath, QSize(1100, 800))
        self._img_worker.thumbnail_ready.connect(self._on_loaded)
        self._img_worker.start()

    def _on_loaded(self, _, px):
        if self.isVisible():
            self.image_label.setPixmap(px)
            self.image_label.setText("")

    def closeEvent(self, event):
        if self._img_worker.isRunning():
            self._img_worker.cancel()
            self._img_worker.wait(1000)
        super().closeEvent(event)


# ---------------------------------------------------------------------------
# Local Browser Dialog (tabbed: Static / Live)
# ---------------------------------------------------------------------------

class LocalBrowserTab(QWidget):
    """A single tab for browsing local wallpapers of one type."""

    _MAX_CONCURRENT = 4

    def __init__(self, folder, file_type, parent_dialog, parent=None):
        super().__init__(parent)
        self.folder = folder
        self.file_type = file_type
        self.parent_dialog = parent_dialog
        self.thumb_workers = []
        self._pending_workers = []
        self._active_count = 0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        if not folder or not os.path.isdir(folder):
            info = QLabel(f"No {'static' if file_type == 'static' else 'live'} wallpapers folder set.\n"
                          "Set it in the main window first.")
            info.setAlignment(Qt.AlignmentFlag.AlignCenter)
            info.setStyleSheet("color: #e8a035; font-weight: bold; font-size: 13px; padding: 40px;")
            layout.addWidget(info)
            return

        path_label = QLabel(f"Folder: {folder}")
        path_label.setStyleSheet("color: gray; font-size: 10px;")
        layout.addWidget(path_label)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        grid_widget = QWidget()
        self.grid_layout = QGridLayout(grid_widget)
        self.grid_layout.setSpacing(10)
        self.grid_layout.setContentsMargins(5, 5, 5, 5)
        scroll.setWidget(grid_widget)
        layout.addWidget(scroll, stretch=1)

        self._load_files(scroll)

    def _load_files(self, scroll):
        if self.file_type == "static":
            exts = (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif")
        else:
            exts = (".mp4", ".webm", ".mkv", ".avi", ".gif", ".jpg", ".jpeg", ".png", ".webp")

        files = []
        for f in sorted(os.listdir(self.folder)):
            if f.lower().endswith(exts):
                files.append(os.path.join(self.folder, f))

        if not files:
            empty = QLabel("No wallpapers found in this folder.\nDownload some first!")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setStyleSheet("color: white; font-weight: bold; padding: 40px; font-size: 13px;")
            self.grid_layout.addWidget(empty, 0, 0)
            return

        cols = 4

        for i, filepath in enumerate(files):
            fname = os.path.basename(filepath)
            card = WallpaperCard(i, fname, "")
            card.double_clicked.connect(lambda idx, fp=filepath: self._on_double_click(fp))
            row, col = divmod(i, cols)
            self.grid_layout.addWidget(card, row, col)

            is_image = any(filepath.lower().endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"))
            is_video = any(filepath.lower().endswith(ext) for ext in (".mp4", ".webm", ".mkv", ".avi"))
            if is_image:
                worker = LocalThumbnailWorker(i, filepath, QSize(208, 140))
                worker.thumbnail_ready.connect(self._set_thumb)
                self._pending_workers.append(worker)
            elif is_video:
                worker = VideoThumbnailWorker(i, filepath, QSize(208, 140))
                worker.thumbnail_ready.connect(self._set_thumb)
                self._pending_workers.append(worker)

        self._drain_queue()

    def _drain_queue(self):
        while self._active_count < self._MAX_CONCURRENT and self._pending_workers:
            worker = self._pending_workers.pop(0)
            self.thumb_workers.append(worker)
            worker.finished.connect(self._on_worker_finished)
            self._active_count += 1
            worker.start()

    def _on_worker_finished(self):
        self._active_count = max(0, self._active_count - 1)
        self._drain_queue()

    def _set_thumb(self, index, pixmap):
        for i in range(self.grid_layout.count()):
            widget = self.grid_layout.itemAt(i).widget()
            if isinstance(widget, WallpaperCard) and widget.index == index:
                widget.set_thumbnail(pixmap)
                break

    def cancel_all_workers(self):
        for w in self._pending_workers:
            w.cancel()
        self._pending_workers.clear()
        for w in self.thumb_workers:
            w.cancel()

    def _on_double_click(self, filepath):
        is_video = filepath.lower().endswith((".mp4", ".webm", ".mkv", ".avi"))
        if is_video:
            for player in ["mpv", "vlc", "celluloid", "totem", "xdg-open"]:
                if shutil.which(player):
                    if player == "mpv":
                        cmd = ["mpv", "--geometry=1280x720", "--autofit=1280x720",
                               "--title=Live Wallpaper Preview", "--loop=inf", filepath]
                    elif player == "vlc":
                        cmd = ["vlc", "--width=1280", "--height=720", filepath]
                    else:
                        cmd = [player, filepath]
                    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    return
            QMessageBox.information(self, "No Player Found",
                                    f"No video player found (tried mpv, vlc, celluloid, totem).\n\nFile:\n{filepath}")
            return
        dlg = LocalPreviewDialog(filepath, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.parent_dialog.set_wallpaper(filepath)


class LocalBrowserDialog(QDialog):
    """Tabbed dialog for browsing downloaded wallpapers."""

    def __init__(self, static_dir, live_dir, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Browse Downloaded Wallpapers")
        self.setMinimumSize(1000, 650)
        self.resize(1100, 700)
        self.main_window = parent

        layout = QVBoxLayout(self)

        # Tabs
        self.tabs = QTabWidget()
        self.tabs.addTab(LocalBrowserTab(static_dir, "static", self), "🖼  Static Wallpapers")
        self.tabs.addTab(LocalBrowserTab(live_dir, "live", self), "🎬  Live Wallpapers")
        layout.addWidget(self.tabs)

        hint = QLabel("Double-click to preview  |  Images: preview & set as wallpaper  |  Videos: play inline with controls")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet("color: #e8a035; font-size: 11px; font-weight: bold; padding: 4px;")
        layout.addWidget(hint)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.reject)
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(close_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

    def closeEvent(self, event):
        for i in range(self.tabs.count()):
            tab = self.tabs.widget(i)
            if isinstance(tab, LocalBrowserTab):
                tab.cancel_all_workers()
        super().closeEvent(event)

    def set_wallpaper(self, filepath):
        if self.main_window and hasattr(self.main_window, "_set_wallpaper"):
            self.main_window._set_wallpaper(filepath)


# ---------------------------------------------------------------------------
# Main Window
# ---------------------------------------------------------------------------

class XeroWallpaperBrowser(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Xero Wallpaper Browser & Downloader")
        self.setMinimumSize(1000, 700)
        self.resize(1200, 800)

        # Load logo
        logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "xero_logo.png")
        if os.path.exists(logo_path):
            self.setWindowIcon(QIcon(logo_path))

        self.config = load_config()
        self.wallpapers = []
        self.selected_indices = set()
        self.current_page = 1
        self.current_source = None
        self.thumb_workers = []
        self.fetch_worker = None
        self.download_worker = None

        self._build_ui()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(8)

        # Header
        header = QHBoxLayout()
        logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "xero_logo.png")
        if os.path.exists(logo_path):
            logo_label = QLabel()
            logo_px = QPixmap(logo_path).scaled(
                QSize(40, 40), Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            logo_label.setPixmap(logo_px)
            header.addWidget(logo_label)

        title_label = QLabel("Xero Wallpaper Browser & Downloader")
        title_font = title_label.font()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title_label.setFont(title_font)
        header.addWidget(title_label)
        header.addStretch()

        main_layout.addLayout(header)

        # Download directory buttons row
        dir_row = QHBoxLayout()

        self.static_dir_btn = QPushButton("📁 Static Wallpapers Folder")
        self.static_dir_btn.clicked.connect(lambda: self._choose_download_dir("static"))
        dir_row.addWidget(self.static_dir_btn)

        self.static_dir_label = QLabel()
        self.static_dir_label.setStyleSheet("color: gray; font-size: 10px;")
        dir_row.addWidget(self.static_dir_label, stretch=1)

        dir_row.addSpacing(20)

        self.live_dir_btn = QPushButton("📁 Live Wallpapers Folder")
        self.live_dir_btn.clicked.connect(lambda: self._choose_download_dir("live"))
        dir_row.addWidget(self.live_dir_btn)

        self.live_dir_label = QLabel()
        self.live_dir_label.setStyleSheet("color: gray; font-size: 10px;")
        dir_row.addWidget(self.live_dir_label, stretch=1)

        main_layout.addLayout(dir_row)
        self._update_dir_labels()

        # Source selection row
        source_row = QHBoxLayout()

        source_row.addWidget(QLabel("Static Wallpapers:"))
        self.static_combo = QComboBox()
        self.static_combo.setMinimumWidth(180)
        for src in STATIC_SOURCES:
            self.static_combo.addItem(src.name, src)
        self.static_combo.setCurrentIndex(-1)
        self.static_combo.setPlaceholderText("Select a source...")
        self.static_combo.currentIndexChanged.connect(lambda: self._on_source_changed("static"))
        source_row.addWidget(self.static_combo)

        source_row.addSpacing(20)

        source_row.addWidget(QLabel("Live Wallpapers:"))
        self.live_combo = QComboBox()
        self.live_combo.setMinimumWidth(180)
        for src in LIVE_SOURCES:
            self.live_combo.addItem(src.name, src)
        self.live_combo.setCurrentIndex(-1)
        self.live_combo.setPlaceholderText("Select a source...")
        self.live_combo.currentIndexChanged.connect(lambda: self._on_source_changed("live"))
        source_row.addWidget(self.live_combo)

        source_row.addSpacing(20)

        self.browse_local_btn = QPushButton("📂 Browse Downloaded")
        self.browse_local_btn.clicked.connect(self._open_local_browser)
        source_row.addWidget(self.browse_local_btn)

        source_row.addStretch()
        main_layout.addLayout(source_row)

        # Orange glowing note
        note_label = QLabel("⚡ Images may take a while to load depending on connection speed and source availability")
        note_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        note_label.setStyleSheet("""
            QLabel {
                color: #e8a035;
                font-size: 11px;
                font-weight: bold;
                padding: 2px 0;
            }
        """)
        main_layout.addWidget(note_label)

        # Search & controls row
        controls = QHBoxLayout()

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search wallpapers...")
        self.search_input.setMinimumWidth(250)
        self.search_input.returnPressed.connect(self._do_search)
        controls.addWidget(self.search_input)

        search_btn = QPushButton("Search")
        search_btn.clicked.connect(self._do_search)
        controls.addWidget(search_btn)

        controls.addSpacing(15)

        self.select_all_btn = QPushButton("Select All")
        self.select_all_btn.clicked.connect(self._toggle_select_all)
        controls.addWidget(self.select_all_btn)

        self.download_btn = QPushButton("⬇ Download Selected")
        self.download_btn.clicked.connect(self._download_selected)
        self.download_btn.setEnabled(False)
        self.download_btn.setStyleSheet("""
            QPushButton {
                background-color: #5b8bd4;
                color: white;
                border: none;
                padding: 6px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #4a7bc3; }
            QPushButton:disabled { background-color: #888; }
        """)
        controls.addWidget(self.download_btn)

        self.sel_count_label = QLabel("0 selected")
        controls.addWidget(self.sel_count_label)

        controls.addStretch()
        main_layout.addLayout(controls)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setTextVisible(True)
        main_layout.addWidget(self.progress_bar)

        # Scroll area for wallpaper grid
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.grid_widget = QWidget()
        self.grid_layout = QGridLayout(self.grid_widget)
        self.grid_layout.setSpacing(10)
        self.grid_layout.setContentsMargins(5, 5, 5, 5)
        self.scroll.setWidget(self.grid_widget)
        main_layout.addWidget(self.scroll, stretch=1)

        # Pagination
        page_row = QHBoxLayout()
        self.prev_btn = QPushButton("← Previous")
        self.prev_btn.clicked.connect(self._prev_page)
        self.prev_btn.setEnabled(False)
        page_row.addWidget(self.prev_btn)

        self.page_label = QLabel("Page 1")
        self.page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        page_row.addWidget(self.page_label)

        self.next_btn = QPushButton("Next →")
        self.next_btn.clicked.connect(self._next_page)
        self.next_btn.setEnabled(False)
        page_row.addWidget(self.next_btn)
        main_layout.addLayout(page_row)

        credit_label = QLabel('App Created by <a href="https://xerolinux.xyz/" style="color: #7aa2f7; text-decoration: none;"><b>DarkXero</b></a>')
        credit_label.setOpenExternalLinks(True)
        credit_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        credit_label.setStyleSheet("font-size: 11px; padding: 4px 0;")
        main_layout.addWidget(credit_label)

        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Set your download folders and select a source to begin.")
        hint_label = QLabel("Tip: Ctrl+Click to select multiple wallpapers")
        hint_label.setStyleSheet("color: gray; font-size: 11px; padding-right: 6px;")
        self.status_bar.addPermanentWidget(hint_label)

        # Welcome message in grid
        welcome = QLabel(
            "Welcome! To get started:\n\n"
            "1. Set your download folders for Static and/or Live wallpapers above\n"
            "2. Select a wallpaper source from the dropdowns\n"
            "3. Browse, select and download!\n\n"
            "You can also browse your downloaded wallpapers using the\n"
            "\"Browse Local\" buttons below the source dropdowns."
        )
        welcome.setAlignment(Qt.AlignmentFlag.AlignCenter)
        welcome.setStyleSheet("font-size: 14px; color: white; font-weight: bold; padding: 60px;")
        self.grid_layout.addWidget(welcome, 0, 0)

    def _choose_download_dir(self, dir_type):
        key = "static_download_dir" if dir_type == "static" else "live_download_dir"
        default = str(Path.home() / "Pictures" / ("Wallpapers" if dir_type == "static" else "Live Wallpapers"))
        current = self.config.get(key, default)
        label = "Static Wallpapers" if dir_type == "static" else "Live Wallpapers"
        d = QFileDialog.getExistingDirectory(self, f"Choose {label} Download Folder", current)
        if d:
            self.config[key] = d
            save_config(self.config)
            self._update_dir_labels()
            self.status_bar.showMessage(f"{label} folder: {d}")

    def _update_dir_labels(self):
        for key, label_widget, desc in [
            ("static_download_dir", self.static_dir_label, "Static"),
            ("live_download_dir", self.live_dir_label, "Live"),
        ]:
            d = self.config.get(key)
            if d:
                label_widget.setText(d)
                label_widget.setStyleSheet("color: gray; font-size: 10px;")
            else:
                label_widget.setText(f"Not set — click to choose {desc} wallpapers folder")
                label_widget.setStyleSheet("color: #e8a035; font-size: 10px; font-weight: bold;")

    def _on_source_changed(self, stype):
        if stype == "static":
            idx = self.static_combo.currentIndex()
            if idx >= 0:
                self.current_source = self.static_combo.itemData(idx)
                self.live_combo.blockSignals(True)
                self.live_combo.setCurrentIndex(-1)
                self.live_combo.blockSignals(False)
        else:
            idx = self.live_combo.currentIndex()
            if idx >= 0:
                self.current_source = self.live_combo.itemData(idx)
                self.static_combo.blockSignals(True)
                self.static_combo.setCurrentIndex(-1)
                self.static_combo.blockSignals(False)

        self.current_page = 1
        self._fetch_wallpapers()

    def _do_search(self):
        if self.current_source:
            self.current_page = 1
            self._fetch_wallpapers()
        else:
            self.status_bar.showMessage("Please select a source first.")

    def _fetch_wallpapers(self):
        if not self.current_source:
            return

        self.status_bar.showMessage(f"Fetching from {self.current_source.name}...")
        self.selected_indices.clear()
        self._update_selection_ui()

        for w in self.thumb_workers:
            w.cancel()
        self.thumb_workers.clear()

        self.fetch_worker = FetchWorker(
            self.current_source, self.current_page, self.search_input.text().strip()
        )
        self.fetch_worker.finished.connect(self._on_wallpapers_fetched)
        self.fetch_worker.error.connect(lambda e: self.status_bar.showMessage(f"Error: {e}"))
        self.fetch_worker.start()

    def _on_wallpapers_fetched(self, wallpapers):
        self.wallpapers = wallpapers
        self._populate_grid()
        count = len(wallpapers)
        self.status_bar.showMessage(
            f"Found {count} wallpapers from {self.current_source.name} (Page {self.current_page})"
        )
        self.page_label.setText(f"Page {self.current_page}")
        self.prev_btn.setEnabled(self.current_page > 1)
        self.next_btn.setEnabled(count > 0)

    def _populate_grid(self):
        # Clear grid
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self.wallpapers:
            empty = QLabel("No wallpapers found. Try a different search or source.")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setStyleSheet("color: gray; padding: 60px; font-size: 13px;")
            self.grid_layout.addWidget(empty, 0, 0)
            return

        cols = max(1, (self.scroll.viewport().width() - 20) // 230)

        for i, wp in enumerate(self.wallpapers):
            card = WallpaperCard(i, wp.get("title", ""), wp.get("resolution", ""))
            card.clicked.connect(self._on_card_clicked)
            card.double_clicked.connect(self._on_card_double_clicked)
            row, col = divmod(i, cols)
            self.grid_layout.addWidget(card, row, col)

            # Load thumbnail
            if wp.get("thumb_url"):
                worker = ThumbnailWorker(i, wp["thumb_url"], QSize(208, 140))
                worker.thumbnail_ready.connect(self._on_thumbnail_ready)
                self.thumb_workers.append(worker)
                worker.start()

    def _on_thumbnail_ready(self, index, pixmap):
        # Find the card at this index
        for i in range(self.grid_layout.count()):
            widget = self.grid_layout.itemAt(i).widget()
            if isinstance(widget, WallpaperCard) and widget.index == index:
                widget.set_thumbnail(pixmap)
                break

    def _on_card_clicked(self, index):
        modifiers = QApplication.keyboardModifiers()
        if modifiers & Qt.KeyboardModifier.ControlModifier:
            # Toggle selection
            if index in self.selected_indices:
                self.selected_indices.discard(index)
            else:
                self.selected_indices.add(index)
        elif modifiers & Qt.KeyboardModifier.ShiftModifier:
            # Range select
            if self.selected_indices:
                last = max(self.selected_indices)
                start, end = min(last, index), max(last, index)
                for i in range(start, end + 1):
                    self.selected_indices.add(i)
            else:
                self.selected_indices.add(index)
        else:
            # Single select toggle
            if index in self.selected_indices and len(self.selected_indices) == 1:
                self.selected_indices.clear()
            else:
                self.selected_indices = {index}

        self._update_card_selections()
        self._update_selection_ui()

    def _on_card_double_clicked(self, index):
        if 0 <= index < len(self.wallpapers):
            item = self.wallpapers[index]
            if not item.get("needs_resolve"):
                dlg = PreviewDialog(item, self)
                if dlg.exec() == QDialog.DialogCode.Accepted:
                    self.selected_indices = {index}
                    self._update_card_selections()
                    self._update_selection_ui()
                    self._download_selected()
            else:
                self.selected_indices = {index}
                self._update_card_selections()
                self._update_selection_ui()
                self.status_bar.showMessage("Selected — click ⬇ Download to save.")

    def _update_card_selections(self):
        for i in range(self.grid_layout.count()):
            widget = self.grid_layout.itemAt(i).widget()
            if isinstance(widget, WallpaperCard):
                widget.set_selected(widget.index in self.selected_indices)

    def _update_selection_ui(self):
        count = len(self.selected_indices)
        self.sel_count_label.setText(f"{count} selected")
        self.download_btn.setEnabled(count > 0)

    def _toggle_select_all(self):
        if len(self.selected_indices) == len(self.wallpapers):
            self.selected_indices.clear()
            self.select_all_btn.setText("Select All")
        else:
            self.selected_indices = set(range(len(self.wallpapers)))
            self.select_all_btn.setText("Deselect All")
        self._update_card_selections()
        self._update_selection_ui()

    def _download_selected(self):
        if not self.selected_indices:
            return

        is_live = self.current_source and self.current_source.source_type == "live"
        dir_key = "live_download_dir" if is_live else "static_download_dir"
        dir_type = "live" if is_live else "static"

        dest = self.config.get(dir_key)
        if not dest:
            self._choose_download_dir(dir_type)
            dest = self.config.get(dir_key)
            if not dest:
                return

        os.makedirs(dest, exist_ok=True)

        items = [self.wallpapers[i] for i in sorted(self.selected_indices)]
        total = len(items)

        self.progress_bar.setVisible(True)
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat(f"Downloading... 0/{total}")
        self.download_btn.setEnabled(False)

        self.download_worker = DownloadWorker(items, dest, self.current_source)
        self.download_worker.progress.connect(self._on_download_progress)
        self.download_worker.file_done.connect(
            lambda f: self.status_bar.showMessage(f"Downloaded: {os.path.basename(f)}")
        )
        self.download_worker.error.connect(lambda e: self.status_bar.showMessage(e))
        self.download_worker.all_done.connect(self._on_downloads_complete)
        self.download_worker.start()

    def _on_download_progress(self, current, total):
        self.progress_bar.setValue(current)
        self.progress_bar.setFormat(f"Downloading... {current}/{total}")

    def _on_downloads_complete(self):
        self.progress_bar.setVisible(False)
        self.download_btn.setEnabled(True)
        is_live = self.current_source and self.current_source.source_type == "live"
        dest = self.config.get("live_download_dir" if is_live else "static_download_dir", "")
        count = len(self.selected_indices)
        self.status_bar.showMessage(f"Downloaded {count} wallpaper(s) to {dest}")
        self.selected_indices.clear()
        self._update_card_selections()
        self._update_selection_ui()

        QMessageBox.information(self, "Download Complete",
                                f"Successfully downloaded {count} wallpaper(s) to:\n{dest}")

    def _open_local_browser(self):
        """Open the local wallpaper browser dialog with tabs."""
        static_dir = self.config.get("static_download_dir", "")
        live_dir = self.config.get("live_download_dir", "")
        if not static_dir and not live_dir:
            QMessageBox.warning(self, "Folders Not Set",
                                "Please set at least one download folder first\n"
                                "(Static or Live wallpapers).")
            return
        dlg = LocalBrowserDialog(static_dir, live_dir, self)
        dlg.exec()

    def _set_wallpaper(self, filepath):
        """Set a static wallpaper using common DE tools."""
        desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").upper()
        cmd = None

        if "KDE" in desktop or "PLASMA" in desktop:
            # KDE Plasma via dbus
            cmd = [
                "plasma-apply-wallpaperimage", filepath
            ]
        elif "GNOME" in desktop:
            cmd = [
                "gsettings", "set", "org.gnome.desktop.background",
                "picture-uri-dark", f"file://{filepath}"
            ]
        elif "XFCE" in desktop:
            cmd = [
                "xfconf-query", "-c", "xfce4-desktop",
                "-p", "/backdrop/screen0/monitor0/workspace0/last-image",
                "-s", filepath
            ]
        elif "MATE" in desktop:
            cmd = [
                "gsettings", "set", "org.mate.background",
                "picture-filename", filepath
            ]
        elif "CINNAMON" in desktop:
            cmd = [
                "gsettings", "set", "org.cinnamon.desktop.background",
                "picture-uri", f"file://{filepath}"
            ]
        elif "HYPRLAND" in desktop or "SWAY" in desktop or "WAYLAND" in desktop:
            cmd = ["swaybg", "-i", filepath, "-m", "fill"]

        if not cmd:
            for tool in ["feh", "nitrogen"]:
                if shutil.which(tool):
                    if tool == "feh":
                        cmd = ["feh", "--bg-fill", filepath]
                    else:
                        cmd = ["nitrogen", "--set-zoom-fill", filepath]
                    break

        if cmd:
            try:
                subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                self.status_bar.showMessage(f"Wallpaper set: {os.path.basename(filepath)}")
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Failed to set wallpaper:\n{e}")
        else:
            QMessageBox.information(
                self, "Set Wallpaper",
                f"Could not detect wallpaper tool for your desktop.\n\n"
                f"File path copied — set it manually:\n{filepath}"
            )
            clipboard = QApplication.clipboard()
            if clipboard:
                clipboard.setText(filepath)

    def _prev_page(self):
        if self.current_page > 1:
            self.current_page -= 1
            self._fetch_wallpapers()

    def _next_page(self):
        self.current_page += 1
        self._fetch_wallpapers()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.wallpapers:
            QTimer.singleShot(100, self._relayout_grid)

    def _relayout_grid(self):
        """Re-layout cards on resize."""
        cards = []
        for i in range(self.grid_layout.count()):
            w = self.grid_layout.itemAt(i).widget()
            if isinstance(w, WallpaperCard):
                cards.append(w)

        if not cards:
            return

        cols = max(1, (self.scroll.viewport().width() - 20) // 230)

        # Remove all from layout without deleting
        while self.grid_layout.count():
            self.grid_layout.takeAt(0)

        for i, card in enumerate(cards):
            row, col = divmod(i, cols)
            self.grid_layout.addWidget(card, row, col)


def _install_message_filter():
    """Suppress noisy Qt warnings that are harmless."""
    _original_handler = None
    try:
        from PyQt6.QtCore import qInstallMessageHandler, QtMsgType
        _suppressed = (
            b"glGetString",
            b"context info",
            b"Parent future has",
            b"GStreamer",
        )
        def _filter(msg_type, context, message):
            msg_bytes = message.encode() if isinstance(message, str) else message
            for pattern in _suppressed:
                if pattern in msg_bytes:
                    return
            # Let through everything else
            sys.stderr.write(message + "\n")
        qInstallMessageHandler(_filter)
    except Exception:
        pass


def main():
    _install_message_filter()
    app = QApplication(sys.argv)
    app.setApplicationName("Xero Wallpaper Browser")
    app.setOrganizationName("XeroLinux")

    # Set app icon
    logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "xero_logo.png")
    if os.path.exists(logo_path):
        app.setWindowIcon(QIcon(logo_path))

    window = XeroWallpaperBrowser()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
