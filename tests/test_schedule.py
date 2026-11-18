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
    def test_year_has_tue_to_fri_around_the_website_led_quarter(self) -> None:
        days = schedule.cadence()
        # Tue-Fri 17-20 Nov 2026 (4); the website-led quarter, Tue-Thu from 24 Nov to
        # 25 Feb with only Tue 22 and 29 Dec over Christmas (12 weeks x 3 + 2 = 38); then
        # the AIREP grid again from Tue 2 Mar to Thu 11 Nov 2027: 37 each of Tue, Wed and
        # Thu, and 36 Fridays (147).
        self.assertEqual(len(days), 4 + 38 + 147)
        self.assertEqual(days[0], date(2026, 11, 17))
        self.assertEqual(days[-1], date(2027, 11, 11))
        self.assertTrue(all(d.weekday() in (1, 2, 3, 4) for d in days))
        self.assertEqual(sum(1 for d in days if d.weekday() == 4), 1 + 36)

    def test_website_led_quarter_posts_three_a_week(self) -> None:
        days = schedule.cadence(schedule.WEBSITE_LED_FROM, schedule.WEBSITE_LED_UNTIL)
        self.assertEqual(len(days), 38)
        self.assertEqual(days[0], date(2026, 11, 24))
        self.assertEqual(days[-1], date(2027, 2, 25))
        self.assertTrue(all(d.weekday() in (1, 2, 3) for d in days))
        # The four days held for the front-page films are posting days, inside the window.
        self.assertTrue(schedule.RESERVED <= set(days))
        self.assertEqual(len(schedule.RESERVED), 4)

    def test_christmas_gap_keeps_only_tuesday(self) -> None:
        self.assertEqual(schedule.allowed_slots(date(2026, 12, 22)), {"website", "feature"})
        self.assertEqual(schedule.allowed_slots(date(2026, 12, 23)), frozenset())
        self.assertEqual(schedule.allowed_slots(date(2026, 12, 31)), frozenset())
        self.assertEqual(schedule.allowed_slots(date(2026, 12, 25)), frozenset())  # Friday
        self.assertEqual(schedule.allowed_slots(date(2027, 1, 1)), frozenset())  # Friday
        self.assertEqual(schedule.allowed_slots(date(2026, 12, 29)), {"website", "feature"})
        # 5 Jan 2027 is a Tuesday, 6 Jan the first Wednesday back.
        self.assertEqual(schedule.allowed_slots(date(2027, 1, 6)), {"website"})
        # The AIREP grid's own Christmas gap still holds after the quarter ends.
        self.assertEqual(schedule.allowed_slots(date(2027, 12, 22)), frozenset())

    def test_weekday_slots(self) -> None:
        self.assertEqual(schedule.allowed_slots(date(2026, 11, 17)), {"feature"})
        self.assertEqual(schedule.allowed_slots(date(2026, 11, 18)), {"field_note"})
        self.assertEqual(
            schedule.allowed_slots(date(2026, 11, 19)), {"pain", "price", "shipped", "date_post"}
        )
        self.assertEqual(schedule.allowed_slots(date(2026, 11, 20)), {"website"})  # Friday
        self.assertEqual(schedule.allowed_slots(date(2026, 11, 21)), frozenset())  # Saturday
        self.assertEqual(schedule.allowed_slots(date(2026, 11, 16)), frozenset())  # Monday

    def test_website_led_quarter_slots(self) -> None:
        # Tue may be a website post or an AIREP feature; Wed and Thu are websites only;
        # no Friday, which the AIREP grid gave the websites before.
        self.assertEqual(schedule.allowed_slots(date(2026, 11, 24)), {"website", "feature"})
        self.assertEqual(schedule.allowed_slots(date(2026, 11, 25)), {"website"})
        self.assertEqual(schedule.allowed_slots(date(2026, 11, 26)), {"website"})
        self.assertEqual(schedule.allowed_slots(date(2026, 11, 27)), frozenset())  # Friday
        self.assertEqual(schedule.allowed_slots(date(2027, 2, 25)), {"website"})  # last day
        self.assertEqual(schedule.allowed_slots(date(2027, 2, 26)), frozenset())  # Friday
        # From March the AIREP grid is back.
        self.assertEqual(schedule.allowed_slots(date(2027, 3, 2)), {"feature"})
        self.assertEqual(schedule.allowed_slots(date(2027, 3, 5)), {"website"})
        self.assertTrue(
            {"website", "feature", "field_note", "pain", "price", "shipped", "date_post"}
            <= schedule.SLOTS
        )


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


def as_pushed(plan: list[schedule.Planned], pushed: dict | None = None) -> dict:
    """Record *plan* the way push.py --live does (due_at = the UTC dueAt sent to Buffer)."""
    pushed = {} if pushed is None else pushed
    for p in plan:
        pushed.setdefault(p.slug, {})[p.channel] = {
            "post_id": f"id-{p.slug}-{p.channel}",
            "due_at": schedule.due_at_iso(p.date, p.channel),
            "pushed_at": "2026-11-15T18:00:00+10:00",
        }
    return pushed


class PlanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.posts = [FakePost(d.isoformat(), d) for d in schedule.cadence()[:12]]  # 3 weeks
        self.sunday = datetime(2026, 11, 15, 18, 0, tzinfo=schedule.AEST)

    def test_first_run_queues_six_a_channel(self) -> None:
        plan = schedule.plan(self.posts, self.sunday, {})
        self.assertEqual(len(plan), 12)
        for channel in schedule.CHANNELS:
            self.assertEqual(sum(1 for p in plan if p.channel == channel), 6)
        self.assertEqual(plan[0].slug, "2026-11-17")
        self.assertEqual(plan[-1].date, date(2026, 11, 25))  # Thu 26 waits a week
        self.assertTrue(all(p.date <= date(2026, 11, 29) for p in plan))
        # Keiran's rule: never more than six queued a channel (the Free plan holds ten).
        self.assertLessEqual(schedule.CHANNEL_CAP, 6)

    def test_cap_counts_posts_already_queued(self) -> None:
        # The bug: the cap counted only this run's calls, so the second Sunday added six
        # more on top of the two still waiting from the first: eight queued a channel.
        first = schedule.plan(self.posts, self.sunday, {})
        pushed = as_pushed(first)
        next_sunday = self.sunday + timedelta(weeks=1)
        self.assertEqual(schedule.queued(pushed, next_sunday), {"linkedin": 2, "facebook": 2})
        second = schedule.plan(self.posts, next_sunday, pushed)
        for channel in schedule.CHANNELS:
            self.assertEqual(sum(1 for p in second if p.channel == channel), 4)
        # Three a week from 23 Nov: Thu 26 Nov, then Tue-Thu 1-3 Dec.
        self.assertEqual(
            sorted({p.slug for p in second}),
            ["2026-11-26", "2026-12-01", "2026-12-02", "2026-12-03"],
        )

    def test_weekly_runs_never_queue_more_than_the_cap_and_miss_nothing(self) -> None:
        posts = [FakePost(d.isoformat(), d) for d in schedule.cadence()[:40]]
        pushed: dict = {}
        sunday = self.sunday
        for _ in range(8):
            plan = schedule.plan(posts, sunday, pushed)
            as_pushed(plan, pushed)
            depth = schedule.queued(pushed, sunday)
            self.assertTrue(all(n <= schedule.CHANNEL_CAP for n in depth.values()), depth)
            sunday += timedelta(weeks=1)
        # Every post due before the last run was queued on both channels, ahead of time.
        for post in posts:
            if schedule.due_at(post.date, "facebook") < sunday - timedelta(weeks=1):
                self.assertEqual(set(pushed.get(post.slug, {})), set(schedule.CHANNELS), post)

    def test_queued_ignores_past_and_unreadable_due_times(self) -> None:
        pushed = {
            "past": {"linkedin": {"due_at": "2026-11-10T21:30:00Z"}},
            "ahead": {"linkedin": {"due_at": "2026-11-16T21:30:00Z"}},
            "junk": {"facebook": {"due_at": "due"}, "linkedin": {"post_id": "x"}},
        }
        self.assertEqual(schedule.queued(pushed, self.sunday), {"linkedin": 1, "facebook": 0})

    def test_cap_limits_each_channel(self) -> None:
        plan = schedule.plan(self.posts, self.sunday, {}, cap=4)
        self.assertEqual(len(plan), 8)
        plan = schedule.plan(self.posts, self.sunday, {}, horizon_days=60, cap=6)
        self.assertEqual(len(plan), 12)  # the cap, not the horizon, is the limit here

    def test_already_pushed_channels_are_skipped(self) -> None:
        pushed = {"2026-11-17": {"linkedin": {"post_id": "x", "due_at": "2026-11-16T21:30:00Z"}}}
        plan = schedule.plan(self.posts, self.sunday, pushed)
        self.assertNotIn(("2026-11-17", "linkedin"), [(p.slug, p.channel) for p in plan])
        self.assertIn(("2026-11-17", "facebook"), [(p.slug, p.channel) for p in plan])
        # LinkedIn already holds one queued post, so it gets five more to reach six.
        self.assertEqual(sum(1 for p in plan if p.channel == "linkedin"), 5)
        self.assertEqual(sum(1 for p in plan if p.channel == "facebook"), 6)

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
