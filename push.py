"""Schedule the next fortnight in Buffer. Dry run by default; --live posts and tells Telegram.

Secrets come only from ~/.config/airep-social/env (mode 600). Nothing here prints them.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import stat
import sys
from collections.abc import Callable
from datetime import date, datetime, time, timedelta
from pathlib import Path
from time import sleep as _sleep

import requests

import buffer_api
import posts as posts_mod
import schedule
import state as state_mod

ENV_PATH = Path.home() / ".config" / "airep-social" / "env"
DEFAULT_PAGES_BASE_URL = "https://intelliai-au.github.io/airep-social/site/"
REQUIRED_KEYS = (
    "BUFFER_API_KEY",
    "BUFFER_LINKEDIN_CHANNEL_ID",
    "BUFFER_FACEBOOK_CHANNEL_ID",
    "ASTRID_WEBHOOK_URL",
)
CHANNEL_LABEL = {"linkedin": "LI", "facebook": "FB"}
# Pauses between HEAD attempts: ~3.5 min in all, long enough for a slow GitHub Pages
# rebuild after run.sh's push, short enough that the Sunday job still finishes.
HEAD_RETRY_DELAYS = (30, 60, 120)
VETO_LINE = "Veto: delete the post in Buffer (Publishing > Queue) before it goes out."


class EnvError(RuntimeError):
    """The env file is missing, too open, or incomplete."""


def load_env(path: Path = ENV_PATH, *, require_secrets: bool) -> dict[str, str]:
    """KEY=VALUE lines from the env file; refuses a file readable by anyone else."""
    if not path.exists():
        if require_secrets:
            raise EnvError(f"{path} is missing; copy env.example there and chmod 600 it")
        return {}
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        raise EnvError(f"{path} is mode {mode:o}; it must be 600")
    env: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip().strip("'\"")
    if require_secrets:
        missing = [k for k in REQUIRED_KEYS if not env.get(k)]
        if missing:
            raise EnvError(f"{path} lacks {', '.join(missing)}")
    return env


def asset_url(base_url: str, post: posts_mod.Post) -> str:
    """The public Pages URL Buffer fetches the asset from."""
    return base_url.rstrip("/") + "/" + post.asset.lstrip("/")


def plan_lines(
    plan: list[schedule.Planned], by_slug: dict[str, posts_mod.Post], base: str
) -> list[str]:
    """One printable line per createPost the run would make."""
    lines = []
    for item in plan:
        post = by_slug[item.slug]
        kind = "video" if post.is_video else "image"
        lines.append(
            f"{item.due_at:%a %d %b %H:%M} {CHANNEL_LABEL[item.channel]}  {post.slot:<10} "
            f"{kind:<5} {item.slug}  {asset_url(base, post)}"
        )
    return lines


def telegram_text(
    run_day: date,
    plan: list[schedule.Planned],
    by_slug: dict[str, posts_mod.Post],
    base: str,
    *,
    scheduled: int,
    alerts: list[str],
    runs_out: date | None,
    write_ahead: bool,
    dry_run: bool,
) -> str:
    """The Sunday preview: what was queued, next up, and any reconnect or content alert."""
    counts = {ch: sum(1 for p in plan if p.channel == ch) for ch in schedule.CHANNELS}
    head = "DRY RUN · " if dry_run else ""
    lines = [
        f"{head}AIREP social · {run_day:%a %d %b %Y}",
        f"Scheduled {scheduled} of {len(plan)} posts in Buffer "
        f"(LinkedIn {counts['linkedin']}, Facebook {counts['facebook']}):",
    ]
    seen: set[str] = set()
    for item in plan:
        if item.slug in seen:
            continue
        seen.add(item.slug)
        post = by_slug[item.slug]
        lines.append(f"• {item.date:%a %d %b} · {post.slot} · LI 07:30 / FB 18:30")
        lines.append(f"  {asset_url(base, post)}")
    for alert in alerts:
        lines.append(f"⚠ {alert}")
    if runs_out is None:
        lines.append("⚠ No content at all: the calendar is empty.")
    elif write_ahead:
        # The month after the last written post is the one the author run writes next
        # (author.py on the box's Max login; the paid swarm is not used for content).
        nxt = (runs_out.replace(day=28) + timedelta(days=4)).strftime("%B")
        lines.append(
            f"⚠ Content runs out {runs_out:%a %d %b}: the author timer writes {nxt} on the "
            "first Sunday; sooner: systemctl --user start airep-social-author@write"
        )
    else:
        lines.append(f"Content written to {runs_out:%a %d %b}.")
    lines.append(VETO_LINE)
    return "\n".join(lines)[:3500]


def notify(url: str, secret: str, text: str) -> None:
    """POST the preview to Astrid's generic webhook, HMAC-signed when a secret is set."""
    body = json.dumps({"event_type": "airep_social", "message": text}).encode()
    headers = {"Content-Type": "application/json"}
    if secret:
        digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        headers["X-Hub-Signature-256"] = f"sha256={digest}"
    response = requests.post(url, data=body, headers=headers, timeout=20)
    response.raise_for_status()


def head_once(url: str) -> bool:
    """One HEAD request; False on any non-200 or network error."""
    try:
        response = requests.head(url, allow_redirects=True, timeout=20)
    except requests.RequestException:
        return False
    return response.status_code == 200


def head_ok(
    url: str,
    *,
    delays: tuple[int, ...] = HEAD_RETRY_DELAYS,
    sleep: Callable[[float], None] = _sleep,
    log: Callable[[str], None] = print,
) -> bool:
    """Buffer HEAD-checks every asset before publishing, so we do first, with retries.

    A fresh image is pushed minutes before this runs and Pages may not have rebuilt yet;
    giving up on the first miss would skip the post, and once its date is behind us it
    would never be scheduled. `sleep` is injectable so tests do not wait.
    """
    attempts = len(delays) + 1
    for attempt, delay in enumerate((*delays, None), start=1):
        if head_once(url):
            return True
        if delay is None:
            break
        log(f"  HEAD {url} not 200 yet (attempt {attempt}/{attempts}); retrying in {delay}s")
        sleep(delay)
    return False


def _now(today: str | None) -> datetime:
    if today:
        return datetime.combine(date.fromisoformat(today), time(0, 0), tzinfo=schedule.AEST)
    return datetime.now(schedule.AEST)


def main(argv: list[str] | None = None) -> int:
    """CLI entry; returns a process exit code."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--live", action="store_true", help="really call Buffer and Telegram")
    parser.add_argument("--today", metavar="YYYY-MM-DD", help="pretend it is this day (AEST)")
    parser.add_argument("--horizon", type=int, default=schedule.HORIZON_DAYS)
    parser.add_argument("--cap", type=int, default=schedule.CHANNEL_CAP)
    parser.add_argument("--env", type=Path, default=ENV_PATH)
    parser.add_argument("--state", type=Path, default=state_mod.STATE_PATH)
    parser.add_argument("--content", type=Path, default=posts_mod.CONTENT_DIR)
    parser.add_argument("--channels", action="store_true", help="list Buffer channels and exit")
    parser.add_argument(
        "--sent", action="store_true", help="list posts already published on both pages and exit"
    )
    parser.add_argument("--skip-head", action="store_true", help="do not HEAD-check assets")
    parser.add_argument("--no-notify", action="store_true", help="live, but no Telegram")
    args = parser.parse_args(argv)
    if args.live and args.today:
        # A pretend date makes plan() keep posts whose real due time has passed, and
        # Buffer would get customScheduled posts with a dueAt already behind us.
        print("error: --today is for dry runs; --live always uses the real clock", file=sys.stderr)
        return 2

    try:
        env = load_env(args.env, require_secrets=args.live or args.channels or args.sent)
    except EnvError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    base = env.get("PAGES_BASE_URL") or DEFAULT_PAGES_BASE_URL

    if args.channels:
        for ch in buffer_api.list_channels(env["BUFFER_API_KEY"]):
            flag = " (DISCONNECTED)" if ch["isDisconnected"] else ""
            print(
                f"{ch['service']:<10} {ch['id']}  {ch['name']}{flag}  org {ch['organization_id']}"
            )
        return 0

    if args.sent:
        # The legacy import's question: which 2026 captions already ran on each page.
        ids = [env["BUFFER_LINKEDIN_CHANNEL_ID"], env["BUFFER_FACEBOOK_CHANNEL_ID"]]
        orgs = {ch["organization_id"] for ch in buffer_api.list_channels(env["BUFFER_API_KEY"])}
        for org_id in sorted(orgs):
            for post in buffer_api.sent_posts(env["BUFFER_API_KEY"], org_id, ids):
                service = (post.get("channel") or {}).get("service", "?")
                # A plain string, not a one-element list repr.
                first_line = next(iter((post.get("text") or "").strip().splitlines()), "")
                print(
                    f"{(post.get('dueAt') or '')[:10]} {service:<9} {post.get('id')}  {first_line}"
                )
        return 0

    try:
        post_list = posts_mod.load_posts(args.content)
    except posts_mod.ContentError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    by_slug = {p.slug: p for p in post_list}
    pushed = state_mod.load_state(args.state)
    now = _now(args.today)
    plan = schedule.plan(post_list, now, pushed, horizon_days=args.horizon, cap=args.cap)
    runs_out, write_ahead = schedule.content_runs_out(post_list, now)

    print(f"airep-social push · now {now:%a %d %b %Y %H:%M} AEST · horizon {args.horizon} days")
    print(f"{len(plan)} createPost call(s) planned:")
    for line in plan_lines(plan, by_slug, base):
        print("  " + line)

    if not args.live:
        print("\nDRY RUN: nothing was sent to Buffer. Pass --live to schedule these.\n")
        print("Telegram preview would read:\n")
        print(
            telegram_text(
                now.date(),
                plan,
                by_slug,
                base,
                scheduled=0,
                alerts=[],
                runs_out=runs_out,
                write_ahead=write_ahead,
                dry_run=True,
            )
        )
        return 0

    token = env["BUFFER_API_KEY"]
    channel_ids = {
        "linkedin": env["BUFFER_LINKEDIN_CHANNEL_ID"],
        "facebook": env["BUFFER_FACEBOOK_CHANNEL_ID"],
    }
    alerts: list[str] = []
    live_channels = {ch["id"]: ch for ch in buffer_api.list_channels(token)}
    usable = set()
    for service, channel_id in channel_ids.items():
        ch = live_channels.get(channel_id)
        if ch is None:
            alerts.append(f"{service} channel id is not visible to this API key")
        elif ch["isDisconnected"]:
            # Only the page admin can fix this (Buffer > Channels > Reconnect).
            alerts.append(f"{service} page is no longer authorised: reconnect it in Buffer")
        else:
            usable.add(service)

    scheduled = 0
    checked: dict[str, bool] = {}
    for item in plan:
        if item.channel not in usable:
            continue
        post = by_slug[item.slug]
        url = asset_url(base, post)
        if not args.skip_head:
            if url not in checked:
                checked[url] = head_ok(url)
                if not checked[url]:
                    # Once per URL, not once per channel: both channels share the asset.
                    alerts.append(f"{item.slug}: {url} did not answer HEAD 200; not scheduled")
            if not checked[url]:
                continue
        create_input = buffer_api.build_create_input(
            channel_ids[item.channel],
            item.channel,
            post.caption(item.channel),
            url,
            schedule.due_at_iso(item.date, item.channel),
            is_video=post.is_video,
            alt_text=post.alt,
            thumbnail_offset_ms=post.thumbnail_offset_ms,
        )
        try:
            post_id = buffer_api.create_post(token, create_input)
        except buffer_api.BufferError as exc:
            alerts.append(f"{item.slug} {item.channel}: {exc}")
            continue
        state_mod.record(
            pushed,
            item.slug,
            item.channel,
            post_id,
            schedule.due_at_iso(item.date, item.channel),
            datetime.now(schedule.AEST).isoformat(timespec="seconds"),
        )
        state_mod.save_state(pushed, args.state)  # after each, so a crash keeps progress
        scheduled += 1
        print(f"  scheduled {item.slug} {item.channel} -> Buffer post {post_id}")

    text = telegram_text(
        now.date(),
        plan,
        by_slug,
        base,
        scheduled=scheduled,
        alerts=alerts,
        runs_out=runs_out,
        write_ahead=write_ahead,
        dry_run=False,
    )
    print(text)
    if not args.no_notify:
        notify(env["ASTRID_WEBHOOK_URL"], env.get("ASTRID_WEBHOOK_SECRET", ""), text)
    return 1 if alerts else 0


if __name__ == "__main__":
    sys.exit(main())
