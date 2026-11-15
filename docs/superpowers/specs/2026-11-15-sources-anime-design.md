# New sources, No anime toggle, Match my screen for static only

## Intent

More high-quality landscape wallpapers in both modes, a way to hide anime, and no more empty live grids caused by Match my screen.

## Sources

Live (order = drop-down order; the first is the default):

1. DesktopHut (desktophut.com): only true video items (direct `.mp4`, listing badge shows a resolution); Wallpaper Engine scenes and web packages (`.zip`) are skipped since the video plugin cannot play them. Preview clip: `media.desktophut.com/previews/<slug>-player.mp4`.
2. LiveWallpapers4Free (livewallpapers4free.com): WordPress; direct `/download/<id>/` MP4; listings split into resolution categories.
3. Lively Wallpaper library (livelywallpaper.app): `cdn.livelywallpaper.app/wallpapers/<slug>/download.mp4` (4K), `hd.mp4` (1080p), `preview.mp4`; pages `/live-wallpapers/4k/<n>/`.
4. MoeWalls, MotionBGs (existing).

Static:

1. 4kwallpapers (existing, moved first so it is the default).
2. hdqwalls (hdqwalls.com).
3. WallpaperCave (wallpapercave.com): category pages, images under `/wp/`.
4. Wallhaven (existing).

Dropped after probing: Magnific (403 bot wall, account needed), Vecteezy (watermarked previews, login for clean files), Wallsflow (full download gated behind an ad-blocker check; not worked around), backiee (1080p only), Videezy, wallpapers.com (Cloudflare walls).

## No anime

- A toggle in Settings (General) and the setup wizard, global for both modes. Default off (my call: MoeWalls is mostly anime and would look empty).
- Matching: site category/flag first (DesktopHut and LiveWallpapers4Free anime categories, Wallhaven's anime category), then a keyword list on title + tags (anime, manga, waifu, plus well-known franchise/character names).
- Applied locally in the verdict, like other strict filters; may miss untagged items.

## Match my screen

- Default off (config default `match_screen: False`, wizard starts unchecked).
- Applies to static only; live mode always uses resolution "any".
- Means "fits my screen": at least the screen resolution and the same aspect ratio (2% tolerance), not an exact size match (exact matching left the grid empty).
- Settings/wizard only; the filter popup has no "My screen" option.
- Size checks are rate-limited per source, so switching sources does not stall.

## Left to the builder

Selectors and paging per site, search URLs, keyword list contents.
