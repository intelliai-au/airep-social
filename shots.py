"""Screenshot and film the client sites in sites.yaml for the Friday website posts (shots.py).

Runs outside the writer's sandbox (it needs the public web): author.py calls it before a
writing run, and it can be run by hand. Idempotent in effect, not in bytes: every run
retakes every shot, so a site that changed shows its current self.

    shots.py                 # every site: phone + laptop PNGs; a scroll film if missing
    shots.py --films always  # re-film too (a film is a few MB in git, so not monthly)
    shots.py --only gripswich --films never
"""

from __future__ import annotations

import argparse
import math
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
SITES_YAML = ROOT / "sites.yaml"
SITE_DIR = ROOT / "site"
SHOTS_DIR = SITE_DIR / "shots"
VIDEO_DIR = SITE_DIR / "video"

# CSS viewports. The phone is an iPhone-14-class 390 x 844; the laptop a 16:10 1440 x 900.
# Both at device scale 2, so the PNGs are 780 x 1688 and 2880 x 1800 and stay sharp when
# the website template shows them at a third of that.
PHONE = (390, 844)
LAPTOP = (1440, 900)
DEVICE_SCALE = 2

# The scroll film: frames are screenshots, not a screencast, so the text stays crisp.
# 30 fps for FILM_SECONDS: a one-second hold, a smooth scroll of SCROLL_SCREENS screens,
# a one-second hold. LinkedIn and Facebook both want at least three seconds and an even
# pixel size (yuv420p); 780 x 1688 is both.
FILM_FPS = 30
FILM_SECONDS = 12
SCROLL_SCREENS = 2.5
HOLD_SECONDS = 1.0

# mpv encodes (Playwright's bundled ffmpeg has no H.264); the same libx264 settings as
# the AIREP film rig (airep tools/filming/social/cut.py), and movflags writes the index
# first so Buffer and the networks can start playing before the whole file is down.
MPV_ARGS = (
    "--ovc=libx264",
    "--ovcopts=preset=slow,crf=20,profile=high,level=4.0",
    "--vf=format=yuv420p",
    "--ofopts=movflags=+faststart",
    "--no-audio",
    "--msg-level=all=error",
)


@dataclass(frozen=True)
class Site:
    """One site the Friday posts may show."""

    slug: str
    name: str
    url: str
    display_url: str
    sector: str = ""
    plan: str = ""
    facts: tuple[str, ...] = ()
    pages: tuple[str, ...] = field(default_factory=tuple)  # extra paths, e.g. /prices/
    hide: tuple[str, ...] = ()  # CSS selectors hidden before the shot (transient notices)

    @property
    def phone_shot(self) -> str:
        """Path under site/ of the phone screenshot."""
        return f"shots/{self.slug}-phone.png"

    @property
    def laptop_shot(self) -> str:
        """Path under site/ of the laptop screenshot."""
        return f"shots/{self.slug}-laptop.png"

    @property
    def film(self) -> str:
        """Path under site/ of the phone scroll-through film."""
        return f"video/website_{self.slug}_scroll.mp4"


def load_sites(path: Path = SITES_YAML) -> list[Site]:
    """The sites in sites.yaml, in order."""
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    out = []
    for row in raw.get("sites") or []:
        out.append(
            Site(
                slug=str(row["slug"]),
                name=str(row["name"]),
                url=str(row["url"]),
                display_url=str(row.get("display_url") or row["url"]),
                sector=str(row.get("sector", "")),
                plan=str(row.get("plan", "")),
                facts=tuple(str(f) for f in row.get("facts") or ()),
                pages=tuple(str(p) for p in row.get("pages") or ()),
                hide=tuple(str(h) for h in row.get("hide") or ()),
            )
        )
    return out


def page_slug(site: Site, path: str) -> str:
    """``gripswich-prices`` for an extra page ``/prices/``."""
    tail = path.strip("/").replace("/", "-") or "home"
    return f"{site.slug}-{tail}"


# Jump, never glide: a site with `scroll-behavior: smooth` would otherwise still be
# moving when the shot is taken (the first GRIPswich shot caught the page mid-scroll).
_JUMP = "document.documentElement.style.scrollBehavior = 'auto'; window.scrollTo(0, %s)"


def _settle(page) -> None:
    """Let fonts, lazy images and entrance animations finish before a shot."""
    page.wait_for_load_state("networkidle")
    page.evaluate("document.fonts.ready")
    # Lazy-loaded images and reveal-on-scroll sections only appear once they have been
    # in view, so walk the whole page a screen at a time (a single jump to the bottom
    # would skip the middle), then back to the top for the first frame.
    height = int(page.evaluate("document.documentElement.scrollHeight"))
    step = int(page.viewport_size["height"] * 0.8)
    for y in range(0, height, step):
        page.evaluate(_JUMP % y)
        page.wait_for_timeout(150)
    page.evaluate(_JUMP % "0")
    page.wait_for_timeout(1000)


def shoot(site: Site, browser, out_dir: Path, *, films: str = "missing", log=print) -> list[Path]:
    """Phone and laptop PNGs for the site (and each extra page), plus the scroll film.

    *films* is ``always``, ``missing`` (the default: film only when site/video/ lacks it,
    since every new film is a few MB more in git) or ``never``.
    """
    written: list[Path] = []
    want_film = films == "always" or (films == "missing" and not (out_dir / site.film).is_file())
    targets = [(site.url, site.slug)] + [
        (site.url.rstrip("/") + p, page_slug(site, p)) for p in site.pages
    ]
    for url, slug in targets:
        for label, size in (("phone", PHONE), ("laptop", LAPTOP)):
            ctx = browser.new_context(
                viewport={"width": size[0], "height": size[1]},
                device_scale_factor=DEVICE_SCALE,
                is_mobile=label == "phone",
                has_touch=label == "phone",
                locale="en-AU",
                timezone_id="Australia/Brisbane",
                color_scheme="light",
            )
            try:
                page = ctx.new_page()
                page.goto(url, wait_until="load", timeout=60_000)
                if site.hide:
                    # A "busy tonight" bar or a cookie notice is true today and stale by
                    # the time the post runs; the card shows the site, not the day.
                    page.add_style_tag(
                        content=", ".join(site.hide) + " { display: none !important; }"
                    )
                _settle(page)
                out = out_dir / "shots" / f"{slug}-{label}.png"
                out.parent.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(out), full_page=False, type="png")
                written.append(out)
                log(f"shot    {out.relative_to(out_dir)}")
                if want_film and label == "phone" and slug == site.slug:
                    film = out_dir / site.film
                    _film(page, film)
                    written.append(film)
                    log(f"film    {film.relative_to(out_dir)}")
            finally:
                ctx.close()
    return written


def _film(page, out: Path) -> None:
    """Frame-by-frame scroll-through of the current page, encoded with mpv."""
    total = FILM_FPS * FILM_SECONDS
    hold = int(FILM_FPS * HOLD_SECONDS)
    moving = total - 2 * hold
    height = page.evaluate("document.documentElement.scrollHeight")
    viewport = page.viewport_size["height"]
    distance = min(SCROLL_SCREENS * viewport, max(height - viewport, 0))
    with tempfile.TemporaryDirectory(prefix="shots-") as tmp:
        frames = Path(tmp)
        for i in range(total):
            if i < hold:
                y = 0.0
            elif i >= hold + moving:
                y = distance
            else:
                t = (i - hold) / max(moving - 1, 1)
                y = distance * (0.5 - 0.5 * math.cos(t * math.pi))  # ease in and out
            page.evaluate(_JUMP % f"{y:.1f}")
            page.screenshot(path=str(frames / f"{i:04d}.png"), full_page=False, type="png")
        page.evaluate(_JUMP % "0")
        out.parent.mkdir(parents=True, exist_ok=True)
        encode_frames(frames, out)


def encode_frames(frames: Path, out: Path, fps: int = FILM_FPS) -> None:
    """Encode ``frames/0000.png…`` into an H.264 mp4 with mpv."""
    mpv = shutil.which("mpv")
    if not mpv:
        raise RuntimeError("mpv is not installed; it encodes the scroll films")
    tmp_out = out.with_suffix(".part.mp4")
    cmd = [mpv, f"mf://{frames}/*.png", f"--mf-fps={fps}", f"--o={tmp_out}", *MPV_ARGS]
    proc = subprocess.run(cmd, text=True, capture_output=True)
    if proc.returncode != 0 or not tmp_out.exists():
        raise RuntimeError(f"mpv failed: {(proc.stderr or proc.stdout).strip()[-400:]}")
    tmp_out.replace(out)


def main(argv: list[str] | None = None) -> int:
    """CLI: ``shots.py [--only SLUG] [--films always|missing|never] [--out DIR]``."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--only", metavar="SLUG", help="one site")
    parser.add_argument(
        "--films", choices=("always", "missing", "never"), default="missing", help="scroll films"
    )
    parser.add_argument("--out", type=Path, default=SITE_DIR, help="write under this site/ dir")
    parser.add_argument("--sites", type=Path, default=SITES_YAML)
    args = parser.parse_args(argv)

    sites = load_sites(args.sites)
    if args.only:
        sites = [s for s in sites if s.slug == args.only]
        if not sites:
            print(f"no site {args.only!r} in {args.sites}", file=sys.stderr)
            return 2
    from playwright.sync_api import sync_playwright

    failures = 0
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            for site in sites:
                try:
                    shoot(site, browser, args.out, films=args.films)
                except Exception as exc:  # noqa: BLE001 - one site down must not stop the rest
                    failures += 1
                    print(f"FAILED  {site.slug}: {type(exc).__name__}: {exc}", file=sys.stderr)
        finally:
            browser.close()
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
