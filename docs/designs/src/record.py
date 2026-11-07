#!/usr/bin/env python3
"""Record each design walkthrough to docs/designs/gifs/<slug>.gif.

Usage: record.py [--extras] [design numbers...]   (default: 1-36)
--extras records the add-on walkthrough (first-run, sort & filter, SVWR update, about)
to <slug>-extras.gif.
"""
import asyncio
import base64
import shutil
import sys
import tempfile
from pathlib import Path

from playwright.async_api import async_playwright

SRC = Path(__file__).resolve().parent
OUT = SRC.parent / "gifs"
ENGINE = SRC / "engine.html"
PARALLEL = 4
FPS = 12
WIDTH = 960


async def record(browser, num, sem, extras):
    async with sem:
        ctx = await browser.new_context(viewport={"width": 1280, "height": 800})
        page = await ctx.new_page()
        await page.goto(f"{ENGINE.as_uri()}?d={num}{'&extras' if extras else ''}")
        await page.wait_for_function("window.__ready")
        slug = await page.evaluate("DESIGN.slug")
        tmp = Path(tempfile.mkdtemp(prefix=f"xw{num}-"))
        frames = []
        cdp = await ctx.new_cdp_session(page)

        async def on_frame(ev):
            path = tmp / f"f{len(frames):05d}.jpg"
            path.write_bytes(base64.b64decode(ev["data"]))
            frames.append((path, ev["metadata"]["timestamp"]))
            try:
                await cdp.send("Page.screencastFrameAck", {"sessionId": ev["sessionId"]})
            except Exception:
                pass  # late frame after the context closed

        cdp.on("Page.screencastFrame", lambda ev: asyncio.ensure_future(on_frame(ev)))
        await cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 88, "maxWidth": 1280, "maxHeight": 800})
        await page.evaluate("window.__go()")
        await page.wait_for_function("window.__done", timeout=120_000, polling=250)
        await asyncio.sleep(0.8)
        await cdp.send("Page.stopScreencast")
        err = await page.evaluate("window.__err || null")
        await ctx.close()
        if err:
            print(f"[{num}] script error: {err}", file=sys.stderr)

        concat = tmp / "list.txt"
        lines = []
        for k, (path, ts) in enumerate(frames):
            nxt = frames[k + 1][1] if k + 1 < len(frames) else ts + 1.0
            lines.append(f"file '{path}'\nduration {max(nxt - ts, 0.001):.4f}")
        lines.append(f"file '{frames[-1][0]}'")
        concat.write_text("\n".join(lines))
        gif = OUT / f"{slug}{'-extras' if extras else ''}.gif"
        vf = (f"fps={FPS},scale={WIDTH}:-1:flags=lanczos,split[a][b];"
              "[a]palettegen=stats_mode=diff:max_colors=192[p];"
              "[b][p]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle")
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(concat),
            "-vf", vf, "-loop", "0", str(gif))
        await proc.wait()
        shutil.rmtree(tmp)
        print(f"[{num}] {gif.name} {gif.stat().st_size / 1e6:.1f} MB, {len(frames)} frames")


async def main():
    args = sys.argv[1:]
    extras = "--extras" in args
    nums = [int(a) for a in args if a != "--extras"] or list(range(1, 37))
    OUT.mkdir(exist_ok=True)
    sem = asyncio.Semaphore(PARALLEL)
    async with async_playwright() as p:
        browser = await p.chromium.launch(args=["--force-color-profile=srgb"])
        await asyncio.gather(*(record(browser, n, sem, extras) for n in nums))
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
