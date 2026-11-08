"""shots.py's site list, output names and the mpv encode (no browser, no network)."""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

import shots


class SiteListTests(unittest.TestCase):
    def test_sites_yaml_lists_live_client_sites_with_facts(self) -> None:
        sites = shots.load_sites()
        self.assertEqual(
            [s.slug for s in sites], ["gripswich", "ascot-vale-driving", "mike-trace-engineering"]
        )
        for site in sites:
            self.assertTrue(site.url.startswith("https://"), site.slug)
            self.assertGreaterEqual(len(site.facts), 2, site.slug)
            self.assertTrue(site.sector and site.plan, site.slug)
        # The pitch demos never appear until their owner says yes.
        text = shots.SITES_YAML.read_text().lower()
        for banned in ("rb-electrical", "hfr-sweeping", "tallowwood", "onrender.com"):
            self.assertNotIn(f"url: https://{banned}", text)

    def test_gripswich_hides_its_day_notice_bar(self) -> None:
        site = next(s for s in shots.load_sites() if s.slug == "gripswich")
        self.assertEqual(site.hide, (".site-notice",))

    def test_output_paths_follow_the_slug(self) -> None:
        site = shots.Site("acme", "Acme", "https://acme.au", "acme.au")
        self.assertEqual(site.phone_shot, "shots/acme-phone.png")
        self.assertEqual(site.laptop_shot, "shots/acme-laptop.png")
        self.assertEqual(site.film, "video/website_acme_scroll.mp4")
        self.assertEqual(shots.page_slug(site, "/prices/"), "acme-prices")
        self.assertEqual(shots.page_slug(site, "/"), "acme-home")

    def test_film_is_long_enough_and_even_sized_for_the_networks(self) -> None:
        self.assertGreaterEqual(shots.FILM_SECONDS, 3)
        self.assertEqual(shots.PHONE[0] * shots.DEVICE_SCALE % 2, 0)
        self.assertEqual(shots.PHONE[1] * shots.DEVICE_SCALE % 2, 0)


class EncodeTests(unittest.TestCase):
    def test_mpv_encodes_a_frame_sequence_to_mp4(self) -> None:
        if not shutil.which("mpv"):
            self.skipTest("mpv not installed")
        try:
            from PIL import Image
        except ImportError:  # pragma: no cover
            self.skipTest("Pillow not installed")
        with tempfile.TemporaryDirectory() as tmp:
            frames = Path(tmp) / "frames"
            frames.mkdir()
            for i in range(6):
                Image.new("RGB", (64, 128), (i * 40, 80, 120)).save(frames / f"{i:04d}.png")
            out = Path(tmp) / "out.mp4"
            shots.encode_frames(frames, out, fps=6)
            data = out.read_bytes()
        self.assertGreater(len(data), 500)
        self.assertEqual(data[4:8], b"ftyp")
        # faststart: the moov index comes before the media data.
        self.assertLess(data.find(b"moov"), data.find(b"mdat"))


if __name__ == "__main__":
    unittest.main()
