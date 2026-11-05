"""Cadence, due times and the 14-day push plan for AIREP's social calendar.

Pure functions only: no network, no files. push.py and the tests drive it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta, timezone
from typing import Protocol

# Brisbane has no daylight saving, so Buffer's dueAt can use a fixed +10 all year.
AEST = timezone(timedelta(hours=10), "AEST")

CHANNELS: tuple[str, ...] = ("linkedin", "facebook")

# Owner-operators read LinkedIn before work and Facebook in the evening (plan doc).
POST_TIMES: dict[str, time] = {"linkedin": time(7, 30), "facebook": time(18, 30)}

# Monday is 0. Tue = feature (image or film), Wed = Field Note, Thu = one of the four
# Thursday formats. Weekends and Mon/Fri never post.
WEEKDAY_SLOTS: dict[int, frozenset[str]] = {
    1: frozenset({"feature"}),
    2: frozenset({"field_note"}),
    3: frozenset({"pain", "price", "shipped", "date_post"}),
}
SLOTS: frozenset[str] = frozenset().union(*WEEKDAY_SLOTS.values())

PLAN_START = date(2026, 11, 17)
PLAN_END = date(2027, 11, 11)

# push.py schedules the next fortnight: six posts a channel at most, which fits the
# Free plan's ten queued posts a channel with room for a hand-made one.
HORIZON_DAYS = 14
CHANNEL_CAP = 6

# Fewer than six weeks of unpushed calendar left means the swarm must write the
# next month (plan doc, "Writing ahead").
WRITE_AHEAD_WEEKS = 6

# The plan's recommended LinkedIn hashtags; Facebook gets none.
DEFAULT_HASHTAGS: tuple[str, ...] = ("ERP", "SmallBusiness", "Australia")


def christmas_quiet(day: date) -> bool:
    """True inside the 22 Dec to 4 Jan window, when only Tuesday posts."""
    year = day.year
    return date(year, 12, 22) <= day <= date(year, 12, 31) or date(year, 1, 1) <= day <= date(
        year, 1, 4
    )


def allowed_slots(day: date) -> frozenset[str]:
    """Slot kinds a post dated *day* may use; empty when the day never posts."""
    slots = WEEKDAY_SLOTS.get(day.weekday(), frozenset())
    if slots and christmas_quiet(day) and day.weekday() != 1:
        return frozenset()
    return slots


def cadence(start: date = PLAN_START, end: date = PLAN_END) -> list[date]:
    """Every posting day from *start* to *end* inclusive, in order."""
    days: list[date] = []
    day = start
    while day <= end:
        if allowed_slots(day):
            days.append(day)
        day += timedelta(days=1)
    return days


def due_at(day: date, channel: str) -> datetime:
    """The aware AEST datetime a post dated *day* publishes on *channel*."""
    return datetime.combine(day, POST_TIMES[channel], tzinfo=AEST)


def due_at_iso(day: date, channel: str) -> str:
    """Buffer's dueAt: the same instant in UTC, second precision, trailing Z."""
    return due_at(day, channel).astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class Schedulable(Protocol):
    """What plan() needs from a post (posts.Post satisfies it)."""

    slug: str
    date: date


@dataclass(frozen=True)
class Planned:
    """One createPost call push.py will make."""

    slug: str
    date: date
    channel: str
    due_at: datetime


def plan(
    posts: list[Schedulable],
    now: datetime,
    pushed: dict[str, dict[str, object]],
    horizon_days: int = HORIZON_DAYS,
    cap: int = CHANNEL_CAP,
) -> list[Planned]:
    """Posts to schedule now: due within the horizon, not yet pushed, oldest first.

    *pushed* is state.pushed.json's mapping (slug -> channel -> record). A channel
    stops at *cap* so the Free plan's queue never overflows; the rest wait for the
    next Sunday run.
    """
    today = now.astimezone(AEST).date()
    last_day = today + timedelta(days=horizon_days)
    out: list[Planned] = []
    per_channel = dict.fromkeys(CHANNELS, 0)
    for post in sorted(posts, key=lambda p: p.date):
        if post.date > last_day:
            break
        for channel in CHANNELS:
            when = due_at(post.date, channel)
            if when <= now:
                continue  # already in the past; nothing to schedule
            if channel in pushed.get(post.slug, {}):
                continue
            if per_channel[channel] >= cap:
                continue
            per_channel[channel] += 1
            out.append(Planned(post.slug, post.date, channel, when))
    return out


def content_runs_out(posts: list[Schedulable], now: datetime) -> tuple[date | None, bool]:
    """(last dated post, whether the swarm must write ahead now)."""
    if not posts:
        return None, True
    last = max(p.date for p in posts)
    today = now.astimezone(AEST).date()
    return last, (last - today) < timedelta(weeks=WRITE_AHEAD_WEEKS)
