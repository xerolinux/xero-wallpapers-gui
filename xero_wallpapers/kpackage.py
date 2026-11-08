import json
import os
import shutil
import tarfile
import tempfile
from pathlib import Path

from . import paths

USER_DIR = paths.DATA_HOME / "plasma" / "wallpapers"
PLUGIN_DIRS = [*(d / "plasma" / "wallpapers" for d in paths.SYSTEM_DATA_DIRS), USER_DIR]
MAX_MEMBERS = 10000
MAX_BYTES = 256 << 20


class KPackageError(Exception):
    pass


def _extract(archive: Path, dest: Path) -> None:
    try:
        with tarfile.open(archive, "r:*") as tar:
            members = tar.getmembers()
            if len(members) > MAX_MEMBERS:
                raise KPackageError("Archive has too many files")
            total = 0
            for m in members:
                if os.path.isabs(m.name) or ".." in Path(m.name).parts:
                    raise KPackageError(f"Unsafe path in archive: {m.name!r}")
                if not (m.isfile() or m.isdir()):
                    raise KPackageError(f"Archive entry is not a plain file or folder: {m.name!r}")
                total += m.size
                if total > MAX_BYTES:
                    raise KPackageError("Archive is too large")
            tar.extractall(dest, members=members, filter="data")
    except (tarfile.TarError, OSError) as e:
        raise KPackageError(f"Couldn't extract {archive.name}: {e}") from e


def _package_root(folder: Path) -> Path:
    if (folder / "metadata.json").is_file():
        return folder
    entries = list(folder.iterdir())
    if len(entries) == 1 and (entries[0] / "metadata.json").is_file():
        return entries[0]
    raise KPackageError("The package has no metadata.json")


def _validate(package: Path, plugin_id: str) -> None:
    try:
        found = json.loads((package / "metadata.json").read_text())["KPlugin"]["Id"]
    except (OSError, ValueError, KeyError, TypeError) as e:
        raise KPackageError(f"Unreadable metadata.json: {e}") from e
    if found != plugin_id:
        raise KPackageError(f"Package is {found!r}, expected {plugin_id!r}")
    if not (package / "contents").is_dir():
        raise KPackageError("The package has no contents folder")


def install(source: Path, plugin_id: str) -> Path:
    target = USER_DIR / plugin_id
    try:
        USER_DIR.mkdir(parents=True, exist_ok=True)
        # A hidden sibling keeps every rename on one filesystem, and Plasma skips it (no metadata.json at its root).
        staging = Path(tempfile.mkdtemp(prefix=f".{plugin_id}.", dir=USER_DIR))
    except OSError as e:
        raise KPackageError(f"Couldn't prepare {USER_DIR}: {e}") from e
    try:
        if source.is_dir():
            package = staging / "package"
            shutil.copytree(source, package)
        else:
            _extract(source, staging / "archive")
            package = _package_root(staging / "archive")
        _validate(package, plugin_id)
        old = staging / "old"
        if target.exists() or target.is_symlink():
            os.rename(target, old)
        try:
            os.rename(package, target)
        except OSError:
            if old.exists() or old.is_symlink():
                os.rename(old, target)
            raise
    except OSError as e:
        raise KPackageError(f"Couldn't install {plugin_id}: {e}") from e
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return target
