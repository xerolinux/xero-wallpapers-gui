# New sources + No anime + static-only Match my screen Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add DesktopHut, LiveWallpapers4Free, Lively (live) and hdqwalls, WallpaperCave (static); a global No anime toggle; Match my screen off by default and static only.

**Architecture:** Each site is one `Source` subclass in `xero_wallpapers/sources/` following `fourk.py`/`moewalls.py`. Anime detection is one pure function in a new `xero_wallpapers/anime.py`, applied in `_verdict`. DesktopHut scenes (zip) are skipped at listing time.

**Tech Stack:** Python 3, PyQt6/QML, requests, BeautifulSoup.

**Spec:** `docs/superpowers/specs/2026-11-15-sources-anime-design.md`

## Global Constraints

- No tests directory (deleted at the user's request); verify with live scraper smoke runs and by launching the app.
- Never show or save coded names: titles go through `naming.clean_title`.
- Builtin order in `registry.BUILTINS` sets the default: first static = 4kwallpapers, first live = desktophut.
- No em-dashes anywhere; minimal comments; no dead code.

## Review Focus

- A site changes markup and returns zero items: `search` must return `[]` or raise `SourceError`, never crash.
- DesktopHut scene items slipping through: `resolve_download` raises `SourceError`, never downloads a zip.
- No anime on while browsing MoeWalls: grid may be near empty; auto-paging must stop at `MAX_AUTO_PAGES`, no busy loop.
- Match my screen on, then switch to live: live filters must stay `min_res="any"`.
- Users with `match_screen: true` saved keep their choice (only the default changes).

---

### Task 1: Scrapers (one file each)

**Files:** Create `xero_wallpapers/sources/{desktophut,lw4free,lively,hdqwalls,wallpapercave}.py`

**Interfaces:**
- Produces: `DesktopHutSource`, `LW4FreeSource`, `LivelySource`, `HDQWallsSource`, `WallpaperCaveSource`; `name` = `desktophut`, `livewallpapers4free`, `lively`, `hdqwalls`, `wallpapercave`.
- Each fills `Item.tags` with site categories/tags (so `anime.is_anime` can see an "anime" category), `extra["preview_video"]` for live items, `width`/`height` when known, and `download_url` via `details`/`resolve_download`.

- [ ] Smoke run per source: `search(1, Filters())` returns at least 10 items with clean titles; `search(1, Filters(query="space"))` returns items; `search(2, ...)` differs from page 1; `resolve_download(items[0])` returns a URL that serves media (HEAD 200, video/* or image/*).

### Task 3: No anime

**Files:** Create `xero_wallpapers/anime.py`; modify `config.py`, `ui/controllers.py`, `sources/registry.py`, `sources/wallhaven.py`, `app.py`, `qml/GeneralPage.qml`, `qml/SetupWizard.qml`

**Interfaces:**
- Produces: `anime.is_anime(item: Item) -> bool`; config key `no_anime` (default `False`); `SettingsController.noAnime` property + `noAnimeChanged`; `BrowseController.set_no_anime(on: bool)`; `WallhavenSource(safe, no_anime)` sends `categories=101` when on.

- [ ] `is_anime` true for tags/title containing whole-word `anime`, `manga`, `waifu`, `hentai`, `chibi` or a listed franchise (genshin, honkai, naruto, one piece, luffy, dragon ball, goku, demon slayer, jujutsu, gojo, attack on titan, evangelion, chainsaw man, bleach, sailor moon, my hero academia, spy x family, bocchi, frieren, solo leveling, wuthering waves, azur lane, arknights, blue archive, hatsune miku, vocaloid, pokemon, studio ghibli); false for "landscape", "animal", "animation".
- [ ] `_verdict` returns `"no"` early when the toggle is on and `is_anime(item)`; toggling reloads the grid.
- [ ] Toggle row in Settings General and in the wizard (with a summary row).

### Task 4: Match my screen static only, default off

**Files:** Modify `config.py`, `ui/controllers.py`, `qml/FilterPopup.qml`, `qml/SetupWizard.qml`

- [ ] `match_screen` default `False`.
- [ ] Live mode defaults always use `min_res="any"`; `set_match_screen` changes only static filters.
- [ ] FilterPopup hides the "My screen" option when `browse.mode === "live"`; wizard/settings subtitle says it applies to static wallpapers.

### Task 5: Registry, labels, docs

**Files:** Modify `sources/registry.py`, `ui/models.py`, `README.md`, `PKGBUILD` if sources are listed

- [ ] `BUILTINS = (FourKSource, HDQWallsSource, WallpaperCaveSource, WallhavenSource, DesktopHutSource, LW4FreeSource, LivelySource, MoeWallsSource, MotionBGsSource)`; labels "DesktopHut", "LiveWallpapers4Free", "Lively", "HDQWalls", "WallpaperCave".
- [ ] Launch the app; first source in each mode is the new default; browse each new source.
