import threading
import time
from concurrent.futures import ThreadPoolExecutor

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
}

TIMEOUT = (5, 20)

SESSION = requests.Session()
SESSION.headers.update(HEADERS)
_adapter = HTTPAdapter(
    max_retries=Retry(total=2, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503])
)
SESSION.mount("http://", _adapter)
SESSION.mount("https://", _adapter)

EXECUTOR = ThreadPoolExecutor(max_workers=8)
# Set at quit so long waits (the Wallhaven rate limiter, Tidy lookups) give up instead of
# keeping the process alive after the window has closed.
STOP = threading.Event()


def shutdown(executors, grace: float, drain=()) -> bool:
    # Pools in drain keep their queued work (e.g. the latest slideshow apply) and finish within the grace.
    STOP.set()
    for ex in executors:
        ex.shutdown(wait=False, cancel_futures=True)
    for ex in drain:
        ex.shutdown(wait=False)
    deadline = time.monotonic() + grace
    # concurrent.futures joins its workers at interpreter exit, so report any still running.
    workers = [t for ex in (*executors, *drain) for t in list(getattr(ex, "_threads", ()))]
    for t in workers:
        t.join(max(0.0, deadline - time.monotonic()))
    return not any(t.is_alive() for t in workers)
