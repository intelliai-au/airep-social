"""shots.py's site list, output names and the mpv encode (no browser, no network)."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

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

    def test_a_failed_encode_leaves_no_half_written_film_to_commit(self) -> None:
        # mpv writes its output as it goes; one that dies part-way left
        # website_<slug>_scroll.part.mp4 in site/video/, which refresh_shots then committed.
        with tempfile.TemporaryDirectory() as tmp:
            bin_dir = Path(tmp) / "bin"
            bin_dir.mkdir()
            fake = bin_dir / "mpv"
            fake.write_text(
                "#!/bin/sh\n"
                'for a in "$@"; do case "$a" in --o=*) printf partial > "${a#--o=}";; esac; done\n'
                "echo 'encode failed' >&2\nexit 1\n"
            )
            fake.chmod(0o755)
            frames = Path(tmp) / "frames"
            frames.mkdir()
            video = Path(tmp) / "video"
            video.mkdir()
            out = video / "website_acme_scroll.mp4"
            with mock.patch.dict(os.environ, {"PATH": f"{bin_dir}:{os.environ['PATH']}"}):
                with self.assertRaises(RuntimeError):
                    shots.encode_frames(frames, out, fps=6)
            self.assertEqual(list(video.iterdir()), [])

    def test_git_never_picks_up_a_half_written_film(self) -> None:
        # A run killed mid-encode (author.py's shots timeout) cannot clean up after itself.
        proc = subprocess.run(
            ["git", "check-ignore", "-q", "site/video/website_acme_scroll.part.mp4"],
            cwd=shots.ROOT,
        )
        self.assertEqual(proc.returncode, 0)
        proc = subprocess.run(
            ["git", "check-ignore", "-q", "site/video/website_acme_scroll.mp4"], cwd=shots.ROOT
        )
        self.assertEqual(proc.returncode, 1)


if __name__ == "__main__":
    unittest.main()
