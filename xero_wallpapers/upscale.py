import functools
import hashlib
import math
import os
import re
import shutil
import subprocess
import zipfile
from pathlib import Path, PurePosixPath
from typing import Callable, Literal
from urllib.parse import urlparse

from PIL import Image, ImageFilter

from . import net, paths
from .fsutil import move_no_replace

Model = Literal["realesrgan-x4plus", "realesrgan-x4plus-anime"]
# The x4plus models only run at their native factor; smaller plans are met by a Lanczos fit afterwards.
MODEL_SCALES: dict[str, tuple[int, ...]] = {"realesrgan-x4plus": (4,), "realesrgan-x4plus-anime": (4,)}
BINARY = "realesrgan-ncnn-vulkan"
CHUNK = 64 * 1024
VULKANINFO_TIMEOUT = 5
MAX_AI_PIXELS = 200_000_000
NO_DISCRETE_GPU = "Needs a dedicated GPU"
NO_VULKANINFO = "Install vulkan-tools to enable AI upscaling"
_PERCENT = re.compile(r"(\d+(?:\.\d+)?)%")
_GPU_HEADER = re.compile(r"^GPU(\d+):")


class UpscaleError(Exception):
    pass


def _ratio(ratio: str | None) -> float | None:
    if not ratio or ratio == "Original":
        return None
    w, h = (float(p) for p in ratio.split(":"))
    return w / h


def crop_rect(src_w: int, src_h: int, ratio: str | None) -> tuple[int, int, int, int]:
    r = _ratio(ratio)
    if r is None:
        return 0, 0, src_w, src_h
    if src_w / src_h > r:
        w, h = min(src_w, round(src_h * r)), src_h
    else:
        w, h = src_w, min(src_h, round(src_w / r))
    return (src_w - w) // 2, (src_h - h) // 2, w, h


def plan_upscale(crop_w: int, crop_h: int, out_w: int, out_h: int) -> tuple[int | None, str]:
    if out_w <= crop_w and out_h <= crop_h:
        return None, "No upscale needed, Lanczos only"
    scale = next((s for s in (2, 3, 4) if crop_w * s >= out_w and crop_h * s >= out_h), 4)
    if crop_w * scale < out_w or crop_h * scale < out_h:
        return scale, f"Needs more than ×4: Real-ESRGAN ×4, then Lanczos to {out_w} × {out_h}"
    return scale, f"Needs ×{scale}: Real-ESRGAN runs at ×4, then Lanczos fits to {out_w} × {out_h}"


def ai_input_size(crop_w: int, crop_h: int, out_w: int, out_h: int) -> tuple[int, int] | None:
    if not ai_too_large(crop_w, crop_h):
        return crop_w, crop_h
    # None when even a quarter-output input would make the ×4 result exceed the cap.
    if ai_too_large(min(crop_w, math.ceil(out_w / 4)), min(crop_h, math.ceil(out_h / 4))):
        return None
    f = math.sqrt(MAX_AI_PIXELS / (16 * crop_w * crop_h))
    return max(1, math.floor(crop_w * f)), max(1, math.floor(crop_h * f))


def ai_too_large(in_w: int, in_h: int) -> bool:
    return in_w * in_h * 16 > MAX_AI_PIXELS


def lanczos(img: Image.Image, out_w: int, out_h: int) -> Image.Image:
    w, h = img.size
    x, y, cw, ch = crop_rect(w, h, f"{out_w}:{out_h}")
    if (cw, ch) != (w, h):
        img = img.crop((x, y, x + cw, y + ch))
    return img.resize((out_w, out_h), Image.Resampling.LANCZOS)


def denoise(img: Image.Image, amount: float) -> Image.Image:
    if amount <= 0:
        return img
    return Image.blend(img, img.filter(ImageFilter.MedianFilter(3)), min(amount, 1.0))


def sharpen(img: Image.Image, amount: float) -> Image.Image:
    if amount <= 0:
        return img
    return img.filter(ImageFilter.UnsharpMask(radius=2, percent=round(200 * min(amount, 1.0)), threshold=2))


@functools.cache
def gpu_probe() -> tuple[int | None, str]:
    # Real-ESRGAN hangs integrated GPUs hard enough to trigger driver ring resets, so AI needs a discrete one.
    try:
        result = subprocess.run(["vulkaninfo", "--summary"], capture_output=True, text=True, timeout=VULKANINFO_TIMEOUT)
    except OSError:
        return None, NO_VULKANINFO
    except subprocess.SubprocessError:
        return None, NO_DISCRETE_GPU
    if result.returncode != 0:
        return None, NO_DISCRETE_GPU
    current = None
    for line in result.stdout.splitlines():
        if m := _GPU_HEADER.match(line):
            current = int(m.group(1))
        elif current is not None and "PHYSICAL_DEVICE_TYPE_DISCRETE_GPU" in line:
            return current, ""
    return None, NO_DISCRETE_GPU


def discrete_gpu_index() -> int | None:
    return gpu_probe()[0]


def output_name(src: Path, w: int, h: int) -> Path:
    base = f"{src.stem}-{w}x{h}"
    path = src.with_name(base + ".png")
    n = 2
    while path.exists():
        path = src.with_name(f"{base}-{n}.png")
        n += 1
    return path


def publish(part: Path, src: Path, w: int, h: int) -> Path:
    try:
        while True:
            dest = output_name(src, w, h)
            try:
                move_no_replace(part, dest)
                return dest
            except FileExistsError:
                continue
    finally:
        part.unlink(missing_ok=True)


def parse_progress(text: str) -> float | None:
    hits = _PERCENT.findall(text)
    return float(hits[-1]) / 100 if hits else None


def _fetch(url: str, dest: Path, progress: Callable[[int, int], None], limit: int) -> None:
    if urlparse(url).scheme != "https" or urlparse(url).hostname != "github.com":
        raise UpscaleError("refusing to download Real-ESRGAN from outside github.com")
    resp = net.SESSION.get(url, stream=True, timeout=net.TIMEOUT)
    try:
        resp.raise_for_status()
        if urlparse(resp.url).scheme != "https":
            raise UpscaleError("Real-ESRGAN download was redirected off https")
        total = int(resp.headers.get("Content-Length") or 0)
        if total > limit:
            raise UpscaleError("Real-ESRGAN download is larger than expected")
        done = 0
        with open(dest, "wb") as f:
            for chunk in resp.iter_content(CHUNK):
                done += len(chunk)
                if done > limit:
                    raise UpscaleError("Real-ESRGAN download is larger than expected")
                f.write(chunk)
                progress(done, total)
    finally:
        resp.close()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def _unsafe(info: zipfile.ZipInfo) -> bool:
    name = PurePosixPath(info.filename)
    is_link = (info.external_attr >> 16) & 0o170000 == 0o120000
    return name.is_absolute() or ".." in name.parts or "\\" in info.filename or is_link


class RealEsrgan:
    PINNED = {
        "tag": "v0.2.5.0",
        "asset": "realesrgan-ncnn-vulkan-20220424-ubuntu.zip",
        "size": 46931474,
        "sha256": "e5aa6eb131234b87c0c51f82b89390f5e3e642b7b70f2b9bbe95b6a285a40c96",
        "binary_sha256": "22c2296a39b40cc43ac92615c827ab6d4b60b7142e8cee59f718e3f8e2cdbda9",
    }

    @property
    def root(self) -> Path:
        return Path(paths.DATA_DIR) / "realesrgan"

    @property
    def binary(self) -> Path:
        return self.root / BINARY

    def _wanted(self) -> list[str]:
        return [BINARY] + [f"models/{m}{ext}" for m in MODEL_SCALES for ext in (".bin", ".param")]

    def available(self) -> bool:
        return (
            self.binary.is_file()
            and os.access(self.binary, os.X_OK)
            and all((self.root / name).is_file() for name in self._wanted()[1:])
        )

    def url(self) -> str:
        return (
            "https://github.com/xinntao/Real-ESRGAN/releases/download/"
            f"{self.PINNED['tag']}/{self.PINNED['asset']}"
        )

    def ensure(self, progress: Callable[[int, int], None]) -> Path:
        if self.available():
            return self.binary
        self.root.mkdir(parents=True, exist_ok=True)
        archive = self.root / "download.zip"
        try:
            _fetch(self.url(), archive, progress, self.PINNED["size"])
            if archive.stat().st_size != self.PINNED["size"] or _sha256(archive) != self.PINNED["sha256"]:
                raise UpscaleError("Real-ESRGAN download failed verification")
            self._clear()
            self._extract(archive)
            self.verify()
        except BaseException:
            self._clear()
            raise
        finally:
            archive.unlink(missing_ok=True)
        return self.binary

    def verify(self):
        try:
            ok = _sha256(self.binary) == self.PINNED["binary_sha256"]
        except OSError:
            ok = False
        if not ok:
            self._clear()
            raise UpscaleError("Real-ESRGAN binary failed verification")

    def _clear(self):
        for name in (BINARY, "models"):
            target = self.root / name
            if target.is_dir() and not target.is_symlink():
                shutil.rmtree(target, ignore_errors=True)
            else:
                target.unlink(missing_ok=True)

    def _extract(self, archive: Path):
        try:
            with zipfile.ZipFile(archive) as z:
                infos = z.infolist()
                if any(_unsafe(i) for i in infos):
                    raise UpscaleError("Real-ESRGAN archive contains unsafe paths")
                members = {i.filename: i for i in infos}
                wanted = self._wanted()
                missing = [n for n in wanted if n not in members]
                if missing:
                    raise UpscaleError(f"Real-ESRGAN archive is missing {', '.join(missing)}")
                # The binary goes last so available() only turns true once everything is in place.
                for name in wanted[1:] + wanted[:1]:
                    dest = self.root / name
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.unlink(missing_ok=True)
                    with z.open(members[name]) as src, open(dest, "xb") as out:
                        shutil.copyfileobj(src, out, CHUNK)
        except zipfile.BadZipFile as e:
            raise UpscaleError(f"Real-ESRGAN archive is damaged: {e}") from e
        self.binary.chmod(0o755)

    def command(self, inp: str, out: str, scale: int, model: Model) -> list[str]:
        if scale not in MODEL_SCALES.get(model, ()):
            raise ValueError(f"{model} cannot run at ×{scale}")
        gpu = discrete_gpu_index()
        if gpu is None:
            raise UpscaleError("Real-ESRGAN needs a dedicated GPU")
        # ncnn defaults to GPU 0, which is often the integrated one on hybrid machines.
        return [
            str(self.binary), "-i", inp, "-o", out, "-n", model, "-s", str(scale),
            "-m", str(self.root / "models"), "-f", "png", "-g", str(gpu),
        ]
