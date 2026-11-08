"""Render every post's missing PNG from templates/ with Playwright; flatten legacy PNGs into site/.

Idempotent: an image that already exists under site/ is left alone unless --force.
"""

from __future__ import annotations

import argparse
import base64
import html
import re
import sys
from collections.abc import Callable
from pathlib import Path

import posts as posts_mod

ROOT = Path(__file__).resolve().parent
TEMPLATES_DIR = ROOT / "templates"
SITE_DIR = ROOT / "site"
LEGACY_DIR = ROOT / "assets" / "legacy"

# CSS pixels; Playwright renders at device scale 2, so 1080 -> 2160. The pain series
# is the one landscape format (plan doc: 2160 x 1130).
DEFAULT_SIZE = (1080, 1080)
SIZES: dict[str, tuple[int, int]] = {"pain": (1080, 565)}
DEVICE_SCALE = 2

Renderer = Callable[[str, Path, tuple[int, int]], None]

# A template's placeholders that get a value when the post names none, so the AIREP
# formats keep their footer and a Friday website post can point the same template at
# intelliai.au/websites instead.
TEMPLATE_DEFAULTS: dict[str, dict[str, str]] = {
    "field_note": {"foot_link": "by AIREP · save this →"},
    "price": {"foot_link": "intelliai.au/pricing →"},
    "website": {"foot_link": "intelliai.au/websites →", "frame": "phone"},
}

# Fields that name an image under site/ (a screenshot from shots.py). Playwright renders
# from a string, so the file is inlined as a data URI rather than linked.
IMAGE_FIELDS = frozenset({"shot"})

_PLACEHOLDER = re.compile(r"\{\{(\w+)\}\}")
_EMPHASIS = re.compile(r"\*(.+?)\*")


class BuildError(RuntimeError):
    """A post cannot be rendered; the message names the post."""


def _value(value: object) -> str:
    """Escape a field; `*phrase*` becomes the one blue italic phrase."""
    text = html.escape(str(value), quote=False)
    return _EMPHASIS.sub(r"<em>\1</em>", text)


def _columns(columns: list[str]) -> str:
    return "".join(f"<th>{_value(c)}</th>" for c in columns)


def _rows(template: str, rows: list[dict], templates_dir: Path) -> str:
    row_src = (templates_dir / f"{template}.row.html").read_text(encoding="utf-8").strip()
    out = []
    for row in rows:
        ctx = {k: _value(v) for k, v in row.items()}
        out.append(_PLACEHOLDER.sub(lambda m, c=ctx: c.get(m.group(1), ""), row_src))
    return "".join(out)


def _data_uri(rel: str, site_dir: Path) -> str:
    """``data:image/png;base64,…`` for a PNG under site/; a missing file is a BuildError."""
    path = site_dir / rel
    if not path.is_file():
        raise BuildError(f"screenshot {rel} is not in site/ (run shots.py)")
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def render_html(
    template: str,
    fields: dict,
    templates_dir: Path = TEMPLATES_DIR,
    site_dir: Path = SITE_DIR,
) -> str:
    """The self-contained HTML for one image: CSS, logo and screenshots inlined, fields
    substituted."""
    path = templates_dir / f"{template}.html"
    if not path.exists():
        raise BuildError(f"no template {template!r} in {templates_dir}")
    src = path.read_text(encoding="utf-8")
    ctx: dict[str, str] = {
        "base_css": (templates_dir / "base.css").read_text(encoding="utf-8"),
        "logo_svg": (templates_dir / "assets" / "intelli-ai.svg").read_text(encoding="utf-8"),
        **TEMPLATE_DEFAULTS.get(template, {}),
    }
    for key, value in fields.items():
        if key == "rows":
            ctx[key] = _rows(template, list(value or []), templates_dir)
        elif key == "columns":
            ctx[key] = _columns(list(value or []))
        elif key in IMAGE_FIELDS:
            ctx[key] = _data_uri(str(value), site_dir)
        else:
            ctx[key] = _value(value)
    return _PLACEHOLDER.sub(lambda m: ctx.get(m.group(1), ""), src)


class PlaywrightRenderer:
    """Screenshots HTML with one Chromium kept open across images."""

    def __init__(self) -> None:
        self._pw = None
        self._browser = None

    def __call__(self, html_text: str, out: Path, size: tuple[int, int]) -> None:
        if self._browser is None:
            from playwright.sync_api import sync_playwright

            self._pw = sync_playwright().start()
            self._browser = self._pw.chromium.launch()
        page = self._browser.new_page(
            viewport={"width": size[0], "height": size[1]}, device_scale_factor=DEVICE_SCALE
        )
        try:
            page.set_content(html_text, wait_until="load")
            page.evaluate("document.fonts.ready")  # system fonts settle before the shot
            out.parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(out), full_page=False, type="png")
        finally:
            page.close()

    def close(self) -> None:
        if self._browser is not None:
            self._browser.close()
        if self._pw is not None:
            self._pw.stop()


def flatten_legacy(src: Path, dst: Path) -> None:
    """Copy a legacy PNG as opaque RGB: LinkedIn and Facebook reject transparent images."""
    from PIL import Image

    with Image.open(src) as im:
        rgba = im.convert("RGBA")
        flat = Image.new("RGB", rgba.size, (255, 255, 255))
        flat.paste(rgba, mask=rgba.getchannel("A"))
        dst.parent.mkdir(parents=True, exist_ok=True)
        flat.save(dst, "PNG", optimize=True)


def build(
    post_list: list[posts_mod.Post],
    site_dir: Path = SITE_DIR,
    templates_dir: Path = TEMPLATES_DIR,
    renderer: Renderer | None = None,
    legacy_dir: Path = LEGACY_DIR,
    force: bool = False,
    log: Callable[[str], None] = print,
) -> list[Path]:
    """Render what is missing and return the paths written."""
    written: list[Path] = []
    for post in post_list:
        if post.is_video:
            if not (site_dir / post.video).exists():
                raise BuildError(f"{post.slug}: film {post.video} is not in site/")
            continue
        out = site_dir / post.image
        if out.exists() and not force:
            log(f"skip    {post.image} (exists)")
            continue
        if post.image.startswith("images/legacy/"):
            src = legacy_dir / Path(post.image).name
            if not src.exists():
                raise BuildError(f"{post.slug}: legacy PNG {src.name} is not in assets/legacy/")
            flatten_legacy(src, out)
            log(f"legacy  {post.image}")
        elif post.template:
            if renderer is None:
                raise BuildError(f"{post.slug}: needs rendering but no renderer was given")
            renderer(
                render_html(post.template, post.fields, templates_dir, site_dir),
                out,
                _size(post),
            )
            log(f"render  {post.image} ({post.template})")
        elif out.exists():
            # Only reachable with --force: a hand-placed PNG has nothing to re-render from.
            log(f"keep    {post.image} (hand-placed, no template to re-render)")
            continue
        else:
            raise BuildError(f"{post.slug}: {post.image} is missing and the post has no template")
        written.append(out)
    return written


def _size(post: posts_mod.Post) -> tuple[int, int]:
    return SIZES.get(post.slot, DEFAULT_SIZE)


def main(argv: list[str] | None = None) -> int:
    """CLI: `python build.py [--force] [--only SLUG] [--html DIR]`."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--force", action="store_true", help="re-render images that exist")
    parser.add_argument("--only", metavar="SLUG", help="build one post")
    parser.add_argument("--html", metavar="DIR", help="also dump each post's HTML here")
    args = parser.parse_args(argv)

    post_list = posts_mod.load_posts()
    if args.only:
        post_list = [p for p in post_list if p.slug == args.only]
        if not post_list:
            print(f"no post {args.only!r}", file=sys.stderr)
            return 2
    if args.html:
        html_dir = Path(args.html)
        html_dir.mkdir(parents=True, exist_ok=True)
        for post in post_list:
            if post.template:
                (html_dir / f"{post.slug}.html").write_text(
                    render_html(post.template, post.fields), encoding="utf-8"
                )
    renderer = PlaywrightRenderer()
    try:
        written = build(post_list, renderer=renderer, force=args.force)
    finally:
        renderer.close()
    print(f"{len(written)} image(s) written, {len(post_list) - len(written)} untouched")
    return 0


if __name__ == "__main__":
    sys.exit(main())
