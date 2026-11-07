import json
import logging
import os
import tempfile
import threading
import time
from collections import deque
from pathlib import Path
from typing import Callable

log = logging.getLogger("xero_wallpapers.tags")

MAX_CALLS = 40
PERIOD = 60.0
MAX_ENTRIES = 5000
BACKGROUND_RESERVE = 10


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=path.parent, prefix=path.name, suffix=".tmp", delete=False) as f:
        json.dump(data, f)
    try:
        os.replace(f.name, path)
    except OSError:
        os.unlink(f.name)
        raise


def _strs(value) -> list[str]:
    return [v for v in value if isinstance(v, str)] if isinstance(value, list) else []


class Stopped(Exception):
    pass


class RateLimiter:
    # Wall-clock timestamps are persisted so a restart cannot reset the per-minute budget.
    def __init__(self, max_calls: int = MAX_CALLS, state: Path | None = None, stop: threading.Event | None = None):
        self._max = max_calls
        self._stop = stop or threading.Event()
        self._state = Path(state) if state else None
        self._calls: deque[float] = deque(sorted(self._load()))
        self._lock = threading.Lock()

    def _load(self) -> list[float]:
        if self._state is None:
            return []
        try:
            raw = json.loads(self._state.read_text())
        except (OSError, ValueError):
            return []
        now = time.time()
        if not isinstance(raw, list):
            return []
        return [t for t in raw if isinstance(t, (int, float)) and now - PERIOD < t <= now]

    def acquire(self, reserve: int = 0) -> None:
        while True:
            if self._stop.is_set():
                raise Stopped()
            with self._lock:
                now = time.time()
                while self._calls and (now - self._calls[0] >= PERIOD or self._calls[0] > now):
                    self._calls.popleft()
                if len(self._calls) < self._max - reserve:
                    self._calls.append(now)
                    self._save()
                    return
                wait = self._calls[len(self._calls) - (self._max - reserve)] + PERIOD - now
            self._stop.wait(max(wait, 0.01))

    def _save(self) -> None:
        if self._state is None:
            return
        try:
            _write_json(self._state, list(self._calls))
        except OSError as e:
            log.warning("rate limit state write failed: %s", e)


class TagCache:
    def __init__(self, path: Path):
        self._path = Path(path)
        self._data: dict | None = None
        self._lock = threading.Lock()

    def _load(self) -> dict:
        if self._data is None:
            try:
                data = json.loads(self._path.read_text())
            except (OSError, ValueError):
                data = {}
            self._data = data if isinstance(data, dict) else {}
        return self._data

    def get_entry(self, wid: str) -> tuple[list[str], str] | None:
        with self._lock:
            value = self._load().get(wid)
        if isinstance(value, list):
            return _strs(value), ""
        if isinstance(value, dict):
            author = value.get("a")
            return _strs(value.get("t")), author if isinstance(author, str) else ""
        return None

    def put(self, wid: str, tags: list[str], author: str = "") -> None:
        with self._lock:
            data = self._load()
            data.pop(wid, None)
            data[wid] = {"t": _strs(list(tags)), "a": author}
            while len(data) > MAX_ENTRIES:
                data.pop(next(iter(data)))
            try:
                _write_json(self._path, data)
            except OSError as e:
                log.warning("tag cache write failed: %s", e)


class TagFetcher:
    def __init__(self, fetch: Callable[[str], tuple[list[str], str]], cache: TagCache, limiter):
        self._fetch = fetch
        self.cache = cache
        self._limiter = limiter
        self._pending: deque[tuple[str, Callable]] = deque()
        self._cond = threading.Condition()
        self._thread: threading.Thread | None = None

    def detail(self, wid: str, reserve: int = 0) -> tuple[list[str], str]:
        cached = self.cache.get_entry(wid)
        if cached is not None:
            return cached
        self._limiter.acquire(reserve)
        tags, author = self._fetch(wid)
        self.cache.put(wid, tags, author)
        return list(tags), author

    def tags(self, wid: str) -> list[str]:
        return self.detail(wid)[0]

    def request(self, ids, callback: Callable[[str, list[str]], None]) -> None:
        with self._cond:
            queued = {wid for wid, _ in self._pending}
            for wid in ids:
                if wid not in queued:
                    queued.add(wid)
                    self._pending.append((wid, callback))
            if self._thread is None:
                self._thread = threading.Thread(target=self._run, name="wallhaven-tags", daemon=True)
                self._thread.start()
            self._cond.notify()

    def clear(self) -> None:
        with self._cond:
            self._pending.clear()

    def _run(self) -> None:
        while True:
            with self._cond:
                while not self._pending:
                    self._cond.wait()
                wid, callback = self._pending.popleft()
            try:
                found = self.detail(wid, BACKGROUND_RESERVE)[0]
            except Stopped:
                return
            except Exception as e:
                log.warning("tags for wallhaven %s failed: %s", wid, e)
                continue
            try:
                callback(wid, found)
            except Exception:
                log.exception("tag callback for %s crashed", wid)


class WorkQueue:
    # One rate-limited background thread; jobs with a key already queued are skipped.
    def __init__(self, limiter, name: str):
        self._limiter = limiter
        self._name = name
        self._pending: deque[tuple[str, Callable, Callable]] = deque()
        self._cond = threading.Condition()
        self._thread: threading.Thread | None = None

    def request(self, key: str, work: Callable, callback: Callable) -> None:
        with self._cond:
            if any(k == key for k, _, _ in self._pending):
                return
            self._pending.append((key, work, callback))
            if self._thread is None:
                self._thread = threading.Thread(target=self._run, name=self._name, daemon=True)
                self._thread.start()
            self._cond.notify()

    def clear(self) -> None:
        with self._cond:
            self._pending.clear()

    def _run(self) -> None:
        while True:
            with self._cond:
                while not self._pending:
                    self._cond.wait()
                key, work, callback = self._pending.popleft()
            try:
                self._limiter.acquire()
                result = work()
            except Stopped:
                return
            except Exception as e:
                log.warning("%s for %s failed: %s", self._name, key, e)
                result = None
            try:
                callback(key, result)
            except Exception:
                log.exception("%s callback for %s crashed", self._name, key)
