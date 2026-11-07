import errno
import os
from pathlib import Path

# FAT/exFAT/NTFS and many network mounts refuse hard links with one of these.
_NO_LINKS = {errno.EPERM, errno.EXDEV, errno.ENOTSUP, errno.EOPNOTSUPP, errno.EMLINK, errno.ENOSYS}


def move_no_replace(src: Path, dest: Path) -> None:
    try:
        os.link(src, dest)
    except FileExistsError:
        raise
    except OSError as e:
        if e.errno not in _NO_LINKS:
            raise
        # Claim the name exclusively, then rename over our own empty placeholder.
        os.close(os.open(dest, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600))
        try:
            os.replace(src, dest)
        except BaseException:
            os.unlink(dest)
            raise
        return
    try:
        os.unlink(src)
    except OSError:
        os.unlink(dest)
        raise
