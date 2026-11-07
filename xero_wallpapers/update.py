import hashlib
import os
import platform
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from . import UPDATE_REPO, VERSION, net

_RUNTIME_VARS = {"APPIMAGE", "APPDIR", "ARGV0", "OWD", "LD_PRELOAD", "LD_LIBRARY_PATH", "PYTHONHOME", "PYTHONPATH",
                 "QT_PLUGIN_PATH", "QML_IMPORT_PATH", "QML2_IMPORT_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH"}
_SEARCH_PATHS = {"PATH", "XDG_DATA_DIRS", "XDG_CONFIG_DIRS"}
_HEADERS = {"User-Agent": f"XeroWallpapers/{VERSION}"}
CHUNK = 1 << 20


class UpdateError(Exception):
    pass


@dataclass(frozen=True)
class UpdateInfo:
    version: str
    url: str
    sha256: str


def _version(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r"\d+", text or ""))


def newer(candidate: str, current: str) -> bool:
    return _version(candidate) > _version(current)


def latest_version(final_url: str) -> str | None:
    # github.com/<repo>/releases/latest redirects to the tag, which needs no rate-limited API call.
    match = re.search(r"/releases/tag/v?(\d+(?:\.\d+)*)$", final_url)
    return match[1] if match else None


def asset_url(repo: str, version: str, arch: str) -> str:
    return f"https://github.com/{repo}/releases/download/v{version}/Xero_Wallpapers-{version}-{arch}.AppImage"


def parse_checksum(text: str, name: str) -> str | None:
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].lstrip("*") == name and re.fullmatch(r"[0-9a-f]{64}", parts[0]):
            return parts[0]
    return None


def clean_env(env: dict, mount: str) -> dict:
    cleaned = {}
    for key, value in env.items():
        if key in _RUNTIME_VARS or key.startswith("SHARUN_"):
            continue
        if key in _SEARCH_PATHS:
            value = ":".join(p for p in value.split(":") if p and not p.startswith(mount))
        cleaned[key] = value
    return cleaned


def running_appimage() -> Path | None:
    path = Path(os.environ.get("APPIMAGE", ""))
    if not UPDATE_REPO or not path.is_file():
        return None
    if not os.access(path, os.W_OK) or not os.access(path.parent, os.W_OK):
        return None
    return path


def check() -> UpdateInfo | None:
    try:
        r = net.SESSION.head(f"https://github.com/{UPDATE_REPO}/releases/latest", headers=_HEADERS,
                             allow_redirects=True, timeout=net.TIMEOUT)
        version = latest_version(r.url)
        if not version or not newer(version, VERSION):
            return None
        url = asset_url(UPDATE_REPO, version, platform.machine())
        r = net.SESSION.get(url + ".sha256", headers=_HEADERS, timeout=net.TIMEOUT)
        r.raise_for_status()
        sha256 = parse_checksum(r.text[:4096], url.rsplit("/", 1)[-1])
    except (OSError, ValueError):
        return None
    return UpdateInfo(version, url, sha256) if sha256 else None


def install(info: UpdateInfo, target: Path, progress):
    partial = target.with_name(target.name + ".new")
    digest = hashlib.sha256()
    received = 0
    try:
        with net.SESSION.get(info.url, headers=_HEADERS, stream=True, timeout=net.TIMEOUT) as r:
            r.raise_for_status()
            size = int(r.headers.get("Content-Length") or 0)
            with open(partial, "wb") as out:
                for chunk in r.iter_content(CHUNK):
                    if net.STOP.is_set():
                        raise UpdateError("the update was cancelled")
                    out.write(chunk)
                    digest.update(chunk)
                    received += len(chunk)
                    if size:
                        progress(received / size)
        if size and received != size:
            raise UpdateError("the download was incomplete")
        if digest.hexdigest() != info.sha256:
            raise UpdateError("the download did not match the published checksum")
        partial.chmod(0o755)
        os.replace(partial, target)
    except (OSError, ValueError, UpdateError) as e:
        partial.unlink(missing_ok=True)
        raise UpdateError(str(e)) from e


def relaunch_after_exit(target: Path):
    env = clean_env(dict(os.environ), os.environ.get("APPDIR", "/nonexistent"))
    subprocess.Popen(["/bin/sh", "-c", 'while kill -0 "$1" 2>/dev/null; do sleep 0.2; done; exec "$2"',
                      "xero-wallpapers-update", str(os.getpid()), str(target)],
                     env=env, start_new_session=True,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
