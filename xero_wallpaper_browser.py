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
import subprocess
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin, urlparse, quote

import requests
from bs4 import BeautifulSoup
from PIL import Image
from io import BytesIO

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QLabel, QPushButton, QComboBox, QFileDialog,
    QScrollArea, QFrame, QProgressBar, QStatusBar, QLineEdit,
    QCheckBox, QSplitter, QDialog, QDialogButtonBox, QSpinBox,
    QMessageBox, QSizePolicy, QToolBar, QStyle, QMenu, QTabWidget
)
from PyQt6.QtCore import (
    Qt, QThread, pyqtSignal, QSize, QTimer, QPropertyAnimation,
    QEasingCurve, QPoint, QRect, pyqtProperty, QObject, QUrl
)
from PyQt6.QtGui import (
    QPixmap, QImage, QIcon, QPainter, QColor, QPalette, QFont,
    QAction, QDesktopServices, QCursor, QPainterPath, QBrush, QPen
)
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget

import cv2
import numpy as np


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


class DuskLinuxSource(WallpaperSource):
    name = "DuskLinux Dark"
    url = "https://github.com/dusklinux/images/tree/main/dark"
    source_type = "static"

    def fetch_wallpapers(self, page=1, search=""):
        api_url = "https://api.github.com/repos/dusklinux/images/contents/dark"
        try:
            r = requests.get(api_url, headers=HEADERS, timeout=15)
            r.raise_for_status()
            items = r.json()
            results = []
            for item in items:
                if item.get("type") == "file" and any(
                    item["name"].lower().endswith(ext) for ext in
                    (".jpg", ".jpeg", ".png", ".webp")
                ):
                    raw_url = item.get("download_url", "")
                    if raw_url:
                        results.append({
                            "thumb_url": raw_url,
                            "full_url": raw_url,
                            "title": item["name"],
                            "resolution": "",
                        })
            if search:
                results = [r for r in results if search.lower() in r["title"].lower()]
            return results
        except Exception as e:
            print(f"DuskLinux error: {e}")
            return []


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


class DesktopHutSource(WallpaperSource):
    name = "DesktopHut"
    url = "https://www.desktophut.com"
    source_type = "live"

    def fetch_wallpapers(self, page=1, search=""):
        try:
            if search:
                url = f"https://www.desktophut.com/search/{quote(search)}?page={page}"
            else:
                url = f"https://www.desktophut.com/category/Animated-Wallpapers?page={page}"
            r = requests.get(url, headers=HEADERS, timeout=15)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")
            results = []
            # Find all links to /live-wallpaper/ detail pages
            seen = set()
            for link in soup.select("a[href*='/live-wallpaper/']"):
                page_url = link.get("href", "")
                if not page_url.startswith("http"):
                    page_url = urljoin("https://www.desktophut.com", page_url)
                # Skip download links and duplicates
                if "/download" in page_url or page_url in seen:
                    continue
                seen.add(page_url)
                # Title from link text or slug
                title = link.get_text(strip=True)
                if not title:
                    slug = page_url.rstrip("/").split("/")[-1]
                    title = slug.replace("-", " ").title()
                # Thumbnails are JS-loaded; try to find nearby img
                img = link.select_one("img")
                thumb = ""
                if img:
                    thumb = img.get("src") or img.get("data-src") or ""
                    if thumb and not thumb.startswith("http"):
                        thumb = urljoin("https://www.desktophut.com", thumb)
                    # Skip SVG placeholders
                    if "svg" in thumb.lower() or "data:" in thumb.lower():
                        thumb = ""
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
            print(f"DesktopHut error: {e}")
            return []

    def resolve_download_url(self, page_url):
        """Get thumbnail and download URL from detail page."""
        try:
            r = requests.get(page_url, headers=HEADERS, timeout=15)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")
            # Direct download link: /live-wallpaper/{slug}/download
            download_url = page_url.rstrip("/") + "/download"
            return download_url
        except Exception as e:
            print(f"DesktopHut resolve error: {e}")
        return page_url

    def get_detail_thumb(self, page_url):
        """Fetch thumbnail from detail page (for lazy-loaded listings)."""
        try:
            r = requests.get(page_url, headers=HEADERS, timeout=15)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")
            # Look for thumbnail in uploads/thumbnails
            for img in soup.select("img[src*='/uploads/thumbnails/']"):
                src = img["src"]
                if not src.startswith("http"):
                    src = urljoin("https://www.desktophut.com", src)
                return src
            # Fallback: og:image meta
            og = soup.select_one("meta[property='og:image']")
            if og and og.get("content"):
                return og["content"]
        except Exception:
            pass
        return ""


STATIC_SOURCES = [DuskLinuxSource(), WallhavenSource(), FourKWallpapersSource()]
LIVE_SOURCES = [MoeWallsSource(), MotionBGsSource(), DesktopHutSource()]


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

    def run(self):
        data = cached_download(self.url)
        if data:
            px = bytes_to_qpixmap(data, self.size)
            if px:
                self.thumbnail_ready.emit(self.index, px)


class LocalThumbnailWorker(QThread):
    thumbnail_ready = pyqtSignal(int, QPixmap)

    def __init__(self, index, filepath, size):
        super().__init__()
        self.index = index
        self.filepath = filepath
        self.size = size

    def run(self):
        try:
            img = QImage(self.filepath)
            if not img.isNull():
                px = QPixmap.fromImage(img)
                if self.size:
                    px = px.scaled(self.size, Qt.AspectRatioMode.KeepAspectRatio,
                                   Qt.TransformationMode.SmoothTransformation)
                self.thumbnail_ready.emit(self.index, px)
        except Exception:
            pass


class VideoThumbnailWorker(QThread):
    """Extract a thumbnail frame from a video file using OpenCV."""
    thumbnail_ready = pyqtSignal(int, QPixmap)

    def __init__(self, index, filepath, size):
        super().__init__()
        self.index = index
        self.filepath = filepath
        self.size = size

    def run(self):
        try:
            cap = cv2.VideoCapture(self.filepath)
            if not cap.isOpened():
                return
            # Seek to 25% of video for a representative frame
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            if total_frames > 10:
                cap.set(cv2.CAP_PROP_POS_FRAMES, total_frames // 4)
            ret, frame = cap.read()
            cap.release()
            if not ret or frame is None:
                return
            # Convert BGR to RGB
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, ch = frame.shape
            img = QImage(frame.data, w, h, ch * w, QImage.Format.Format_RGB888)
            px = QPixmap.fromImage(img)
            if self.size:
                px = px.scaled(self.size, Qt.AspectRatioMode.KeepAspectRatio,
                               Qt.TransformationMode.SmoothTransformation)
            # Draw a play button overlay
            painter = QPainter(px)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            cx, cy = px.width() // 2, px.height() // 2
            # Semi-transparent circle
            painter.setBrush(QBrush(QColor(0, 0, 0, 140)))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(QPoint(cx, cy), 22, 22)
            # White triangle
            painter.setBrush(QBrush(QColor(255, 255, 255, 220)))
            triangle = [QPoint(cx - 8, cy - 12), QPoint(cx - 8, cy + 12), QPoint(cx + 14, cy)]
            painter.drawPolygon(triangle)
            painter.end()
            self.thumbnail_ready.emit(self.index, px)
        except Exception:
            pass


class DetailThumbWorker(QThread):
    """Fetch thumbnail from a detail page (for sites with JS-loaded listings)."""
    thumbnail_ready = pyqtSignal(int, QPixmap)

    def __init__(self, index, source, page_url, size):
        super().__init__()
        self.index = index
        self.source = source
        self.page_url = page_url
        self.size = size

    def run(self):
        try:
            thumb_url = self.source.get_detail_thumb(self.page_url)
            if thumb_url:
                data = cached_download(thumb_url)
                if data:
                    px = bytes_to_qpixmap(data, self.size)
                    if px:
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

        layout = QVBoxLayout(self)

        self.image_label = QLabel("Loading full resolution...")
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

        self.load_thread = ThumbnailWorker(0, item["full_url"], QSize(1200, 900))
        self.load_thread.thumbnail_ready.connect(self._on_loaded)
        self.load_thread.start()

    def _on_loaded(self, _, pixmap):
        self.image_label.setPixmap(pixmap.scaled(
            self.image_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        ))


class LocalPreviewDialog(QDialog):
    """Preview a local image or video file with option to set as wallpaper."""

    def __init__(self, filepath, parent=None):
        super().__init__(parent)
        self.filepath = filepath
        self.setWindowTitle(os.path.basename(filepath))
        self.setMinimumSize(900, 650)
        self.resize(1000, 720)
        self._is_video = any(filepath.lower().endswith(ext)
                             for ext in (".mp4", ".webm", ".mkv", ".avi"))

        layout = QVBoxLayout(self)

        if self._is_video:
            self._build_video_preview(layout)
        else:
            self._build_image_preview(layout)

        # Info label
        info = QLabel(os.path.basename(filepath))
        info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(info)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_style = """
            QPushButton {
                background-color: #5b8bd4;
                color: white;
                border: none;
                padding: 6px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #4a7bc3; }
        """
        if not self._is_video:
            set_btn = QPushButton("Set as Wallpaper")
            set_btn.setStyleSheet(btn_style)
            set_btn.clicked.connect(self.accept)
            btn_layout.addStretch()
            btn_layout.addWidget(set_btn)
        else:
            btn_layout.addStretch()

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self._close)
        btn_layout.addWidget(close_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

    def _build_image_preview(self, layout):
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self.image_label)

        px = QPixmap(self.filepath)
        if not px.isNull():
            self.image_label.setPixmap(px.scaled(
                QSize(1100, 800),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            ))

    def _build_video_preview(self, layout):
        # Info note
        note = QLabel("Live wallpapers must be set using your preferred live wallpaper tool "
                       "(e.g. Komorebi, Hidamari, xwinwrap, mpvpaper)")
        note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        note.setWordWrap(True)
        note.setStyleSheet("color: #e8a035; font-size: 11px; font-weight: bold; padding: 4px 0;")
        layout.addWidget(note)

        # Video player
        self.video_widget = QVideoWidget()
        self.video_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self.video_widget)

        self.media_player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.media_player.setAudioOutput(self.audio_output)
        self.media_player.setVideoOutput(self.video_widget)
        self.audio_output.setVolume(0.5)

        # Transport controls
        transport = QHBoxLayout()

        self.play_btn = QPushButton("▶ Play")
        self.play_btn.clicked.connect(self._toggle_play)
        transport.addWidget(self.play_btn)

        self.stop_btn = QPushButton("⏹ Stop")
        self.stop_btn.clicked.connect(self._stop)
        transport.addWidget(self.stop_btn)

        self.position_label = QLabel("0:00 / 0:00")
        transport.addWidget(self.position_label)

        transport.addStretch()

        vol_label = QLabel("Vol:")
        transport.addWidget(vol_label)
        self.vol_slider = QSpinBox()
        self.vol_slider.setRange(0, 100)
        self.vol_slider.setValue(50)
        self.vol_slider.setSuffix("%")
        self.vol_slider.valueChanged.connect(lambda v: self.audio_output.setVolume(v / 100.0))
        transport.addWidget(self.vol_slider)

        self.loop_btn = QPushButton("🔁 Loop")
        self.loop_btn.setCheckable(True)
        self.loop_btn.setChecked(True)
        transport.addWidget(self.loop_btn)

        layout.addLayout(transport)

        # Connect signals
        self.media_player.positionChanged.connect(self._on_position_changed)
        self.media_player.durationChanged.connect(self._on_duration_changed)
        self.media_player.mediaStatusChanged.connect(self._on_media_status)
        self._duration = 0

        # Load and auto-play
        self.media_player.setSource(QUrl.fromLocalFile(self.filepath))
        QTimer.singleShot(300, lambda: self.media_player.play())

    def _toggle_play(self):
        if self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.media_player.pause()
            self.play_btn.setText("▶ Play")
        else:
            self.media_player.play()
            self.play_btn.setText("⏸ Pause")

    def _stop(self):
        self.media_player.stop()
        self.play_btn.setText("▶ Play")

    def _on_position_changed(self, pos):
        cur = self._format_time(pos)
        total = self._format_time(self._duration)
        self.position_label.setText(f"{cur} / {total}")

    def _on_duration_changed(self, dur):
        self._duration = dur

    def _on_media_status(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia and self.loop_btn.isChecked():
            self.media_player.setPosition(0)
            self.media_player.play()

    @staticmethod
    def _format_time(ms):
        s = ms // 1000
        return f"{s // 60}:{s % 60:02d}"

    def _close(self):
        if self._is_video:
            self.media_player.stop()
        self.reject()

    def closeEvent(self, event):
        if self._is_video:
            self.media_player.stop()
        super().closeEvent(event)


# ---------------------------------------------------------------------------
# Local Browser Dialog (tabbed: Static / Live)
# ---------------------------------------------------------------------------

class LocalBrowserTab(QWidget):
    """A single tab for browsing local wallpapers of one type."""

    def __init__(self, folder, file_type, parent_dialog, parent=None):
        super().__init__(parent)
        self.folder = folder
        self.file_type = file_type
        self.parent_dialog = parent_dialog
        self.thumb_workers = []

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
                worker.thumbnail_ready.connect(lambda idx, px: self._set_thumb(idx, px))
                self.thumb_workers.append(worker)
                worker.start()
            elif is_video:
                worker = VideoThumbnailWorker(i, filepath, QSize(208, 140))
                worker.thumbnail_ready.connect(lambda idx, px: self._set_thumb(idx, px))
                self.thumb_workers.append(worker)
                worker.start()

    def _set_thumb(self, index, pixmap):
        for i in range(self.grid_layout.count()):
            widget = self.grid_layout.itemAt(i).widget()
            if isinstance(widget, WallpaperCard) and widget.index == index:
                widget.set_thumbnail(pixmap)
                break

    def _on_double_click(self, filepath):
        dlg = LocalPreviewDialog(filepath, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            # Only images return Accepted (set as wallpaper)
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

    def set_wallpaper(self, filepath):
        """Delegate to main window's wallpaper setter."""
        if self.main_window and hasattr(self.main_window, "_set_wallpaper"):
            self.main_window._set_wallpaper(filepath)


# ---------------------------------------------------------------------------
# About Dialog
# ---------------------------------------------------------------------------

class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About")
        self.setFixedSize(360, 300)
        self.setWindowFlags(
            Qt.WindowType.Dialog |
            Qt.WindowType.WindowTitleHint |
            Qt.WindowType.WindowCloseButtonHint
        )

        layout = QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(28, 22, 28, 22)

        # Logo centered
        logo_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "xero_logo.png")
        if os.path.exists(logo_path):
            logo_label = QLabel()
            logo_px = QPixmap(logo_path).scaled(
                QSize(72, 72), Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            logo_label.setPixmap(logo_px)
            logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(logo_label)

        layout.addSpacing(10)

        # App name
        name_label = QLabel("Xero Wallpaper Browser")
        name_font = name_label.font()
        name_font.setPointSize(14)
        name_font.setBold(True)
        name_label.setFont(name_font)
        name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(name_label)

        layout.addSpacing(6)

        # Description
        desc_label = QLabel(
            "Browse, preview and download wallpapers\n"
            "from multiple online sources. Part of the\n"
            "XeroLinux project."
        )
        desc_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc_label.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(desc_label)

        layout.addSpacing(18)

        # Separator line
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: rgba(128,128,128,0.3);")
        layout.addWidget(sep)

        layout.addSpacing(14)

        links = [
            ("🌐", "Website", "https://xerolinux.xyz"),
            ("📖", "Wiki", "https://wiki.xerolinux.xyz"),
            ("☕", "Donate", "https://ko-fi.com/xerolinux"),
            ("🐙", "GitHub", "https://github.com/xerolinux"),
        ]

        icons_row = QHBoxLayout()
        icons_row.setSpacing(14)
        icons_row.addStretch()

        for icon, tooltip, url in links:
            col = QVBoxLayout()
            col.setSpacing(4)
            col.setAlignment(Qt.AlignmentFlag.AlignHCenter)

            btn = QPushButton(icon)
            btn.setToolTip(tooltip)
            btn.setFixedSize(52, 44)
            btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            btn.clicked.connect(lambda checked, u=url: QDesktopServices.openUrl(QUrl(u)))
            col.addWidget(btn, alignment=Qt.AlignmentFlag.AlignHCenter)

            lbl = QLabel(tooltip)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet("font-size: 10px; color: gray;")
            col.addWidget(lbl)

            icons_row.addLayout(col)

        icons_row.addStretch()
        layout.addLayout(icons_row)

        layout.addStretch()


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

        about_btn = QPushButton("ℹ About")
        about_btn.setToolTip("About Xero Wallpaper Browser")
        about_btn.clicked.connect(self._show_about)
        header.addWidget(about_btn)

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

        controls.addSpacing(8)

        refresh_btn = QPushButton("↻")
        refresh_btn.setToolTip("Reload wallpapers from the selected source")
        refresh_btn.setFixedSize(48, 30)
        refresh_font = refresh_btn.font()
        refresh_font.setPointSize(16)
        refresh_btn.setFont(refresh_font)
        refresh_btn.clicked.connect(self._do_refresh)
        controls.addWidget(refresh_btn)

        controls.addSpacing(8)

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

        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Set your download folders and select a source to begin.")

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

    def _do_refresh(self):
        if self.current_source:
            self._fetch_wallpapers()
        else:
            self.status_bar.showMessage("Please select a source first.")

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

        # Stop previous workers
        for w in self.thumb_workers:
            if w.isRunning():
                w.quit()
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
            elif wp.get("page_url") and self.current_source and hasattr(self.current_source, "get_detail_thumb"):
                # Fetch thumbnail from detail page (e.g. DesktopHut)
                worker = DetailThumbWorker(i, self.current_source, wp["page_url"], QSize(208, 140))
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
                # For live wallpapers, just select for download
                self.selected_indices = {index}
                self._update_card_selections()
                self._update_selection_ui()
                self._download_selected()

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

    def _show_about(self):
        dlg = AboutDialog(self)
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
            # Fallback: try feh, nitrogen, or notify user
            for tool in ["feh", "nitrogen"]:
                if os.system(f"which {tool} > /dev/null 2>&1") == 0:
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
