"""push.py's dry run, env-file guard, createPost shapes and the Telegram preview."""

from __future__ import annotations

import contextlib
import io
import os
import tempfile
import unittest
import unittest.mock
from datetime import date
from pathlib import Path

import buffer_api
import posts
import push
import schedule


class DryRunTests(unittest.TestCase):
    def test_dry_run_prints_the_fortnight_and_sends_nothing(self) -> None:
        # Pin the tree to November so the "runs out" line does not move as months are written.
        real = posts.load_posts

        def november_only(*args, **kwargs):
            return [p for p in real(*args, **kwargs) if p.date < date(2026, 12, 1)]

        with tempfile.TemporaryDirectory() as tmp:
            out = io.StringIO()
            with (
                unittest.mock.patch.object(push.posts_mod, "load_posts", november_only),
                contextlib.redirect_stdout(out),
            ):
                code = push.main(
                    ["--today", "2026-11-15", "--state", str(Path(tmp) / "pushed.json")]
                )
            text = out.getvalue()
        self.assertEqual(code, 0)
        self.assertIn("DRY RUN", text)
        # Four posts a week (the Friday website post since 2026-11-08), two weeks ahead.
        self.assertIn("16 createPost call(s) planned", text)
        self.assertIn("Tue 17 Nov 07:30 LI", text)
        self.assertIn("Fri 27 Nov 18:30 FB", text)
        self.assertIn("video/airep_reorder_music.mp4", text)
        self.assertIn("images/2026-11-20-website-gripswich.png", text)
        self.assertIn(push.VETO_LINE, text)
        self.assertIn("LinkedIn 8, Facebook 8", text)
        self.assertIn("the author timer writes December", text)

    def test_second_run_after_a_push_plans_nothing_new(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "pushed.json"
            import state as state_mod

            data: dict = {}
            for post in posts.load_posts():
                for channel in schedule.CHANNELS:
                    state_mod.record(data, post.slug, channel, "id", "due", "at")
            state_mod.save_state(data, state_path)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                push.main(["--today", "2026-11-15", "--state", str(state_path)])
        self.assertIn("0 createPost call(s) planned", out.getvalue())


class LiveGuardTests(unittest.TestCase):
    def test_live_refuses_a_pretend_date_before_touching_buffer(self) -> None:
        # --today is a dry-run aid: with --live it would createPost with past dueAts.
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / "env"
            env_path.write_text(
                "BUFFER_API_KEY=k\nBUFFER_LINKEDIN_CHANNEL_ID=l\n"
                "BUFFER_FACEBOOK_CHANNEL_ID=f\nASTRID_WEBHOOK_URL=u\n"
            )
            os.chmod(env_path, 0o600)

            def boom(*_a, **_k):
                raise AssertionError("Buffer was called")

            err = io.StringIO()
            with (
                unittest.mock.patch.object(buffer_api, "list_channels", boom),
                unittest.mock.patch.object(buffer_api, "create_post", boom),
                contextlib.redirect_stderr(err),
            ):
                code = push.main(["--live", "--today", "2026-11-15", "--env", str(env_path)])
        self.assertEqual(code, 2)
        self.assertIn("--today is for dry runs", err.getvalue())


class EnvTests(unittest.TestCase):
    def test_env_file_must_be_private(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "env"
            path.write_text("BUFFER_API_KEY=k\n")
            os.chmod(path, 0o644)
            with self.assertRaisesRegex(push.EnvError, "must be 600"):
                push.load_env(path, require_secrets=False)
            os.chmod(path, 0o600)
            with self.assertRaisesRegex(push.EnvError, "lacks"):
                push.load_env(path, require_secrets=True)
            path.write_text(
                "# c\nBUFFER_API_KEY='k'\nBUFFER_LINKEDIN_CHANNEL_ID=l\n"
                'BUFFER_FACEBOOK_CHANNEL_ID=f\nASTRID_WEBHOOK_URL="u"\n'
            )
            env = push.load_env(path, require_secrets=True)
            self.assertEqual(env["BUFFER_API_KEY"], "k")
            self.assertEqual(env["ASTRID_WEBHOOK_URL"], "u")

    def test_missing_env_is_fine_for_a_dry_run_only(self) -> None:
        missing = Path(tempfile.gettempdir()) / "airep-social-no-such-env"
        self.assertEqual(push.load_env(missing, require_secrets=False), {})
        with self.assertRaises(push.EnvError):
            push.load_env(missing, require_secrets=True)


class CreateInputTests(unittest.TestCase):
    def test_image_post_for_facebook(self) -> None:
        inp = buffer_api.build_create_input(
            "fb1",
            "facebook",
            "hi https://intelliai.au",
            "https://x/a.png",
            "2026-11-17T08:30:00Z",
            alt_text="alt",
        )
        self.assertEqual(inp["mode"], "customScheduled")
        self.assertEqual(inp["dueAt"], "2026-11-17T08:30:00Z")
        self.assertEqual(
            inp["assets"], [{"image": {"url": "https://x/a.png", "metadata": {"altText": "alt"}}}]
        )
        self.assertEqual(inp["metadata"], {"facebook": {"type": "post"}})
        self.assertEqual(inp["schedulingType"], "automatic")

    def test_video_post_for_linkedin(self) -> None:
        inp = buffer_api.build_create_input(
            "li1",
            "linkedin",
            "t",
            "https://x/v.mp4",
            "2026-11-16T21:30:00Z",
            is_video=True,
            thumbnail_offset_ms=3000,
        )
        self.assertEqual(
            inp["assets"],
            [{"video": {"url": "https://x/v.mp4", "metadata": {"thumbnailOffset": 3000}}}],
        )
        self.assertNotIn("metadata", inp)  # LinkedIn needs no post type
        self.assertNotIn("thumbnailUrl", inp["assets"][0]["video"])  # the API rejects it


class TelegramTextTests(unittest.TestCase):
    def test_preview_lists_each_post_once_with_its_url(self) -> None:
        post_list = posts.load_posts()
        by_slug = {p.slug: p for p in post_list}
        now = push._now("2026-11-15")
        plan = schedule.plan(post_list, now, {})
        text = push.telegram_text(
            date(2026, 11, 15),
            plan,
            by_slug,
            "https://pages/site/",
            scheduled=16,
            alerts=["facebook page is no longer authorised"],
            runs_out=date(2026, 11, 26),
            write_ahead=True,
            dry_run=False,
        )
        self.assertEqual(text.count("airep_reorder_music.mp4"), 1)
        self.assertIn("Scheduled 16 of 16", text)
        self.assertIn("Fri 20 Nov · website", text)
        self.assertIn("⚠ facebook page is no longer authorised", text)
        self.assertIn("Content runs out Thu 26 Nov", text)
        self.assertLessEqual(len(text), 3500)


if __name__ == "__main__":
    unittest.main()


class HeadRetryTests(unittest.TestCase):
    """Pages may still be rebuilding when push.py runs, so a HEAD miss is retried."""

    def test_succeeds_after_pages_catches_up(self) -> None:
        answers = iter([False, False, True])
        slept: list[float] = []
        logged: list[str] = []
        with unittest.mock.patch.object(push, "head_once", lambda _u: next(answers)):
            ok = push.head_ok("https://x/a.png", sleep=slept.append, log=logged.append)
        self.assertTrue(ok)
        self.assertEqual(slept, [30, 60])
        self.assertEqual(len(logged), 2)
        self.assertIn("attempt 1/4", logged[0])

    def test_gives_up_after_a_bounded_wait(self) -> None:
        calls = 0

        def never(_url: str) -> bool:
            nonlocal calls
            calls += 1
            return False

        slept: list[float] = []
        with unittest.mock.patch.object(push, "head_once", never):
            ok = push.head_ok("https://x/a.png", sleep=slept.append, log=lambda _m: None)
        self.assertFalse(ok)
        self.assertEqual(calls, len(push.HEAD_RETRY_DELAYS) + 1)
        self.assertLessEqual(sum(slept), 240)  # ~4 minutes at most
        self.assertEqual(slept, list(push.HEAD_RETRY_DELAYS))


class SentListingTests(unittest.TestCase):
    def test_first_line_prints_plainly_not_as_a_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / "env"
            env_path.write_text(
                "BUFFER_API_KEY=k\nBUFFER_LINKEDIN_CHANNEL_ID=l\n"
                "BUFFER_FACEBOOK_CHANNEL_ID=f\nASTRID_WEBHOOK_URL=u\n"
            )
            os.chmod(env_path, 0o600)
            channels = [{"organization_id": "o", "id": "l", "service": "linkedin"}]
            sent = [
                {
                    "id": "p1",
                    "dueAt": "2026-01-02T07:30:00Z",
                    "channel": {"service": "linkedin"},
                    "text": "First line\nsecond line",
                }
            ]
            out = io.StringIO()
            with (
                unittest.mock.patch.object(buffer_api, "list_channels", lambda _k: channels),
                unittest.mock.patch.object(buffer_api, "sent_posts", lambda *_a: sent),
                contextlib.redirect_stdout(out),
            ):
                code = push.main(["--sent", "--env", str(env_path)])
        self.assertEqual(code, 0)
        self.assertIn("2026-01-02 linkedin  p1  First line", out.getvalue())
        self.assertNotIn("['First line']", out.getvalue())
