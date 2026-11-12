"""The content files load, follow the rules, and bad ones are refused with a reason."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import posts

GOOD = """\
date: 2026-11-18
slot: field_note
image: images/x.png
template: field_note
linkedin: |
  One line.
  Two lines.
  https://intelliai.au
facebook: |
  One line.
  https://intelliai.au
"""


def _write(tmp: Path, name: str, body: str) -> Path:
    path = tmp / name
    path.write_text(body, encoding="utf-8")
    return path


class RealContentTests(unittest.TestCase):
    def test_every_content_file_loads(self) -> None:
        loaded = posts.load_posts()
        self.assertGreaterEqual(len(loaded), 6)
        self.assertEqual([p.date for p in loaded], sorted(p.date for p in loaded))
        for post in loaded:
            self.assertTrue(post.asset)
            self.assertIn("intelliai.au", post.caption("facebook"))

    def test_linkedin_caption_carries_hashtags_facebook_does_not(self) -> None:
        post = posts.load_posts()[0]
        self.assertTrue(post.caption("linkedin").endswith("#ERP #SmallBusiness #Australia"))
        self.assertNotIn("#", post.caption("facebook"))


class ValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_good_file(self) -> None:
        post = posts.parse_post(_write(self.tmp, "2026-11-18-x.yaml", GOOD))
        self.assertEqual(post.slug, "2026-11-18-x")
        self.assertEqual(post.slot, "field_note")
        self.assertFalse(post.is_video)

    def test_slot_must_match_the_weekday(self) -> None:
        body = GOOD.replace("2026-11-18", "2026-11-19")  # a Thursday
        with self.assertRaisesRegex(posts.ContentError, "Thu 19 Nov allows"):
            posts.parse_post(_write(self.tmp, "2026-11-19-x.yaml", body))

    def test_friday_is_the_website_slot_with_its_own_hashtags(self) -> None:
        body = GOOD.replace("2026-11-18", "2026-11-20").replace("slot: field_note", "slot: website")
        post = posts.parse_post(_write(self.tmp, "2026-11-20-x.yaml", body))
        self.assertEqual(post.slot, "website")
        self.assertTrue(post.caption("linkedin").endswith("#WebDesign #SmallBusiness #Australia"))
        wrong = GOOD.replace("2026-11-18", "2026-11-20")  # a field_note on a Friday
        with self.assertRaisesRegex(posts.ContentError, "Fri 20 Nov allows \\['website'\\]"):
            posts.parse_post(_write(self.tmp, "2026-11-20-x.yaml", wrong))

    def test_christmas_wednesday_is_refused(self) -> None:
        body = GOOD.replace("2026-11-18", "2026-12-23")
        with self.assertRaisesRegex(posts.ContentError, "no post"):
            posts.parse_post(_write(self.tmp, "2026-12-23-x.yaml", body))

    def test_caption_rules(self) -> None:
        too_long = GOOD.replace("One line.\n  Two lines.\n", "a\n  b\n  c\n  d\n")
        with self.assertRaisesRegex(posts.ContentError, "max 4"):
            posts.parse_post(_write(self.tmp, "2026-11-18-x.yaml", too_long))
        no_link = GOOD.replace("  https://intelliai.au\nfacebook", "facebook")
        with self.assertRaisesRegex(posts.ContentError, "exactly once"):
            posts.parse_post(_write(self.tmp, "2026-11-18-x.yaml", no_link))
        inline_tag = GOOD.replace("Two lines.", "Two #lines.")
        with self.assertRaisesRegex(posts.ContentError, "hashtags go in"):
            posts.parse_post(_write(self.tmp, "2026-11-18-x.yaml", inline_tag))

    def test_hashtags_are_a_list_of_single_words(self) -> None:
        # A bare string is iterated letter by letter and would post "#E #R #P".
        bare = GOOD.replace("template: field_note", "template: field_note\nhashtags: ERP")
        with self.assertRaisesRegex(posts.ContentError, "must be a list"):
            posts.parse_post(_write(self.tmp, "2026-11-18-x.yaml", bare))
        for bad in ('["#ERP"]', '["Small Business"]', "[42]", '[""]'):
            body = GOOD.replace("template: field_note", f"template: field_note\nhashtags: {bad}")
            with self.assertRaisesRegex(posts.ContentError, "one word without the #", msg=bad):
                posts.parse_post(_write(self.tmp, "2026-11-18-x.yaml", body))
        none = GOOD.replace("template: field_note", "template: field_note\nhashtags: []")
        post = posts.parse_post(_write(self.tmp, "2026-11-18-x.yaml", none))
        self.assertNotIn("#", post.caption("linkedin"))
        good = GOOD.replace("template: field_note", "template: field_note\nhashtags: [ERP, AU_ERP]")
        post = posts.parse_post(_write(self.tmp, "2026-11-18-x.yaml", good))
        self.assertTrue(post.caption("linkedin").endswith("#ERP #AU_ERP"))

    def test_exactly_one_asset(self) -> None:
        both = GOOD.replace("template: field_note", "video: video/x.mp4")
        with self.assertRaisesRegex(posts.ContentError, "exactly one"):
            posts.parse_post(_write(self.tmp, "2026-11-18-x.yaml", both))

    def test_asset_paths_stay_under_site_images_and_video(self) -> None:
        # build.py writes site/<image> (with --force from author.py, outside the writer's
        # sandbox), so a path that climbs out of site/ would overwrite a file anywhere;
        # a stray "site/" prefix would build site/site/... and 404 on Pages at push time.
        for bad in (
            "../../deploy/run.sh",
            "/home/x/.bashrc",
            "images/../../author.py",
            "site/images/x.png",
            "images/x.yaml",
        ):
            body = GOOD.replace("image: images/x.png", f"image: {bad}")
            with self.assertRaisesRegex(posts.ContentError, "image must be", msg=bad):
                posts.parse_post(_write(self.tmp, "2026-11-18-x.yaml", body))
        for bad in ("../x.mp4", "video/../../x.mp4", "/tmp/x.mp4", "images/x.mp4"):
            body = GOOD.replace("image: images/x.png\ntemplate: field_note", f"video: {bad}")
            with self.assertRaisesRegex(posts.ContentError, "video must be", msg=bad):
                posts.parse_post(_write(self.tmp, "2026-11-18-x.yaml", body))
        legacy = GOOD.replace("images/x.png", "images/legacy/AIREP-Educational-01.png")
        post = posts.parse_post(_write(self.tmp, "2026-11-18-x.yaml", legacy))
        self.assertEqual(post.image, "images/legacy/AIREP-Educational-01.png")
        film = GOOD.replace("image: images/x.png\ntemplate: field_note", "video: video/a_b-c.mp4")
        self.assertTrue(posts.parse_post(_write(self.tmp, "2026-11-18-x.yaml", film)).is_video)

    def test_thumbnail_offset_is_whole_milliseconds(self) -> None:
        # push.py int()s it while building createPost; "3s" raised ValueError mid-run on
        # Sunday, after some posts were already in Buffer, and no Telegram went out.
        film = GOOD.replace("image: images/x.png\ntemplate: field_note", "video: video/x.mp4")
        for bad in ("3s", "-1", "true", "'3000'"):
            body = film + f"thumbnail_offset_ms: {bad}\n"
            with self.assertRaisesRegex(posts.ContentError, "thumbnail_offset_ms", msg=bad):
                posts.parse_post(_write(self.tmp, "2026-11-18-x.yaml", body))
        post = posts.parse_post(
            _write(self.tmp, "2026-11-18-x.yaml", film + "thumbnail_offset_ms: 0\n")
        )
        self.assertEqual(post.thumbnail_offset_ms, 0)

    def test_one_post_per_day(self) -> None:
        _write(self.tmp, "2026-11-18-a.yaml", GOOD)
        _write(self.tmp, "2026-11-18-b.yaml", GOOD)
        with self.assertRaisesRegex(posts.ContentError, "already has"):
            posts.load_posts(self.tmp)


if __name__ == "__main__":
    unittest.main()
