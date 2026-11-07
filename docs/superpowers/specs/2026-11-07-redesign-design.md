# Xero Wallpapers: ground-up redesign

Date: 2026-11-07
Status: approved 2026-11-07

## Intent

Xero Wallpapers (today `xero_wallpaper_browser.py`, a 1550-line PyQt6 widgets app) browses, previews and downloads wallpapers and live wallpapers. It is being rebuilt from scratch with a new UI, so it feels native on KDE Plasma, is fast and hard to crash, and gains the features below.

The look is fixed by mockup **#22 "Immersive · Frost"**:
- `docs/designs/gifs/22-immersive-frost.gif`: main walkthrough.
- `docs/designs/gifs/22-immersive-frost-extras.gif`: first-run screen, sort/filter, SVWR update pill, About.
- `docs/designs/src/engine.html?d=22`: the live HTML mockup. It is the visual reference for spacing, components and flows.

Treat the mockup as the spec for layout and behavior, not pixel-exact styling. Real Kirigami/Breeze components replace hand-drawn ones where they exist.

**Always dark: follows your Plasma colour scheme when it's dark; light schemes are replaced by Layan** (decided). At startup the app reads the active colours from `kdeglobals` (`[Colors:Window] BackgroundNormal`). On Plasma with a dark scheme it sets nothing and lets the KDE platform theme drive Kirigami, so it looks exactly like the rest of the desktop. With a light scheme, or outside Plasma (no KDE scheme counts as light), it points `KDE_COLOR_SCHEME_PATH` at `Layan.colors` (the installed copy from `color-schemes/` in the XDG data dirs, otherwise the bundled `xero_wallpapers/data/Layan.colors`), sets a matching QPalette and the Qt dark colour-scheme hint. The `org.kde.desktop` controls style is always used, because Kirigami's built-in fallback theme is light-only. Breeze Dark is the fallback icon theme, and outside Plasma in the Layan fallback it is the icon theme. Use `Kirigami.Theme` colours everywhere, with no hard-coded Frost colours. There is no light mode. Only #22's layout, spacing and flows carry over.

## Goals

1. **Rebuild in PyQt6 + QML/Kirigami** with the #22 layout:
   - Hero banner ("Wallpaper of the day" / "Featured live wallpaper") at the top.
   - "Trending" grid below it with image-only cards and overlay captions. The row above the grid holds the "Trending" heading, the active filter chips and, right-aligned, a **source drop-down** (every enabled source for the current mode, custom sources included; Wallpapers lists static sources, Live lists live sources), then Sort and Filter.
   - A floating bottom dock: Wallpapers, Live (hidden until enabled), Library, Search, Settings, About.
   - Details in a centered sheet; Settings in a dialog.
2. **Static sources only on launch.** Live wallpapers are off by default.
3. **Live Wallpapers toggle (Settings > Live Wallpapers).**
   - It is disabled while Smart Video Wallpaper Reborn (SVWR) is missing, and an **Install** button is shown instead.
   - Once SVWR is detected, the toggle unlocks.
   - Turning it on reveals the Live dock entry, the live sources and the live download folder.
4. **SVWR install and update:** on Arch, the verified GitHub release archive installed with `kpackagetool6` (never AUR); Fedora and openSUSE use their repo packages. Details below.
5. **Metadata** in the details sheet.
   - Static: resolution, aspect ratio, format, file size, source, uploader, views/favourites, upload date, tags, colour palette.
   - Live: resolution, duration, frame rate, codec/container, file size, source, upload date, tags.
   - Show whatever each source provides; hide fields it doesn't.
6. **Crop, resize and upscale** editor for static images.
   - Aspect presets: Original, 16:9, 16:10, 21:9, 32:9, 9:16, plus a draggable crop box.
   - Target resolution list, from FHD to 8K, plus custom.
   - Upscaler choice: Lanczos, Real-ESRGAN, Real-ESRGAN Anime.
   - Denoise/sharpen sliders and a summary (source, crop, output, scale).
   - "Save copy" and an optional "Set as wallpaper after saving".
   - AI path: Real-ESRGAN at the smallest of ×2/×3/×4 that meets or exceeds the target, then a Lanczos fit to the exact size. Pure downscale or small changes use Lanczos only.
   - The original is kept; the copy is named `<name>-<W>x<H>.<ext>`.
7. **Fullscreen coverflow** (3D tilt style).
   - Opens on the current grid list at the current item.
   - ← → browse; **Space downloads and sets** the centred wallpaper (static via Plasma; live via SVWR); I toggles info; Esc exits.
   - The blurred current wallpaper fills the background, with reflections, title and metadata under the centred cover, and a key hint bar.
   - Live wallpapers animate: only the centre cover plays, muted and looping, once it has settled for 300 ms; side covers stay stills, and the video stops and unloads as soon as the cover moves or the coverflow closes, so at most one video ever plays. It uses the lightest URL available: the low-res preview clip on MoeWalls and MotionBGs detail pages (`Item.extra["preview_video"]`, never the download URL), else the download URL. Details are fetched off the GUI thread and cached per item; with no preview the still stays.
8. **Sort and filter** on the browse grid.
   - Sort: Popular, Newest, Resolution (high→low, low→high), File size.
   - Filter pop-up: tags, colour (8 swatches matched by dominant colour), minimum resolution (Any, 1440p+, 4K+, 8K, and "My screen (W × H)"), aspect ratio (Any, 16:9, 16:10, 21:9, 32:9, Ultra-wide), then Clear and **Apply filters** (no result count: only loaded pages could be counted, so any number would be wrong). Active filters show as removable chips. The tag list refreshes as Wallhaven tags arrive in the background.
   - Filters are strict and always verified locally, even when the server filtered too (Wallhaven's colour match is loose). Colour: the most dominant non-grey colour among an item's top 3 palette colours must be within 30° of the swatch hue; items without colours get a palette computed from the thumbnail off the GUI thread (cached by URL). Size and ratio: "My screen" means exactly the native size; other ratios match within 2%; Ultra-wide is an aspect of 2.3 or more. While a size or ratio filter is on, items of unknown size are hidden; sources whose detail pages carry the size (4K Wallpapers, MoeWalls, MotionBGs) get those pages fetched in the background (one thread, 30 a minute), and matches join the grid. Sources that never report size (custom sources without size fields) ignore size filters, and the pop-up says so. A small "Checking sizes..." / "Checking colours..." label sits by the heading while checks are pending. While a filter is active and the grid has fewer than 24 wallpapers, up to 4 more pages load automatically.
   - Every click target in the pop-up and in anything floating over the grid (dock, update pill, editor page) is a real control or sits on a press-absorbing area, so clicks never fall through to the wallpaper card underneath. Modal cards (About, setup wizard) absorb presses on their content with a TapHandler that takes the exclusive grab only when nothing else did, because a TapHandler in the content only grabs passively and would let the press reach the grid; rows with tap handlers inside dialogs (Tidy names) do the same.
   - Wallpapers and Live keep separate filters. Live sources list no colours or tags and few sizes, so entering Live for the first time starts from the default filters (Match my screen applies); switching back restores the static filters. Only the search text is shared.
   - Pass filters to the source API when it supports them (e.g. Wallhaven `q`, `colors`, `atleast`, `resolutions`, `ratios`, `sorting`; Ultra-wide sends `ratios=21x9,32x9`). Otherwise filter and sort locally on what has loaded.
9. **User-added sources (Settings > Sources).**
   - List the built-in and custom sources, each with an enable toggle.
   - "Add source" form: name, type (Static/Live), search URL template with `{query}` and `{page}`, parser (JSON API or HTML page), and an item path or selector.
   - A "Test" button runs one fetch and shows how many items it found.
   - Custom sources are stored in config and appear alongside built-ins.
10. **Separate download folders** for wallpapers and live wallpapers (Settings > Downloads). The live folder is greyed out until Live Wallpapers is on. A "Skip duplicates" toggle lives there too. Originals are always kept after upscaling (no toggle).
11. **First-launch setup wizard** (replaces a simple welcome popup). It runs once on first launch and is skippable. It is reopened from a **"Run setup again" button in the Settings dialog header (top right, next to the "Settings" title)**, not About. Every choice it makes also lives in Settings. Steps, with Back and Next on each:
    1. **Welcome:** what the app is, plus the AI disclosure: "This app was built with the help of AI coding tools. It's open source, so you can read every line on GitHub."
    2. **Wallpapers folder:** a folder picker.
    3. **Live wallpapers:** detects SVWR. Shows **Install** (same verified flow and consent rules as Settings) or "Installed". Then an "Enable live wallpapers" switch and a live folder picker. "Skip for now" keeps the app static-only.
    4. **Preferences:** the preferences in Goal 15.
    5. **Done:** a summary, then into the app.
    Nothing is saved until Finish, except an SVWR install the user explicitly started.
    Look (user requirement): a polished, guided wizard in the spirit of Plasma's Welcome Center: large centred window, left step rail with numbered steps and progress, big headings and icons, image-led welcome hero, card-style controls (folder cards, status cards, preference cards), primary Next/Finish, animated page transitions. The About popup gets the same treatment (hero band, overlapping logo, version chip, link cards).
12. **About** dialog: the app icon centred, name, version, licence (GPL-3.0), a one-line description, links to `https://github.com/xerolinux/xero-wallpapers-gui` and `https://discord.xerolinux.xyz`, and a "Built with AI help" line.
13. **Library**: Wallpapers and Live tabs showing the two download folders, with a "Current" badge on the wallpaper in use, an "Open folder" button, and set/edit/delete actions on each item.
14. **Responsive and crash-resistant** (see Constraints).
15. **Preferences** (decided by the user; the SVWR update check is NOT a preference: it always runs on every launch when SVWR is installed; all in Settings, and shown in the wizard's Preferences step):
    - **Safe content only** (default on): Wallhaven `purity=100`. When off, `purity=110` (SFW + sketchy). NSFW is never offered.
    - **Match my screen** (default on): the default resolution filter is "My screen": only wallpapers whose size equals the primary screen's native size (from `QScreen.size() * devicePixelRatio`) exactly. It is stored as `min_res = "<W>x<H>"`. Wallhaven gets `resolutions=WxH`. Items of unknown size are hidden until their size is known (see Sort and filter). Users can still change the filter per session.
    - **Skip duplicates** (default on).
    - **Thumbnail cache size**: 250 MB, 500 MB (default) or 1 GB, plus a "Clear cache" button.
18. **Automatic wallpaper change with transitions** (user request; static wallpapers only). The app ships its own Plasma wallpaper plugin, **Xero Slideshow** (KPackage id `org.xerolinux.wallpapers.slideshow`, QML, `X-Plasma-API-Minimum-Version` 6.0), because Plasma's built-in slideshow only crossfades and has no transition settings. It keeps working when the app is closed and runs no background process.
    - Config group `General` keys (the app writes them through Plasma scripting): `SlideFolder` (absolute path, the Wallpapers download folder), `SlideInterval` (seconds, 60 to 604800), `SlideOrder` (0 random, 1 by name), `Transition` ("fade", "slide", "wipe", "grow", "zoom", "pixelate", "wave", "random"), `TransitionDuration` (ms, 500 to 3000, default 1200), `FillMode` (Image fill mode, default PreserveAspectCrop).
    - Transitions are GPU shaders (ShaderEffect / MultiEffect) active only during the switch; images load at screen size; folder changes are picked up without restart; one image per screen, same order on all screens.
    - Installation: the Arch package installs it system-wide to `/usr/share/plasma/wallpapers/org.xerolinux.wallpapers.slideshow/`. When it's missing (running from source, other distros), the app installs it per user with `kpackagetool6 -t Plasma/Wallpaper -i` (update with `-u` when the bundled version is newer). No root.
    - Settings > General only (NOT in the setup wizard, which stays basic; user decision): "Change wallpaper automatically" (default off); interval slider with presets (5 min, 15 min, 30 min, 1 h, 3 h, 6 h, 12 h, 24 h) plus "Custom" minutes (1 to 10080); order Random or By name; transition picker with a small live preview; transition duration slider. Turning it on while a live wallpaper is set asks first. Setting a single wallpaper from the app switches back to a static image and the toggle reflects the real Plasma state. Disabled with "Needs KDE Plasma" outside Plasma.
17. **Thumbnails show the whole image** (user request): grid cards, library tiles and coverflow covers scale images to fit. The home hero banner is the exception: it fills edge-to-edge (cropped), as before (no cropping). Spare space is filled with a blurred, dimmed copy of the same image so cards keep their shape.
16. **Tidy names** (user-approved). Coded names are replaced with readable ones everywhere a wallpaper is named: grid/detail titles, coverflow caption and saved file names.
    - Wallhaven list results carry no tags, so titles are filled in the background: tags are fetched per item from `/api/v1/w/<id>` for visible items, rate-limited (at most 40 requests/minute, Wallhaven's unauthenticated limit is 45), cached on disk by id, and the title updates in place when they arrive.
    - Wallhaven: title from the top 3-4 tags in title case (e.g. "Clouds Sky Anime Girl"). File name `<slug>-<W>x<H>.<ext>` (e.g. `clouds-sky-anime-girl-2074x1166.jpg`). Fallback: "<Category> wallpaper <short id>".
    - Never show or save coded names (e.g. "w8", "jqwel", "yqkl97"). If no friendly name is available, the title is empty and the UI shows only the source name; files are saved as `<source>-<W>x<H>.<ext>`. The "<Category> wallpaper <short id>" fallback is dropped.
    - MoeWalls, MotionBGs, 4K Wallpapers, custom sources: strip site noise ("Live Wallpaper", "Wallpaper", "4K", "HD", "Free Download", site names, trailing ids/resolution codes), collapse whitespace, title case.
    - Library "Tidy names" action for existing files: scans a folder, proposes old -> new names (Wallhaven `wallhaven-<id>` files get tags via the Wallhaven API; others get the noise-stripping rules; files it can't improve are left alone), shows the list for confirmation, then renames. Never overwrites (clash gets -2, -3). If a renamed file is the current static or live wallpaper, it is re-applied with the new path so the desktop doesn't break.
19. **Hide duplicates app-wide** (user request: "hide duplicates by default app wide, make it very very very strict"). A duplicate is the same picture regardless of source, resolution, file name, format or re-compression.
    - Fingerprints (`xero_wallpapers/dupes.py`): exact identity first (source + normalised page URL, normalised download URL, source id), then a 64-bit dHash and a 64-bit aHash of the thumbnail. Strict match: both Hamming distances <= 6 AND aspect ratios within 3% (the item's real size when known), so a slight crop never matches. Near-flat images get no fingerprint and never match. Computed off the GUI thread from the thumbnail bytes the thumb pipeline caches (concurrent requests for one thumbnail share one fetch), and cached on disk in `fingerprints.db` under the cache dir, by normalised URL and for local files by (path, size, mtime).
    - Browse grid and coverflow: later items that duplicate an earlier loaded item (across pages and sources, per mode) are hidden; a later copy with more pixels replaces the earlier one in place. Each batch waits up to 300 ms for its fingerprints so duplicates don't flash; items still unknown then are shown and removed in place once known. Exact-id duplicates are hidden immediately.
    - Downloads ("Skip duplicates", default on): before saving, a fingerprint match in the target Library folder means no download; the app says "Already in your Library" and Set uses the existing file. When no fingerprint is available (and for videos without one) the old name check still applies.
    - Library: one entry per picture (prefers the current wallpaper, then the largest image, then the largest file). A "Remove duplicates" button in the header lists the extra copies with checkboxes and moves the selected ones to the Trash, with Undo.
    - Live: browse items use their thumbnail; library videos use the grabbed first frame or the thumbnail they were downloaded with.
    - "Hide duplicates" in Settings > General (default on) controls browse and Library hiding.

## Non-goals

- Distro-agnostic packaging (planned later; just don't block it).
- Non-Plasma desktops. Plasma 6 is the target. The old GNOME/XFCE/sway setters may stay as a basic fallback for static images, but no new work goes into them.
- Accounts, favourites sync, or cloud features.
- Video editing or trimming of live wallpapers.

## Anti-goals (a failure even if it works)

- Clutter: Windows-style toolbars, ribbons, dense menus. Keep the calm #22 layout.
- A UI that freezes on network, disk, thumbnail or upscale work.
- A crash or traceback from one source's bad HTML or JSON taking down the app.
- Insecure shortcuts: no `curl | sh`, no disabled TLS verification, no running the whole app as root, no storing passwords.
- X11-only behaviour. Wayland is the default.

## Constraints

- **Stack:** Python 3 + PyQt6 6.12 (system Qt 6.12) + QML with Kirigami 6.31 (`org.kde.kirigami`). All of these are already present on the dev machine. Plasma is 6.8.
- **Wayland first:** remove the current forced `QT_QPA_PLATFORM=xcb` and `LIBGL_ALWAYS_SOFTWARE` hacks. Let Qt pick the platform.
- **Responsiveness:**
  - No blocking calls on the GUI thread.
  - Network: `QNetworkAccessManager` or a bounded worker pool, with timeouts, retries and cancellation when a page or view changes.
  - Thumbnails: async loading, a size-capped disk cache, and an in-memory LRU.
  - Grid: virtualised (`GridView`), never one widget per item.
- **Crash resistance:**
  - Each source's fetch and parse runs isolated and catches its own errors, which show as an inline message on the grid, not a dialog storm.
  - Atomic config writes (temp file, then rename).
  - Downloads go to `.part` and are renamed on completion.
  - A global exception hook logs to `~/.cache/xero-wallpaper-browser/log.txt`.
- **Paths** stay where they are: config at `~/.config/xero-wallpaper-browser/config.json` and cache at `~/.cache/xero-wallpaper-browser/`. Migrate existing `static_download_dir` / `live_download_dir`.
- **Packaging:** keep a PKGBUILD that installs to `/usr/lib/xero-wallpaper-browser/` with a launcher, `.desktop` file and icon. Add new runtime deps (`kirigami`, `qt6-declarative`), drop unused ones (OpenCV can likely go if Qt Multimedia makes video thumbnails), and bump to 2.0.0.

## SVWR install, detection, update (decided)

Source: https://github.com/luisbocanegra/plasma-smart-video-wallpaper-reborn

**Plugin id:** `luisbocanegra.smart.video.wallpaper.reborn`. It needs Plasma ≥ 6.0.

**Detection:**
- Look for the plugin's `metadata.json` in `/usr/share/plasma/wallpapers/<id>/` (distro package) and `~/.local/share/plasma/wallpapers/<id>/` (archive install).
- The installed version is `KPlugin.Version` in that file.

**Install route by distro** (decided; read `/etc/os-release` `ID` / `ID_LIKE`, all in one function):
- **Arch and Arch-based (never AUR):**
  1. Fetch the latest GitHub release from the API (`releases/latest`). Its asset `plasma-smart-video-wallpaper-reborn-vX.Y.Z.tar.gz` is the packaged plugin, the same one the KDE Store installs.
  2. Download it to the cache and verify its SHA-256 against the asset's `digest` field. On a mismatch, delete it and stop.
  3. Install with `kpackagetool6 -t Plasma/Wallpaper -i <archive>` into `~/.local/share/plasma/wallpapers/`. No root needed.
  4. The runtime deps the README lists for this route are `qt6-multimedia qt6-multimedia-ffmpeg`. If they're missing, offer `pkexec pacman -S --needed qt6-multimedia qt6-multimedia-ffmpeg`.
- **Fedora:** `pkexec dnf install -y plasma-smart-video-wallpaper-reborn`. The README notes this package isn't maintained by the author and may lag.
- **openSUSE:** the author's OBS repo package `plasma-smart-video-wallpaper-reborn`, added per the OBS install instructions linked in the README. Ask before adding the repo.
- **Any other distro:** the same verified-archive + `kpackagetool6` route as Arch.

**Install UI:**
- Stream each step's output into the progress card on the Live Wallpapers page.
- On failure, show the last lines and a "Copy log" button.
- Afterwards, re-run detection and unlock the toggle.

**Update:**
- Archive installs: on every launch (always; not configurable), compare the installed version with the latest GitHub release tag.
  - If it's newer, show the home-screen pill "Smart Video Wallpaper Reborn X.Y.Z is available" with an **Update** button.
  - Update = download and verify the new archive, then `kpackagetool6 -t Plasma/Wallpaper -u <archive>`.
- Package installs: the pill appears the same way when the repo has a newer version. Update runs the distro's upgrade of that one package via `pkexec`.
- After installing or updating, restart only the wallpaper if possible. Otherwise tell the user to log out and in.

**Setting a live wallpaper:**
- Switch each desktop's wallpaper plugin to the SVWR id via Plasma's scripting interface (`qdbus6 org.kde.plasmashell /PlasmaShell org.kde.PlasmaShell.evaluateScript`).
- Write `VideoUrls` in the `Wallpaper/<id>/General` config group.
- `VideoUrls` is a JSON string: an array of `{filename, enabled, duration, customDuration, playbackRate, alternativePlaybackRate, loop, dayNightPhase}`, as written by the plugin's `config.qml`.
- Builder: confirm whether `filename` is a `file://` URL or a plain path by setting one through the plugin's own settings UI, then reading `~/.config/plasma-org.kde.plasma.desktop-appletsrc`.

**Setting a static wallpaper** on Plasma: `plasma-apply-wallpaperimage <path>`.

## Real-ESRGAN (my call)

Use the portable `realesrgan-ncnn-vulkan` release binary and models from the upstream GitHub releases (xinntao/Real-ESRGAN-ncnn-vulkan).
- Download it on first use of the AI upscaler into `~/.local/share/xero-wallpapers/realesrgan/`, after asking the user.
- Upstream publishes no checksums, so the app pins one release (latest at build time, v0.2.5.0) and hard-codes the SHA-256 of its Linux asset. The builder computes that hash once while implementing.
- A download whose hash doesn't match is deleted and the AI path refuses to run; Lanczos stays available. Moving to a newer release is a deliberate code change that updates the pinned hash.
- This keeps the app distro-agnostic, in line with the SVWR decision.
- AI upscaling is offered only when a dedicated GPU is detected (`vulkaninfo --summary` reports `PHYSICAL_DEVICE_TYPE_DISCRETE_GPU`). Without one, Real-ESRGAN options are disabled with "Needs a dedicated GPU" and never run, because running it on an integrated GPU crashed the iGPU driver (user report).
- If Vulkan is unavailable or the run fails, fall back to Lanczos and say so.
- Run it in a subprocess with tiling and a progress readout. Cancelling kills the process.

## Sources (carried over)

Port the existing scrapers: Wallhaven (API), 4K Wallpapers (HTML), MoeWalls (HTML), MotionBGs (HTML). DuskLinux and DesktopHut are already gone from the code.
- Each source implements one interface: `search(query, page, filters) -> items`, `resolve_download(item) -> url`, and `metadata(item) -> dict`.
- Built-ins and user-defined sources share that interface.
- User-defined sources use a generic adapter. Its form and config schema hold:
  - an item list path (JSON) or item selector (HTML);
  - per-field paths or selectors relative to each item: title, thumbnail URL, and download-or-detail URL are required; resolution, tags, author and file size are optional;
  - an optional "detail page download selector". When set, the adapter opens the item's detail URL and reads the real download link from it, the same way the built-in HTML scrapers do.
  The "Test" button runs one search and shows the item count plus the first item's mapped fields, so mistakes are visible.

## Browsing scope (my call, from the mockup)

The grid shows **one source at a time**: the source drop-down above the grid picks it. Search, sort and filters apply to the selected source; filters go to its API when it supports them, otherwise they apply locally to the loaded pages. There is no merged feed.

## Left to the builder

- Python ↔ QML split (models, controllers), project file layout, and whether to keep a single entry script.
- Colour extraction method for palettes and the colour filter (e.g. k-means on the thumbnail).
- Exact cache sizes, timeouts and retry counts.
- How "Wallpaper of the day" and "Featured live" are chosen (e.g. top of today's toplist).
- Test strategy. Source parsers, the config migration, the SVWR version comparison and the upscale size maths should all have unit tests.
- Kirigami component choices that match the mockup.

## Calls I made (please check)

- Version 2.0.0.
- The Real-ESRGAN distribution approach above.
- Config/cache paths kept for migration.
- `pkexec` used for the package-manager steps.
- OpenCV is dropped if Qt Multimedia can make video thumbnails.
- One source at a time in the grid (no merged feed).
- Custom source form fields and the optional detail-page step, as described under Sources.
- Real-ESRGAN pinned to one release with a hard-coded SHA-256; no unverified binary ever runs.
