import json
import os
import shutil
import subprocess
import weakref
from pathlib import Path

from PyQt6.QtCore import QUrl
from PyQt6.QtDBus import QDBus, QDBusConnection, QDBusMessage

from . import library, svwr

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
    bus = QDBusConnection.sessionBus()
    if not bus.isConnected():
        raise WallpaperError("Couldn't reach the session D-Bus")
    message = QDBusMessage.createMethodCall("org.kde.plasmashell", "/PlasmaShell", "org.kde.PlasmaShell",
                                            "evaluateScript")
    message.setArguments([script])
    reply = bus.call(message, QDBus.CallMode.Block, TIMEOUT * 1000)
    if reply.type() == QDBusMessage.MessageType.ErrorMessage:
        raise WallpaperError(reply.errorMessage() or reply.errorName())


def desktops_script(plugin: str, values: dict) -> str:
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


def static_script(path: Path | None) -> str:
    values = {"Image": Path(path).as_uri()} if path else {}
    return desktops_script(library.IMAGE_PLUGIN, values)


def set_static(path: Path) -> None:
    if is_plasma():
        evaluate_script(static_script(path))
        _notify("static")
        return
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
    return desktops_script(svwr.ID, {"VideoUrls": videos})


def set_live(video: Path) -> None:
    if svwr.installed_version() is None:
        raise WallpaperError("Smart Video Wallpaper Reborn is not installed")
    evaluate_script(live_script(video))
    _notify("live")
