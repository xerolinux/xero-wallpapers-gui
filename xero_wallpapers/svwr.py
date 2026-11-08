import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

import requests

from . import kpackage, net, paths

ID = "luisbocanegra.smart.video.wallpaper.reborn"
REPO = "https://github.com/luisbocanegra/plasma-smart-video-wallpaper-reborn"
API_LATEST = REPO.replace("https://github.com/", "https://api.github.com/repos/") + "/releases/latest"
PACKAGE = "plasma-smart-video-wallpaper-reborn"
RUNTIME_DEPS = ("qt6-multimedia", "qt6-multimedia-ffmpeg")
OS_RELEASE = Path("/etc/os-release")
OBS = "https://download.opensuse.org/repositories/home:/luisbocanegra/"
ZYPP_REPO = Path("/etc/zypp/repos.d/home_luisbocanegra.repo")
OSTREE_BOOTED = Path("/run/ostree-booted")
TIMEOUT = 30

Step = tuple[str, str, str, str] | tuple[str, list[str]] | tuple[str, str]


class SvwrError(Exception):
    pass


def _metadata() -> tuple[Path, str] | None:
    for root in kpackage.PLUGIN_DIRS:
        try:
            meta = json.loads((root / ID / "metadata.json").read_text())
            return root, str(meta.get("KPlugin", {}).get("Version", ""))
        except (OSError, ValueError, AttributeError):
            continue
    return None


def installed_version() -> str | None:
    found = _metadata()
    return found[1] if found else None


def archive_install() -> bool:
    found = _metadata()
    return bool(found) and found[0] == kpackage.USER_DIR


def parse_version(s: str) -> tuple[int, ...]:
    parts = s.strip().removeprefix("v").split(".")
    out = []
    for p in parts:
        m = re.match(r"\d+", p)
        if not m:
            raise ValueError(f"bad version {s!r}")
        out.append(int(m.group(0)))
    return tuple(out)


def is_newer(latest: str, installed: str) -> bool:
    try:
        return parse_version(latest) > parse_version(installed)
    except ValueError:
        return False


def _os_release() -> dict[str, str]:
    data = {}
    try:
        for line in OS_RELEASE.read_text().splitlines():
            key, sep, value = line.partition("=")
            if sep:
                data[key.strip()] = value.strip().strip("\"'")
    except OSError:
        pass
    return data


def distro() -> Literal["arch", "fedora", "opensuse", "other"]:
    info = _os_release()
    ident = info.get("ID", "").lower()
    ids = {ident, *info.get("ID_LIKE", "").lower().split()}
    if "arch" in ids:
        return "arch"
    # Atomic variants (Kinoite) can't dnf install; they take the user-level archive route.
    if "fedora" in ids and "rhel" not in ids and not OSTREE_BOOTED.exists():
        return "fedora"
    # The author's OBS repo only builds for Tumbleweed and Slowroll; Leap takes the archive route.
    if ident in ("opensuse-tumbleweed", "opensuse-slowroll"):
        return "opensuse"
    return "other"


def _obs_variant() -> str:
    return "openSUSE_Slowroll" if _os_release().get("ID") == "opensuse-slowroll" else "openSUSE_Tumbleweed"


def _release() -> dict:
    r = net.SESSION.get(API_LATEST, timeout=net.TIMEOUT, headers={"Accept": "application/vnd.github+json"})
    r.raise_for_status()
    data = r.json()
    if not isinstance(data, dict):
        raise ValueError("unexpected release JSON")
    return data


def _github_https(url: str) -> bool:
    parts = urlparse(url)
    return parts.scheme == "https" and parts.netloc == "github.com"


def latest_asset() -> tuple[str, str, str, str]:
    try:
        data = _release()
        tag = str(data["tag_name"])
        assets = data.get("assets") or []
    except (requests.RequestException, ValueError, KeyError) as e:
        raise SvwrError(f"Couldn't read the latest release: {e}") from e
    name = f"{PACKAGE}-{tag}.tar.gz"
    archive_path(name)
    asset = next((a for a in assets if isinstance(a, dict) and a.get("name") == name), None)
    if asset is None:
        raise SvwrError(f"Release {tag} has no {name}")
    url = str(asset.get("browser_download_url", ""))
    digest = str(asset.get("digest", ""))
    if not _github_https(url):
        raise SvwrError("Release asset is not an https://github.com download")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        raise SvwrError("Release asset has no SHA-256 digest")
    return tag, url, digest.removeprefix("sha256:"), name


def archive_path(name: str) -> Path:
    if not name or "/" in name or ".." in name:
        raise SvwrError(f"Unsafe archive name {name!r}")
    return Path(paths.CACHE_DIR) / "svwr" / name


def verify(path: Path, sha256: str) -> None:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    if h.hexdigest() != sha256.lower():
        Path(path).unlink(missing_ok=True)
        raise SvwrError("Download failed verification")


def download_archive(url: str, sha256: str, name: str, progress=None) -> Path:
    if not _github_https(url):
        raise SvwrError("Refusing a download that is not from https://github.com")
    target = archive_path(name)
    target.parent.mkdir(parents=True, exist_ok=True)
    part = target.with_name(target.name + ".part")
    try:
        with net.SESSION.get(url, stream=True, timeout=net.TIMEOUT) as r:
            r.raise_for_status()
            total = int(r.headers.get("Content-Length") or 0)
            done = 0
            with open(part, "wb") as f:
                for chunk in r.iter_content(1 << 16):
                    f.write(chunk)
                    done += len(chunk)
                    if progress:
                        progress(done, total)
        os.replace(part, target)
    except (requests.RequestException, OSError) as e:
        part.unlink(missing_ok=True)
        raise SvwrError(f"Download failed: {e}") from e
    verify(target, sha256)
    return target


def install_archive(name: str) -> None:
    try:
        kpackage.install(archive_path(name), ID)
    except kpackage.KPackageError as e:
        raise SvwrError(str(e)) from e


def missing_runtime_deps() -> list[str]:
    if distro() != "arch":
        return []
    missing = []
    for dep in RUNTIME_DEPS:
        try:
            if subprocess.run(["pacman", "-Q", dep], capture_output=True, timeout=TIMEOUT).returncode:
                missing.append(dep)
        except (OSError, subprocess.SubprocessError):
            return []
    return missing


def deps_step(missing: list[str]) -> Step:
    return ("run", ["pkexec", "pacman", "-S", "--needed", "--noconfirm", *missing])


def install_steps(update: bool, allow_repo: bool = False) -> list[Step]:
    d = distro()
    if d == "fedora":
        return [("run", ["pkexec", "dnf", "upgrade" if update else "install", "-y", PACKAGE])]
    if d == "opensuse":
        if update:
            return [("run", ["pkexec", "zypper", "--non-interactive", "update", PACKAGE])]
        steps: list[Step] = []
        if not ZYPP_REPO.exists():
            if not allow_repo:
                raise SvwrError("Adding the plugin's openSUSE repository needs your confirmation")
            base = OBS + _obs_variant() + "/"
            steps += [
                ("run", ["pkexec", "rpm", "--import", base + "repodata/repomd.xml.key"]),
                ("run", ["pkexec", "zypper", "--non-interactive", "addrepo", "--refresh",
                         base + "home:luisbocanegra.repo"]),
            ]
        steps.append(("run", ["pkexec", "zypper", "--non-interactive", "install", PACKAGE]))
        return steps
    _, url, sha256, name = latest_asset()
    missing = missing_runtime_deps() if d == "arch" else []
    steps = [deps_step(missing)] if missing else []
    steps += [
        ("download", url, sha256, name),
        ("install", name),
    ]
    return steps


def package_latest() -> str | None:
    d = distro()
    if d == "fedora":
        cmd = ["dnf", "repoquery", "--latest-limit", "1", "--qf", "%{version}\n", PACKAGE]
    elif d == "opensuse":
        cmd = ["zypper", "--non-interactive", "info", PACKAGE]
    else:
        return None
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=120).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    if d == "opensuse":
        m = re.search(r"^Version\s*:\s*(\S+)", out, re.M)
        return m.group(1).split("-")[0] if m else None
    lines = [line.strip() for line in out.splitlines() if re.match(r"\d", line.strip())]
    return lines[0] if lines else None


def latest_available() -> str | None:
    if distro() in ("fedora", "opensuse"):
        return package_latest()
    return latest_asset()[0]
