"""The cadence, due times and the fortnight plan (dates, channels, Christmas gap, caps)."""

from __future__ import annotations

import unittest
from dataclasses import dataclass
from datetime import date, datetime, timedelta

import schedule


@dataclass
class FakePost:
    slug: str
    date: date


class CadenceTests(unittest.TestCase):
    def test_year_has_tue_to_fri_minus_the_christmas_gap(self) -> None:
        days = schedule.cadence()
        # 52 Tuesdays, 52 Wednesdays, 52 Thursdays and 51 Fridays from 17 Nov 2026 to
        # 11 Nov 2027 (a Thursday), minus the four Wed/Thu and two Fridays inside
        # 22 Dec - 4 Jan.
        self.assertEqual(len(days), 156 - 4 + 51 - 2)
        self.assertEqual(days[0], date(2026, 11, 17))
        self.assertEqual(days[-1], date(2027, 11, 11))
        self.assertTrue(all(d.weekday() in (1, 2, 3, 4) for d in days))
        self.assertEqual(sum(1 for d in days if d.weekday() == 4), 49)

    def test_christmas_gap_keeps_only_tuesday(self) -> None:
        self.assertEqual(schedule.allowed_slots(date(2026, 12, 22)), {"feature"})
        self.assertEqual(schedule.allowed_slots(date(2026, 12, 23)), frozenset())
        self.assertEqual(schedule.allowed_slots(date(2026, 12, 31)), frozenset())
        self.assertEqual(schedule.allowed_slots(date(2026, 12, 25)), frozenset())  # Friday
        self.assertEqual(schedule.allowed_slots(date(2027, 1, 1)), frozenset())  # Friday
        self.assertEqual(schedule.allowed_slots(date(2026, 12, 29)), {"feature"})
        # 5 Jan 2027 is a Tuesday, 6 Jan the first Wednesday back.
        self.assertEqual(schedule.allowed_slots(date(2027, 1, 6)), {"field_note"})

    def test_weekday_slots(self) -> None:
        self.assertEqual(schedule.allowed_slots(date(2026, 11, 17)), {"feature"})
        self.assertEqual(schedule.allowed_slots(date(2026, 11, 18)), {"field_note"})
        self.assertEqual(
            schedule.allowed_slots(date(2026, 11, 19)), {"pain", "price", "shipped", "date_post"}
        )
        self.assertEqual(schedule.allowed_slots(date(2026, 11, 20)), {"website"})  # Friday
        self.assertEqual(schedule.allowed_slots(date(2026, 11, 21)), frozenset())  # Saturday
        self.assertEqual(schedule.allowed_slots(date(2026, 11, 16)), frozenset())  # Monday


class HashtagTests(unittest.TestCase):
    def test_website_posts_get_their_own_default_tags(self) -> None:
        self.assertEqual(schedule.default_hashtags("feature"), schedule.DEFAULT_HASHTAGS)
        self.assertEqual(
            schedule.default_hashtags("website"), ("WebDesign", "SmallBusiness", "Australia")
        )


class DueAtTests(unittest.TestCase):
    def test_linkedin_0730_and_facebook_1830_aest_as_utc(self) -> None:
        self.assertEqual(
            schedule.due_at_iso(date(2026, 11, 17), "linkedin"), "2026-11-16T21:30:00Z"
        )
        self.assertEqual(
            schedule.due_at_iso(date(2026, 11, 17), "facebook"), "2026-11-17T08:30:00Z"
        )

    def test_no_daylight_saving_in_january(self) -> None:
        # Brisbane stays on +10, so the UTC offset is the same in summer.
        self.assertEqual(schedule.due_at_iso(date(2027, 1, 5), "linkedin"), "2027-01-04T21:30:00Z")


class PlanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.posts = [FakePost(d.isoformat(), d) for d in schedule.cadence()[:12]]  # 4 weeks
        self.sunday = datetime(2026, 11, 15, 18, 0, tzinfo=schedule.AEST)

    def test_fortnight_is_eight_posts_a_channel(self) -> None:
        plan = schedule.plan(self.posts, self.sunday, {})
        self.assertEqual(len(plan), 16)
        for channel in schedule.CHANNELS:
            self.assertEqual(sum(1 for p in plan if p.channel == channel), 8)
        self.assertEqual(plan[0].slug, "2026-11-17")
        self.assertEqual(plan[-1].date, date(2026, 11, 27))  # the second Friday
        self.assertTrue(all(p.date <= date(2026, 11, 29) for p in plan))
        # Eight queued a channel stays under the Free plan's ten.
        self.assertLessEqual(schedule.CHANNEL_CAP, 9)

    def test_cap_limits_each_channel(self) -> None:
        plan = schedule.plan(self.posts, self.sunday, {}, cap=4)
        self.assertEqual(len(plan), 8)
        plan = schedule.plan(self.posts, self.sunday, {}, horizon_days=60, cap=6)
        self.assertEqual(len(plan), 12)  # the cap, not the horizon, is the limit here

    def test_already_pushed_channels_are_skipped(self) -> None:
        pushed = {"2026-11-17": {"linkedin": {"post_id": "x"}}}
        plan = schedule.plan(self.posts, self.sunday, pushed)
        self.assertNotIn(("2026-11-17", "linkedin"), [(p.slug, p.channel) for p in plan])
        self.assertIn(("2026-11-17", "facebook"), [(p.slug, p.channel) for p in plan])
        # Only eight posts sit inside the fortnight, so LinkedIn has seven left to make.
        self.assertEqual(sum(1 for p in plan if p.channel == "linkedin"), 7)
        self.assertEqual(sum(1 for p in plan if p.channel == "facebook"), 8)

    def test_past_due_times_are_not_scheduled(self) -> None:
        tuesday_10am = datetime(2026, 11, 17, 10, 0, tzinfo=schedule.AEST)
        plan = schedule.plan(self.posts, tuesday_10am, {})
        first_day = [p for p in plan if p.slug == "2026-11-17"]
        self.assertEqual([p.channel for p in first_day], ["facebook"])

    def test_content_runs_out_warns_inside_six_weeks(self) -> None:
        last, warn = schedule.content_runs_out(self.posts, self.sunday)
        self.assertEqual(last, self.posts[-1].date)
        self.assertTrue(warn)
        far = [FakePost("x", self.sunday.date() + timedelta(weeks=8))]
        self.assertFalse(schedule.content_runs_out(far, self.sunday)[1])
        self.assertEqual(schedule.content_runs_out([], self.sunday), (None, True))


if __name__ == "__main__":
    unittest.main()
