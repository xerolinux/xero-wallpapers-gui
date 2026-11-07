import colorsys

from PIL import Image

GREY_SATURATION = 0.15
DARKEST = 0.1
LIGHTEST = 0.93


def palette(image: Image.Image, n: int = 5) -> list[str]:
    small = image.convert("RGB")
    small.thumbnail((128, 128))
    quant = small.quantize(colors=n)
    flat = quant.getpalette() or []
    counts = sorted(quant.getcolors() or [], reverse=True)
    return [
        "#{:02x}{:02x}{:02x}".format(*flat[i * 3 : i * 3 + 3]) for _, i in counts
    ]


def _hue_sat(hexcolor: str) -> tuple[int, float, float]:
    h = hexcolor.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) / 255 for i in (0, 2, 4))
    hue, light, sat = colorsys.rgb_to_hls(r, g, b)
    return round(hue * 360) % 360, sat, light


def _chromatic(sat: float, light: float) -> bool:
    return sat >= GREY_SATURATION and DARKEST < light < LIGHTEST


def hue_matches(item_colors: list[str], hue: int, tol: int = 30, top: int = 3) -> bool:
    # Palettes are ordered by area: the most dominant non-grey colour of the top few decides.
    for hexcolor in item_colors[:top]:
        h, sat, light = _hue_sat(hexcolor)
        if _chromatic(sat, light):
            diff = abs(h - hue) % 360
            return min(diff, 360 - diff) <= tol
    return False
