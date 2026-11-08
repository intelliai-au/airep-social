"""build.py skips existing images, renders missing ones, and flattens legacy PNGs."""

from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

import build
import posts


def _post(slug: str, image: str, template: str | None = "field_note", **kw) -> posts.Post:
    return posts.Post(
        slug=slug,
        date=date(2026, 11, 18),
        slot="field_note",
        linkedin="x https://intelliai.au",
        facebook="x https://intelliai.au",
        image=image,
        template=template,
        fields={"headline": "A *blue* phrase", "rows": [{"label": "A", "text": "b", "tag": "c"}]},
        **kw,
    )


class RenderHtmlTests(unittest.TestCase):
    def test_fields_are_escaped_and_the_phrase_is_emphasised(self) -> None:
        out = build.render_html("field_note", {"headline": "Fish *& chips*", "rows": []})
        self.assertIn("Fish <em>&amp; chips</em>", out)
        self.assertNotIn("{{", out)  # every placeholder resolved (missing ones go blank)
        # Field Notes carry a kicker where the other formats show the logo.
        self.assertIn("<svg", build.render_html("feature", {"rows": [], "columns": []}))

    def test_rows_use_the_row_partial(self) -> None:
        out = build.render_html("field_note", {"rows": [{"label": "L", "text": "T", "tag": "G"}]})
        self.assertIn('<div class="label">L</div>', out)

    def test_foot_link_defaults_per_template_and_can_be_overridden(self) -> None:
        self.assertIn("by AIREP · save this →", build.render_html("field_note", {"rows": []}))
        self.assertIn("intelliai.au/pricing →", build.render_html("price", {"rows": []}))
        out = build.render_html("field_note", {"rows": [], "foot_link": "intelliai.au/websites →"})
        self.assertIn("intelliai.au/websites →", out)
        self.assertNotIn("by AIREP", out)

    def test_website_template_inlines_the_screenshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            site = Path(tmp)
            (site / "shots").mkdir()
            (site / "shots" / "x-phone.png").write_bytes(b"\x89PNG\r\n")
            out = build.render_html(
                "website",
                {"shot": "shots/x-phone.png", "rows": [{"text": "Bookings"}]},
                site_dir=site,
            )
            self.assertIn('src="data:image/png;base64,iVBORw0K', out)
            self.assertIn('class="page site-phone"', out)  # frame defaults to phone
            self.assertIn('<span class="chip">Bookings</span>', out)
            self.assertIn("intelliai.au/websites →", out)
            with self.assertRaisesRegex(build.BuildError, "run shots.py"):
                build.render_html("website", {"shot": "shots/missing.png"}, site_dir=site)

    def test_unknown_template_is_an_error(self) -> None:
        with self.assertRaises(build.BuildError):
            build.render_html("nope", {})


class BuildTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.site = Path(self._tmp.name) / "site"
        self.calls: list[tuple[Path, tuple[int, int]]] = []

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _renderer(self, html: str, out: Path, size: tuple[int, int]) -> None:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(b"png")
        self.calls.append((out, size))

    def test_renders_missing_and_skips_existing(self) -> None:
        a = _post("a", "images/a.png")
        b = _post("b", "images/b.png")
        (self.site / "images").mkdir(parents=True)
        (self.site / "images" / "b.png").write_bytes(b"old")
        written = build.build([a, b], self.site, renderer=self._renderer, log=lambda _: None)
        self.assertEqual([p.name for p in written], ["a.png"])
        self.assertEqual((self.site / "images" / "b.png").read_bytes(), b"old")
        self.assertEqual(self.calls[0][1], (1080, 1080))

    def test_force_rerenders(self) -> None:
        b = _post("b", "images/b.png")
        (self.site / "images").mkdir(parents=True)
        (self.site / "images" / "b.png").write_bytes(b"old")
        build.build([b], self.site, renderer=self._renderer, force=True, log=lambda _: None)
        self.assertEqual((self.site / "images" / "b.png").read_bytes(), b"png")

    def test_force_keeps_a_hand_placed_image_with_no_template(self) -> None:
        # --force used to say the file "is missing" when it plainly existed.
        c = _post("c", "images/c.png", template=None)
        (self.site / "images").mkdir(parents=True)
        (self.site / "images" / "c.png").write_bytes(b"hand")
        logged: list[str] = []
        written = build.build(
            [c], self.site, renderer=self._renderer, force=True, log=logged.append
        )
        self.assertEqual(written, [])
        self.assertEqual((self.site / "images" / "c.png").read_bytes(), b"hand")
        self.assertIn("hand-placed", logged[0])

    def test_pain_is_landscape(self) -> None:
        p = _post("p", "images/p.png", template="pain")
        p.slot = "pain"
        build.build([p], self.site, renderer=self._renderer, log=lambda _: None)
        self.assertEqual(self.calls[0][1], (1080, 565))

    def test_video_posts_need_the_film_in_site(self) -> None:
        v = posts.Post("v", date(2026, 11, 17), "feature", "x", "x", video="video/x.mp4")
        with self.assertRaisesRegex(build.BuildError, "not in site/"):
            build.build([v], self.site, renderer=self._renderer, log=lambda _: None)
        (self.site / "video").mkdir(parents=True)
        (self.site / "video" / "x.mp4").write_bytes(b"mp4")
        self.assertEqual(
            build.build([v], self.site, renderer=self._renderer, log=lambda _: None), []
        )

    def test_legacy_png_is_flattened_to_rgb(self) -> None:
        try:
            from PIL import Image
        except ImportError:  # pragma: no cover - Pillow is in the venv the timer uses
            self.skipTest("Pillow not installed")
        legacy = Path(self._tmp.name) / "legacy"
        legacy.mkdir()
        Image.new("RGBA", (4, 4), (0, 0, 0, 0)).save(legacy / "AIREP-Educational-99.png")
        post = _post("l", "images/legacy/AIREP-Educational-99.png", template=None)
        written = build.build(
            [post], self.site, renderer=None, legacy_dir=legacy, log=lambda _: None
        )
        with Image.open(written[0]) as im:
            self.assertEqual(im.mode, "RGB")
            self.assertEqual(im.getpixel((0, 0)), (255, 255, 255))


if __name__ == "__main__":
    unittest.main()
