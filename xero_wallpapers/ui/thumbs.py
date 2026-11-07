import hashlib
import io
import logging
import os
import threading
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import unquote

from PIL import Image, ImageFilter
from PyQt6.QtCore import QBuffer, QByteArray, QSize, Qt, QUrl
from PyQt6.QtGui import QImage, QImageReader
from PyQt6.QtQuick import QQuickAsyncImageProvider, QQuickImageResponse, QQuickTextureFactory

from .. import net, paths
from ..downloads import require_http

log = logging.getLogger("xero_wallpapers.thumbs")

CACHE_SIZES_MB = (250, 500, 1000)
MEMORY_ITEMS = 300
EVICT_EVERY = 50
MAX_BYTES = 20 * 1024 * 1024
HERO_MAX_BYTES = 8 * 1024 * 1024
HERO_WIDTH = 1920
MAX_PIXELS = 64_000_000
BLUR_SIZE = 48
LOCAL_BLUR_MAX_BYTES = 50 * 1024 * 1024

THUMB_EXECUTOR = ThreadPoolExecutor(max_workers=6)


def cache_dir() -> Path:
    return Path(paths.CACHE_DIR) / "thumbs"


_disk_cap = 500 * 1024 * 1024


def set_disk_cap(megabytes: int):
    global _disk_cap
    _disk_cap = megabytes * 1024 * 1024


def clear_cache(folder: Path) -> int:
    freed = 0
    try:
        files = [p for p in folder.iterdir() if p.is_file()]
    except OSError:
        return 0
    for p in files:
        try:
            size = p.stat().st_size
            p.unlink()
            freed += size
        except OSError:
            pass
    return freed


def evict(folder: Path, cap: int | None = None):
    cap = _disk_cap if cap is None else cap
    try:
        files = [(p.stat(), p) for p in folder.iterdir() if p.is_file()]
    except OSError:
        return
    total = sum(st.st_size for st, _ in files)
    for st, p in sorted(files, key=lambda f: f[0].st_mtime):
        if total <= cap:
            break
        try:
            p.unlink()
            total -= st.st_size
        except OSError:
            pass


_write_lock = threading.Lock()
_writes = 0


def _cache_path(key: str) -> Path:
    return cache_dir() / hashlib.sha1(key.encode()).hexdigest()


def _read_cached(path: Path) -> bytes | None:
    try:
        data = path.read_bytes()
        os.utime(path)
        return data
    except OSError:
        return None


def _fetch(url: str, cap: int) -> bytes:
    chunks, size = [], 0
    with net.SESSION.get(url, timeout=net.TIMEOUT, stream=True) as r:
        r.raise_for_status()
        for chunk in r.iter_content(64 * 1024):
            size += len(chunk)
            if size > cap:
                raise ValueError(f"image larger than {cap // (1024 * 1024)} MB")
            chunks.append(chunk)
    return b"".join(chunks)


def _store(path: Path, data: bytes):
    global _writes
    folder = path.parent
    folder.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".{threading.get_ident()}.part")
    tmp.write_bytes(data)
    os.replace(tmp, path)
    with _write_lock:
        _writes += 1
        due = _writes % EVICT_EVERY == 0
    if due:
        evict(folder)


_inflight: dict[str, threading.Lock] = {}
_inflight_lock = threading.Lock()


def cached_bytes(url: str) -> bytes:
    require_http(url)
    path = _cache_path(url)
    data = _read_cached(path)
    if data is not None:
        return data
    # The grid and the duplicate check ask for the same thumbnail at once; fetch it only once.
    with _inflight_lock:
        lock = _inflight.setdefault(url, threading.Lock())
    try:
        with lock:
            data = _read_cached(path)
            if data is None:
                data = _fetch(url, MAX_BYTES)
                _store(path, data)
    finally:
        with _inflight_lock:
            _inflight.pop(url, None)
    return data


def _check_pixels(w: int, h: int):
    if w * h > MAX_PIXELS:
        raise ValueError(f"image too large ({w}x{h})")


def _open_reduced(data: bytes, box: tuple[int, int] = (HERO_WIDTH, 1)) -> Image.Image:
    image = Image.open(io.BytesIO(data))
    _check_pixels(*image.size)
    image.draft("RGB", box)
    return image


def hero_bytes(url: str) -> bytes:
    require_http(url)
    path = _cache_path("hero:" + url)
    data = _read_cached(path)
    if data is None:
        image = _open_reduced(_fetch(url, HERO_MAX_BYTES)).convert("RGB")
        image.thumbnail((HERO_WIDTH, HERO_WIDTH * 4))
        buf = io.BytesIO()
        image.save(buf, "JPEG", quality=90)
        data = buf.getvalue()
        _store(path, data)
    return data


def blurred(data: bytes) -> QImage:
    image = _open_reduced(data, (BLUR_SIZE, BLUR_SIZE)).convert("RGB")
    image.thumbnail((BLUR_SIZE, BLUR_SIZE))
    image = image.filter(ImageFilter.GaussianBlur(2))
    buf = io.BytesIO()
    image.save(buf, "PNG")
    return QImage.fromData(buf.getvalue())


class _Memory:
    def __init__(self, limit: int):
        self._limit = limit
        self._data: OrderedDict = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key):
        with self._lock:
            image = self._data.get(key)
            if image is not None:
                self._data.move_to_end(key)
            return image

    def put(self, key, image):
        with self._lock:
            self._data[key] = image
            self._data.move_to_end(key)
            while len(self._data) > self._limit:
                self._data.popitem(last=False)


class _Response(QQuickImageResponse):
    def __init__(self):
        super().__init__()
        self._image = QImage()
        self._error = ""
        self._cancelled = threading.Event()

    def cancel(self):
        self._cancelled.set()

    def cancelled(self) -> bool:
        return self._cancelled.is_set()

    def textureFactory(self):
        return QQuickTextureFactory.textureFactoryForImage(self._image)

    def errorString(self):
        return self._error

    def complete(self, image: QImage, error: str):
        self._image = image
        self._error = error
        try:
            self.finished.emit()
        except RuntimeError:
            pass


class ThumbProvider(QQuickAsyncImageProvider):
    def __init__(self):
        super().__init__()
        self._memory = _Memory(MEMORY_ITEMS)
        THUMB_EXECUTOR.submit(evict, cache_dir())

    def requestImageResponse(self, id_: str, requested: QSize):
        response = _Response()
        url = unquote(id_)
        size = (requested.width(), requested.height()) if requested.isValid() else (0, 0)
        THUMB_EXECUTOR.submit(self._load, response, url, size)
        return response

    def _load(self, response: _Response, url: str, size: tuple[int, int]):
        if response.cancelled():
            response.complete(QImage(), "cancelled")
            return
        try:
            key = (url, size)
            image = self._memory.get(key)
            if image is None:
                image = self._scaled(self._decode(url), size)
                self._memory.put(key, image)
            response.complete(image, "")
        except Exception as e:
            log.debug("thumbnail %s failed: %s", url, e)
            response.complete(QImage(), str(e) or type(e).__name__)

    @staticmethod
    def _decode(url: str) -> QImage:
        if url.startswith("blur\n"):
            inner = url.removeprefix("blur\n")
            if inner.startswith("file:"):
                path = Path(QUrl(inner).toLocalFile())
                if path.stat().st_size > LOCAL_BLUR_MAX_BYTES:
                    raise ValueError("file too large to blur")
                return blurred(path.read_bytes())
            return blurred(cached_bytes(inner))
        if not url.startswith("hero\n"):
            return ThumbProvider._image(cached_bytes(url))
        _, original, preview, thumb = url.split("\n")
        attempts = [(hero_bytes, original), (cached_bytes, preview), (cached_bytes, thumb)]
        error: Exception = ValueError("no hero image")
        for fetch, candidate in attempts:
            if not candidate:
                continue
            try:
                return ThumbProvider._image(fetch(candidate))
            except Exception as e:
                log.debug("hero candidate %s failed: %s", candidate, e)
                error = e
        raise error

    @staticmethod
    def _image(data: bytes) -> QImage:
        buffer = QBuffer()
        buffer.setData(QByteArray(data))
        reader = QImageReader(buffer)
        size = reader.size()
        _check_pixels(size.width(), size.height())
        image = reader.read()
        if image.isNull():
            raise ValueError("not an image")
        return image

    @staticmethod
    def _scaled(image: QImage, size: tuple[int, int]) -> QImage:
        w, h = size
        if image.isNull() or (w <= 0 and h <= 0):
            return image
        w = w if w > 0 else round(image.width() * h / image.height())
        h = h if h > 0 else round(image.height() * w / image.width())
        if image.width() <= w and image.height() <= h:
            return image
        return image.scaled(
            w, h, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation
        )
