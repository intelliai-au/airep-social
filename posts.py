"""Load and validate the one-file-per-post calendar in content/ (YAML, dated filenames)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import yaml

import schedule

CONTENT_DIR = Path(__file__).resolve().parent / "content"
SITE_DIR = Path(__file__).resolve().parent / "site"

# Three short lines and one link (plan doc, "Rules"); the link line is the fourth.
MAX_CAPTION_LINES = 4
LINK_HOST = "intelliai.au"
MAX_HASHTAGS = 3

_FILENAME = re.compile(r"^(\d{4}-\d{2}-\d{2})-[a-z0-9-]+\.yaml$")
# One word per tag: caption() adds the "#", and a space or a second "#" would publish a
# broken tag. A bare string here (hashtags: ERP) would otherwise become "#E #R #P".
_HASHTAG = re.compile(r"^[A-Za-z0-9_]+$")


class ContentError(ValueError):
    """A content file breaks the calendar's rules; the message names the file."""


@dataclass
class Post:
    """One calendar entry: the same asset to both pages, a caption each."""

    slug: str
    date: date
    slot: str
    linkedin: str
    facebook: str
    hashtags: list[str] = field(default_factory=lambda: list(schedule.DEFAULT_HASHTAGS))
    image: str | None = None  # path under site/, e.g. images/2026-11-18-x.png
    video: str | None = None  # path under site/, e.g. video/airep_reorder_music.mp4
    template: str | None = None  # templates/<name>.html, rendered by build.py
    fields: dict = field(default_factory=dict)
    alt: str = ""
    thumbnail_offset_ms: int | None = None

    @property
    def asset(self) -> str:
        """The asset's path under site/ (image or video)."""
        return self.video or self.image or ""

    @property
    def is_video(self) -> bool:
        """True when the asset is a film."""
        return bool(self.video)

    def caption(self, channel: str) -> str:
        """The text Buffer receives for *channel*: LinkedIn carries the hashtags."""
        text = self.linkedin if channel == "linkedin" else self.facebook
        text = text.strip()
        if channel == "linkedin" and self.hashtags:
            text += "\n\n" + " ".join(f"#{tag}" for tag in self.hashtags)
        return text


def _caption_errors(text: str, channel: str) -> list[str]:
    lines = [ln for ln in text.strip().splitlines() if ln.strip()]
    errors = []
    if not lines:
        errors.append(f"{channel}: caption is empty")
    if len(lines) > MAX_CAPTION_LINES:
        errors.append(f"{channel}: {len(lines)} lines, max {MAX_CAPTION_LINES} (3 + the link)")
    if text.count(LINK_HOST) != 1:
        errors.append(f"{channel}: must link {LINK_HOST} exactly once")
    if "#" in text:
        errors.append(f"{channel}: hashtags go in `hashtags:`, not the caption")
    return errors


def parse_post(path: Path) -> Post:
    """Read one content file, validating the rules the plan fixes."""
    match = _FILENAME.match(path.name)
    if not match:
        raise ContentError(f"{path.name}: name must be YYYY-MM-DD-slug.yaml")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    errors: list[str] = []

    day = raw.get("date")
    if not isinstance(day, date) or day.isoformat() != match.group(1):
        errors.append("date must match the filename's date")
        day = date.fromisoformat(match.group(1))

    slot = str(raw.get("slot", ""))
    allowed = schedule.allowed_slots(day)
    if slot not in schedule.SLOTS:
        errors.append(f"slot {slot!r} is not one of {sorted(schedule.SLOTS)}")
    elif slot not in allowed:
        errors.append(f"{day:%a %d %b} allows {sorted(allowed) or 'no post'}, not {slot!r}")

    image, video = raw.get("image"), raw.get("video")
    if bool(image) == bool(video):
        errors.append("exactly one of image: or video: is required")
    template = raw.get("template")
    if template and video:
        errors.append("a video post has no template")

    raw_tags = raw.get("hashtags", list(schedule.DEFAULT_HASHTAGS))
    hashtags = [str(t) for t in raw_tags] if isinstance(raw_tags, list) else []
    if not isinstance(raw_tags, list):
        errors.append("hashtags must be a list, e.g. [ERP, SmallBusiness, Australia]")
    elif len(hashtags) > MAX_HASHTAGS:
        errors.append(f"{len(hashtags)} hashtags, max {MAX_HASHTAGS}")
    elif any(not isinstance(t, str) or not _HASHTAG.match(t) for t in raw_tags):
        errors.append("each hashtag is one word without the #, e.g. SmallBusiness")

    linkedin = str(raw.get("linkedin", ""))
    facebook = str(raw.get("facebook", ""))
    errors += _caption_errors(linkedin, "linkedin")
    errors += _caption_errors(facebook, "facebook")

    if errors:
        raise ContentError(f"{path.name}: " + "; ".join(errors))

    return Post(
        slug=path.stem,
        date=day,
        slot=slot,
        linkedin=linkedin,
        facebook=facebook,
        hashtags=hashtags,
        image=image,
        video=video,
        template=template,
        fields=dict(raw.get("fields") or {}),
        alt=str(raw.get("alt", "")),
        thumbnail_offset_ms=raw.get("thumbnail_offset_ms"),
    )


def load_posts(content_dir: Path = CONTENT_DIR) -> list[Post]:
    """Every post in *content_dir*, oldest first; one slot per day."""
    posts = [parse_post(p) for p in sorted(content_dir.glob("*.yaml"))]
    seen: dict[date, str] = {}
    for post in posts:
        if post.date in seen:
            raise ContentError(f"{post.slug}: {post.date} already has {seen[post.date]}")
        seen[post.date] = post.slug
    return posts
