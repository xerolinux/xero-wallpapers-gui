import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from . import library, svwr
from .wallpaper import WallpaperError, evaluate_script, is_plasma, run

ID = "org.xerolinux.wallpapers.slideshow"
# Source checkouts ship the plugin next to the package; the Arch package installs it system-wide instead.
_SOURCE_PLUGIN = Path(__file__).resolve().parent.parent / "plasma" / ID
BUNDLED = _SOURCE_PLUGIN if (_SOURCE_PLUGIN / "metadata.json").is_file() else Path("/usr/share/plasma/wallpapers") / ID
UNSUPPORTED_CHARS = "#?%"
FOLDER_PROBLEM = "Folder names containing #, ? or % aren't supported by the slideshow. Pick or rename the folder."
ORDERS = {"random": 0, "name": 1}
TRANSITIONS = ("fade", "slide", "wipe", "grow", "zoom", "pixelate", "wave", "random")
MIN_MINUTES, MAX_MINUTES = 1, 10080
MIN_MS, MAX_MS = 500, 3000
MIN_SECONDS = 60
FILL_CROP = 2

# One worker so Plasma scripts apply in the order the user changed things.
EXECUTOR = ThreadPoolExecutor(max_workers=1)


def available() -> tuple[bool, str]:
    return (True, "") if is_plasma() else (False, "Needs KDE Plasma")


def clamp_minutes(minutes: int) -> int:
    return max(MIN_MINUTES, min(MAX_MINUTES, int(minutes)))


def clamp_ms(ms: int) -> int:
    return max(MIN_MS, min(MAX_MS, int(ms)))


def _desktops(plugin: str, values: dict) -> str:
    lines = "".join(f"    d.writeConfig({json.dumps(k)}, {json.dumps(v)});\n" for k, v in values.items())
    plugin = json.dumps(plugin)
    return (
        "var ds = desktops();\n"
        "for (var i = 0; i < ds.length; i++) {\n"
        "    var d = ds[i];\n"
        f"    d.wallpaperPlugin = {plugin};\n"
        f'    d.currentConfigGroup = ["Wallpaper", {plugin}, "General"];\n'
        f"{lines}"
        "}\n"
    )


def slideshow_script(folder: Path, minutes: int, order: str, transition: str, duration_ms: int) -> str:
    if order not in ORDERS:
        raise ValueError(f"unknown order {order!r}")
    if transition not in TRANSITIONS:
        raise ValueError(f"unknown transition {transition!r}")
    return _desktops(ID, {
        "SlideFolder": str(folder),
        "SlideInterval": max(MIN_SECONDS, clamp_minutes(minutes) * 60),
        "SlideOrder": ORDERS[order],
        "Transition": transition,
        "TransitionDuration": clamp_ms(duration_ms),
        "FillMode": FILL_CROP,
    })


def static_script(path: Path | None) -> str:
    values = {"Image": Path(path).as_uri()} if path else {}
    return _desktops(library.IMAGE_PLUGIN, values)


def folder_problem(folder: Path | str) -> str:
    return FOLDER_PROBLEM if any(c in str(folder) for c in UNSUPPORTED_CHARS) else ""


def _version(package: Path) -> str | None:
    if not package.is_dir():
        return None
    try:
        return str(json.loads((package / "metadata.json").read_text())["KPlugin"]["Version"])
    except (OSError, ValueError, KeyError, TypeError):
        return "0"


def bundled_version() -> str | None:
    return _version(BUNDLED)


def _installed() -> tuple[Path, str] | None:
    for root in svwr.PLUGIN_DIRS:
        version = _version(root / ID)
        # "0" means unreadable metadata: Plasma can't load that copy either.
        if version not in (None, "0"):
            return root, version
    return None


def ensure_plugin() -> None:
    bundled = bundled_version()
    # Plasma prefers the user copy, so a stale one would shadow a newer system install.
    user = _version(svwr.PLUGIN_DIRS[-1] / ID)
    if user is not None:
        if bundled and svwr.is_newer(bundled, user):
            try:
                run(["kpackagetool6", "-t", "Plasma/Wallpaper", "-u", str(BUNDLED)])
            except WallpaperError:
                # kpackagetool6 can't upgrade a copy whose metadata is broken; replace it instead.
                run(["kpackagetool6", "-t", "Plasma/Wallpaper", "-r", ID])
                run(["kpackagetool6", "-t", "Plasma/Wallpaper", "-i", str(BUNDLED)])
    elif _installed() is None:
        if bundled is None:
            raise WallpaperError("The Xero Slideshow plugin isn't bundled with this copy of the app")
        run(["kpackagetool6", "-t", "Plasma/Wallpaper", "-i", str(BUNDLED)])


def enable(folder: Path, minutes: int, order: str, transition: str, duration_ms: int) -> None:
    problem = folder_problem(folder)
    if problem:
        raise WallpaperError(problem)
    ensure_plugin()
    evaluate_script(slideshow_script(folder, minutes, order, transition, duration_ms))


def disable_to_static(path: Path | None = None) -> None:
    evaluate_script(static_script(path))


def parse_state(text: str) -> dict:
    desktops: dict[str, dict] = {}
    settings: dict[tuple[str, str], dict] = {}
    target = None
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("["):
            target = None
            m = library.CONTAINMENT.fullmatch(line)
            if m:
                cid, rest = m.groups()
                if not rest:
                    target = desktops.setdefault(cid, {})
                else:
                    g = library.WALLPAPER_GROUP.fullmatch(rest)
                    if g:
                        target = settings.setdefault((cid, g.group(1)), {})
            continue
        key, sep, value = line.partition("=")
        if target is not None and sep:
            target[key] = value
    # Panels are containments too; only desktops carry an activity.
    plugins = {cid: d.get("wallpaperplugin", "") for cid, d in desktops.items() if d.get("activityId")}
    for wanted in (ID, svwr.ID):
        if wanted in plugins.values():
            chosen = wanted
            break
    else:
        chosen = next(iter(plugins.values()), "")
    group = next((settings.get((cid, chosen), {}) for cid, p in plugins.items() if p == chosen), {})
    try:
        interval = int(group.get("SlideInterval", 0))
    except ValueError:
        interval = 0
    return {"plugin": chosen, "interval": interval, "folder": group.get("SlideFolder", "")}


def current_state() -> dict:
    try:
        return parse_state(library.appletsrc_text())
    except OSError:
        return parse_state("")
