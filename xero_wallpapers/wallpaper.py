import json
import os
import shutil
import subprocess
import weakref
from pathlib import Path

from PyQt6.QtCore import QUrl

from . import svwr

TIMEOUT = 30

_swaybg: subprocess.Popen | None = None

listeners: list[weakref.WeakMethod] = []


class WallpaperError(Exception):
    pass


def run(cmd: list[str]) -> None:
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT)
    except (OSError, subprocess.SubprocessError) as e:
        raise WallpaperError(f"{cmd[0]} failed: {e}") from e
    if result.returncode != 0:
        raise WallpaperError((result.stderr or "").strip() or f"{cmd[0]} exited with {result.returncode}")


def is_plasma() -> bool:
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").upper()
    return "KDE" in desktop or "PLASMA" in desktop


def _static_commands(path: str) -> list[list[str]]:
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").upper()
    uri = Path(path).as_uri()
    if is_plasma():
        return [["plasma-apply-wallpaperimage", path]]
    if "GNOME" in desktop:
        return [
            ["gsettings", "set", "org.gnome.desktop.background", key, uri]
            for key in ("picture-uri", "picture-uri-dark")
        ]
    if "XFCE" in desktop:
        return [[
            "xfconf-query", "-c", "xfce4-desktop",
            "-p", "/backdrop/screen0/monitor0/workspace0/last-image", "-s", path,
        ]]
    if "MATE" in desktop:
        return [["gsettings", "set", "org.mate.background", "picture-filename", path]]
    if "CINNAMON" in desktop:
        return [["gsettings", "set", "org.cinnamon.desktop.background", "picture-uri", uri]]
    if "HYPRLAND" in desktop or "SWAY" in desktop or "WAYLAND" in desktop:
        return [["swaybg", "-i", path, "-m", "fill"]]
    if shutil.which("feh"):
        return [["feh", "--bg-fill", path]]
    if shutil.which("nitrogen"):
        return [["nitrogen", "--set-zoom-fill", path]]
    return []


def _replace_swaybg(cmd: list[str]) -> None:
    global _swaybg
    if _swaybg is not None:
        _swaybg.terminate()
        try:
            _swaybg.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _swaybg.kill()
    else:
        # A swaybg left over from an earlier run would keep drawing over the new one.
        try:
            subprocess.run(["pkill", "-x", "swaybg"], capture_output=True, timeout=TIMEOUT)
        except (OSError, subprocess.SubprocessError):
            pass
    try:
        _swaybg = subprocess.Popen(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True
        )
    except OSError as e:
        _swaybg = None
        raise WallpaperError(f"swaybg failed: {e}") from e


def _notify(kind: str) -> None:
    for ref in list(listeners):
        callback = ref()
        if callback is None:
            listeners.remove(ref)
        else:
            callback(kind)


def evaluate_script(script: str) -> None:
    run(["qdbus6", "org.kde.plasmashell", "/PlasmaShell", "org.kde.PlasmaShell.evaluateScript", script])


def set_static(path: Path) -> None:
    cmds = _static_commands(str(path))
    if not cmds:
        raise WallpaperError(f"Couldn't find a wallpaper tool for this desktop. Set it manually: {path}")
    if cmds[0][0] == "swaybg":
        _replace_swaybg(cmds[0])
    else:
        for cmd in cmds:
            run(cmd)
    _notify("static")


def live_script(video: Path) -> str:
    videos = json.dumps([
        {
            "filename": QUrl.fromLocalFile(str(video)).toString(),
            "enabled": True,
            "duration": 0,
            "customDuration": 0,
            "playbackRate": 0.0,
            "alternativePlaybackRate": 0.0,
            "loop": False,
            "dayNightPhase": 4,
        }
    ])
    plugin = json.dumps(svwr.ID)
    return (
        f"var videos = {json.dumps(videos)};\n"
        "var ds = desktops();\n"
        "for (var i = 0; i < ds.length; i++) {\n"
        "    var d = ds[i];\n"
        f"    d.wallpaperPlugin = {plugin};\n"
        f'    d.currentConfigGroup = ["Wallpaper", {plugin}, "General"];\n'
        '    d.writeConfig("VideoUrls", videos);\n'
        "}\n"
    )


def set_live(video: Path) -> None:
    if svwr.installed_version() is None:
        raise WallpaperError("Smart Video Wallpaper Reborn is not installed")
    evaluate_script(live_script(video))
    _notify("live")
