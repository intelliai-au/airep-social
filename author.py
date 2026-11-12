"""Headless authoring runs on the box's Claude Code (Max) login: write a month, or film its videos.

Two phases, each a fresh Claude Code session started through the Agent SDK with the API
key blanked, so the run bills the subscription the box is logged in with and never the
API (Keiran, 2026-11-08: "use these Claude sessions with my Max subscription", not the
paid swarm). The sessions work in a git worktree; this script validates what they left
(ruff, the unit tests, build.py, completeness), merges into main on success, and leaves
the worktree in place for inspection on failure. It never pushes to Buffer: push.py does
that on Sundays, from main.

    author.py write            # every missing posting day up to the end of the month
                               # after next, one session per month, each reviewed
    author.py film             # the month after next's two films (YEAR.md), then the
                               # two Tuesday posts that use them
    author.py write --dry-run  # print the plan and the briefs, start no session
"""

from __future__ import annotations

import argparse
import asyncio
import calendar
import contextlib
import fcntl
import os
import re
import subprocess
import sys
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from string import Template

import posts as posts_mod
import push
import schedule
import shots as shots_mod
import state as state_mod

ROOT = Path(__file__).resolve().parent
BRIEFS = ROOT / "deploy" / "briefs"
YEAR_MD = ROOT / "docs" / "YEAR.md"
STATE_DIR = Path.home() / ".local" / "state" / "airep-social"

# Content is kept written to the end of the month after next: the Sunday push looks 14
# days ahead, so two months is slack enough for a failed run to be retried by hand.
MONTHS_AHEAD = 2

# Turn and wall-clock caps per session. A writing run is 13 files plus a render; a film
# run drives the demo tenant and the rig, which is slower by nature.
MAX_TURNS = {"write": 160, "review": 60, "film": 320, "shipped": 40}
TIMEOUT_S = {"write": 60 * 60, "review": 25 * 60, "film": 120 * 60, "shipped": 20 * 60}

# What a session may change in this repo. Everything else (tests, templates, the Python,
# the units, the site screenshots shots.py takes) is the caller's; a session that touches
# it has drifted off its brief, as the first December writer did when it rewrote two
# tests to fit the content it had added.
ALLOWED_PREFIXES = ("content/", "site/images/", "site/video/")

# shots.py (the public web, three sites, a film each the first time) gets this long.
SHOTS_TIMEOUT_S = 25 * 60

# Only these may reach the child session's environment with a value. Anything that looks
# like a credential is blanked, and ANTHROPIC_API_KEY always is: with no key the CLI
# falls back to the box's Claude Code login, which is the whole point of this script.
_SECRET_LIKE = re.compile(r"(API_KEY|TOKEN|SECRET|PASSWORD|PASSWD|DSN|DATABASE_URL)", re.I)

_YEAR_ROW = re.compile(r"^\|\s*(\d{4})-(\d{2})\s*\|(.*)\|\s*$")


@dataclass(frozen=True)
class MonthBrief:
    """What one month's run needs from docs/YEAR.md."""

    year: int
    month: int
    theme: str
    films: str
    hooks: str
    web: str = ""  # the Friday website angle (fourth column, added 2026-11-08)

    @property
    def key(self) -> str:
        """``YYYY-MM``, as the content filenames start."""
        return f"{self.year:04d}-{self.month:02d}"

    @property
    def name(self) -> str:
        """``February 2027``."""
        return f"{calendar.month_name[self.month]} {self.year}"


@dataclass
class SessionResult:
    """What one headless session came back with."""

    ok: bool
    text: str = ""
    turns: int = 0
    cost_usd: float | None = None
    reason: str = ""


@dataclass
class RunReport:
    """Everything the Telegram summary and the exit code are built from."""

    phase: str
    ok: bool = True
    lines: list[str] = field(default_factory=list)

    def say(self, line: str) -> None:
        """Print and remember one line of progress."""
        print(line, flush=True)
        self.lines.append(line)

    def fail(self, line: str) -> None:
        """Record a failure; the run keeps the worktree and exits 1."""
        self.ok = False
        self.say(f"⚠ {line}")


# ----------------------------------------------------------------------------- planning


def month_end(year: int, month: int) -> date:
    """The last day of *month*."""
    return date(year, month, calendar.monthrange(year, month)[1])


def add_months(day: date, months: int) -> tuple[int, int]:
    """(year, month) *months* after *day*'s month."""
    index = day.year * 12 + (day.month - 1) + months
    return index // 12, index % 12 + 1


def missing_days(
    existing: Iterable[date], today: date, months_ahead: int = MONTHS_AHEAD
) -> list[date]:
    """Posting days after *today* with no content yet, up to the end of the month
    *months_ahead* after this one. Past days are never written: a missed post is gone."""
    have = set(existing)
    horizon = month_end(*add_months(today, months_ahead))
    return [d for d in schedule.cadence() if today < d <= horizon and d not in have]


def by_month(days: Iterable[date]) -> dict[tuple[int, int], list[date]]:
    """Group days by (year, month), in order."""
    out: dict[tuple[int, int], list[date]] = {}
    for day in sorted(days):
        out.setdefault((day.year, day.month), []).append(day)
    return out


def year_rows(text: str) -> dict[tuple[int, int], MonthBrief]:
    """Parse docs/YEAR.md's month table."""
    rows: dict[tuple[int, int], MonthBrief] = {}
    for line in text.splitlines():
        m = _YEAR_ROW.match(line)
        if not m:
            continue
        cells = [c.strip() for c in m.group(3).split("|")]
        if len(cells) < 3:
            continue
        year, month = int(m.group(1)), int(m.group(2))
        web = cells[3] if len(cells) > 3 else ""
        rows[(year, month)] = MonthBrief(year, month, cells[0], cells[1], cells[2], web)
    return rows


def month_brief(year: int, month: int, year_text: str | None = None) -> MonthBrief:
    """The YEAR.md row for a month; a month outside the table still gets a usable brief."""
    text = year_text if year_text is not None else YEAR_MD.read_text()
    row = year_rows(text).get((year, month))
    if row is None:
        row = MonthBrief(
            year, month, "(no theme in docs/YEAR.md: pick from the ICP's pains)", "none", ""
        )
    return row


def existing_films(site_dir: Path) -> list[str]:
    """The mp4 files already in site/video/, by name."""
    video_dir = site_dir / "video"
    if not video_dir.is_dir():
        return []
    return sorted(p.name for p in video_dir.glob("*.mp4"))


def site_lines(site_dir: Path, sites: list[shots_mod.Site] | None = None) -> str:
    """One line per site in sites.yaml naming the shots and film that exist, for the brief."""
    lines = []
    for site in shots_mod.load_sites() if sites is None else sites:
        have = [
            rel
            for rel in (site.phone_shot, site.laptop_shot, site.film)
            if (site_dir / rel).is_file()
        ]
        files = ", ".join(have) if have else "no screenshots yet: do not write a showcase for it"
        lines.append(f"- {site.name} ({site.display_url}; {site.sector}; {site.plan}): {files}")
    return "\n".join(lines) or "- none"


def date_lines(days: Iterable[date]) -> str:
    """One line per posting day with its allowed slot(s), for the brief."""
    lines = []
    for day in days:
        slots = sorted(schedule.allowed_slots(day))
        lines.append(f"- {day:%a %d %b %Y} ({day.isoformat()}): slot {' or '.join(slots)}")
    return "\n".join(lines)


def render_brief(
    phase: str, brief: MonthBrief, days: list[date], *, python: str, films_present: list[str]
) -> str:
    """Fill deploy/briefs/<phase>.md for one month."""
    template = Template((BRIEFS / f"{phase}.md").read_text())
    named = [f for f in films_present if f in brief.films]
    if phase == "write":
        film_rule = (
            f"Both films exist in site/video/ ({', '.join(named)}): the first and third Tuesday "
            "are video posts (copy content/2026-11-17-feature-reorder-film.yaml's shape)."
            if len(named) >= 2
            else "Those films are not in site/video/ yet: write EVERY Tuesday as a feature image. "
            "The film run converts two of them later."
        )
    else:
        film_rule = ""
    quoted = f'"{python}"'
    return template.safe_substitute(
        month_name=brief.name,
        month=brief.key,
        theme=brief.theme,
        films=brief.films,
        hooks=brief.hooks or "none",
        web=brief.web or "(no angle in docs/YEAR.md: pick one from docs/WEBSITES.md)",
        sites=site_lines(ROOT / "site"),
        dates=date_lines(days),
        film_rule=film_rule,
        python=quoted,
        files="",
    )


def env_overrides(environ: dict[str, str]) -> dict[str, str]:
    """``options.env`` for the child: credentials blanked, the API key always blanked.

    The SDK builds the child env as ``{**os.environ, **options.env}``, so a blank is
    an explicit empty-string override. No API key means the CLI bills the box's Claude
    Code login.
    """
    # CLAUDE* is blanked too: run by hand from inside a Claude Code session, the child
    # would otherwise inherit that session's sockets and ids and think it is nested.
    out = {k: "" for k in environ if _SECRET_LIKE.search(k) or k.startswith("CLAUDE")}
    out["ANTHROPIC_API_KEY"] = ""
    out["PYTHONDONTWRITEBYTECODE"] = "1"
    out["DISABLE_AUTOUPDATER"] = "1"
    out["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] = "1"
    return out


# ----------------------------------------------------------------------------- sessions


async def _run_session(prompt: str, cwd: Path, *, phase: str, system_append: str) -> SessionResult:
    """One headless Claude Code session in *cwd*; the result text and whether it erred."""
    try:
        from claude_agent_sdk import ClaudeAgentOptions, query
    except ImportError:  # pragma: no cover - the unit sets Astrid's venv python
        return SessionResult(
            False, reason="claude_agent_sdk missing: run with Astrid's venv python"
        )

    tools = ["Read", "Edit", "Write", "Bash", "Grep", "Glob", "TodoWrite"]
    # The writing and review runs need no network at all (Playwright renders a local
    # file). The film run talks to the demo tenant on localhost, which a network
    # namespace would cut off, so it runs unsandboxed and relies on the brief.
    sandbox: dict[str, object] = (
        {"enabled": False}
        if phase == "film"
        else {
            "enabled": True,
            "autoAllowBashIfSandboxed": True,
            "allowUnsandboxedCommands": False,
            "network": {"deniedDomains": ["*"]},
        }
    )
    options = ClaudeAgentOptions(
        cwd=str(cwd),
        effort="medium" if phase == "review" else "high",
        tools=tools,
        allowed_tools=tools,
        disallowed_tools=["WebFetch", "WebSearch"],
        # dontAsk: the listed tools are pre-approved and anything else is denied, never
        # prompted — there is nobody at the keyboard at 02:00 on a Sunday.
        permission_mode="dontAsk",
        sandbox=sandbox,
        # No settings files: the repo's interactive hooks are for people; the rules the
        # run must keep ride in on the system prompt instead.
        setting_sources=[],
        system_prompt={"type": "preset", "preset": "claude_code", "append": system_append},
        max_turns=MAX_TURNS[phase],
        # The SDK's default 1 MB line buffer died on the first December run (2026-11-08,
        # ten posts in, 0 messages delivered): a tool result carrying two rendered PNGs
        # as base64 is bigger than that. Images and long git logs are normal here.
        max_buffer_size=128 * 1024 * 1024,
        env=env_overrides(dict(os.environ)),
        stderr=lambda line: print(f"  cli: {line.rstrip()}", file=sys.stderr, flush=True),
    )
    result = SessionResult(False)
    got_result = False

    async def _consume() -> None:
        nonlocal got_result
        async for msg in query(prompt=prompt, options=options):
            if type(msg).__name__ != "ResultMessage":
                continue
            got_result = True
            result.turns = int(getattr(msg, "num_turns", 0) or 0)
            result.cost_usd = getattr(msg, "total_cost_usd", None)
            result.text = str(getattr(msg, "result", "") or "")
            result.ok = not bool(getattr(msg, "is_error", False))
            if not result.ok:
                result.reason = str(getattr(msg, "subtype", "error"))

    try:
        await asyncio.wait_for(_consume(), timeout=TIMEOUT_S[phase])
    except TimeoutError:
        result.ok, result.reason = False, f"exceeded {TIMEOUT_S[phase] // 60} min"
    except Exception as exc:  # noqa: BLE001 - a crashed CLI is an outcome to report
        if not got_result:
            result.ok, result.reason = False, f"{type(exc).__name__}: {exc}"[:300]
    return result


def run_session(prompt: str, cwd: Path, *, phase: str, system_append: str) -> SessionResult:
    """Synchronous wrapper around the session."""
    return asyncio.run(_run_session(prompt, cwd, phase=phase, system_append=system_append))


# ----------------------------------------------------------------------------- git + checks


def run_lock_path() -> Path:
    """The lock deploy/run.sh takes too; AIREP_SOCIAL_LOCK overrides it (the tests do)."""
    return Path(os.environ.get("AIREP_SOCIAL_LOCK") or STATE_DIR / "run.lock")


@contextlib.contextmanager
def hold_run_lock(path: Path | None = None) -> Iterator[None]:
    """Wait for, then hold, the lock the Sunday push holds while it runs.

    Both commit to main. The author units used Conflicts=airep-social.service instead,
    which in systemd's default replace mode SIGTERMs whichever unit was already running:
    a push killed after Buffer took its posts but before state/pushed.json was committed.
    Python opens the file non-inheritable, so the sessions this run spawns never hold it.
    """
    path = path or run_lock_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print(f"waiting for {path}: the Sunday push is running", flush=True)
            fcntl.flock(handle, fcntl.LOCK_EX)
        yield


def sh(args: list[str], cwd: Path) -> str:
    """Run a command, raise on failure, return stdout."""
    proc = subprocess.run(args, cwd=cwd, text=True, capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(f"{' '.join(args)} failed in {cwd}:\n{proc.stderr.strip()}")
    return proc.stdout


def checks(wt: Path, python: str, report: RunReport) -> bool:
    """ruff, the unit tests and build.py, all inside the worktree."""
    ok = True
    for label, args in (
        ("ruff", [python, "-m", "ruff", "check", "."]),
        ("tests", [python, "-m", "unittest"]),
        ("build", [python, "build.py"]),
    ):
        proc = subprocess.run(args, cwd=wt, text=True, capture_output=True)
        if proc.returncode != 0:
            ok = False
            tail = (proc.stdout + proc.stderr).strip().splitlines()[-8:]
            report.fail(f"{label} failed:\n" + "\n".join(tail))
    return ok


def render_month(wt: Path, python: str, key: str, report: RunReport) -> bool:
    """Re-render every post of month *key* outside the session's sandbox.

    Chromium may not start inside the writer's network-less sandbox, and a reviewer that
    changed a field may not have re-rendered; the caller always does, one post at a time
    so a legacy or video post is left alone.
    """
    ok = True
    for path in sorted((wt / "content").glob(f"{key}-*.yaml")):
        args = [python, "build.py", "--force", "--only", path.stem]
        proc = subprocess.run(args, cwd=wt, text=True, capture_output=True)
        if proc.returncode != 0:
            ok = False
            report.fail(f"render {path.stem}: {(proc.stdout + proc.stderr).strip()[-300:]}")
    return ok


def written_days(wt: Path) -> set[date]:
    """Dates that have a valid content file in the worktree."""
    return {p.date for p in posts_mod.load_posts(wt / "content")}


def completeness(
    phase: str, wt: Path, days: list[date], brief: MonthBrief, report: RunReport
) -> bool:
    """Did the session leave what the month needs?"""
    if phase == "write":
        missing = sorted(set(days) - written_days(wt))
        if missing:
            report.fail(f"{brief.name}: no post for " + ", ".join(d.isoformat() for d in missing))
            return False
        return True
    # film: at least one Tuesday of the month now carries a video that exists on disk
    videos = [
        p
        for p in posts_mod.load_posts(wt / "content")
        if p.date.strftime("%Y-%m") == brief.key and p.video and (wt / "site" / p.video).is_file()
    ]
    if not videos:
        report.fail(f"{brief.name}: no Tuesday post uses a film that exists in site/video/")
        return False
    report.say(
        f"{brief.name}: {len(videos)} video post(s): " + ", ".join(p.video or "" for p in videos)
    )
    return True


def worktree_for(phase: str, key: str, report: RunReport) -> tuple[Path, str, bool] | None:
    """(worktree, branch, resumed): a fresh worktree off main, or an earlier attempt's.

    None when a leftover worktree is on some other branch, which a person must look at.
    """
    wt = STATE_DIR / "worktrees" / f"{phase}-{key}"
    branch = f"author/{phase}-{key}"
    if wt.exists():
        # An earlier attempt was cut short (a crashed CLI, a reboot). Its files are work
        # already paid for, so the run continues in the same worktree; the brief tells
        # the session to keep what is there and finish the month.
        head = sh(["git", "rev-parse", "--abbrev-ref", "HEAD"], wt).strip()
        if head != branch:
            report.fail(
                f"{wt} is on {head}, not {branch}: inspect it, then `git worktree remove` it"
            )
            return None
        report.say(f"resuming the earlier attempt in {wt}")
        return wt, branch, True
    wt.parent.mkdir(parents=True, exist_ok=True)
    existing = sh(["git", "branch", "--list", branch], ROOT).strip()
    if existing:
        sh(["git", "branch", "-D", branch], ROOT)  # an empty leftover: its worktree is gone
    sh(["git", "worktree", "add", "-b", branch, str(wt), "main"], ROOT)
    return wt, branch, False


def catch_up(wt: Path, report: RunReport) -> bool:
    """Merge main into the worktree, so a fix that landed meanwhile applies before validation.

    The first December run (2026-11-08) was held up by a test fixed on main while its
    worktree still carried the old one.
    """
    proc = subprocess.run(
        ["git", "merge", "--no-edit", "main"], cwd=wt, text=True, capture_output=True
    )
    if proc.returncode != 0:
        subprocess.run(["git", "merge", "--abort"], cwd=wt, capture_output=True)
        report.fail(f"merging main into the worktree failed:\n{proc.stderr.strip()[-300:]}")
        return False
    return True


def has_review_commit(wt: Path, base: str) -> bool:
    """True when a review session already committed in this worktree."""
    subjects = sh(["git", "log", "--format=%s", f"{base}..HEAD"], wt)
    return any(line.startswith("review:") for line in subjects.splitlines())


def disallowed_changes(paths: Iterable[str]) -> list[str]:
    """Paths a session changed that are not its to change."""
    return sorted(p for p in paths if p and not p.startswith(ALLOWED_PREFIXES))


def session_paths(wt: Path, base: str) -> list[str]:
    """Every path the session's own commits touched (first-parent, so a main merged in by
    catch_up does not count against it)."""
    shas = sh(["git", "log", "--first-parent", "--no-merges", "--format=%H", f"{base}..HEAD"], wt)
    paths: set[str] = set()
    for sha in shas.split():
        paths.update(sh(["git", "show", "--name-only", "--format=", sha], wt).split("\n"))
    return sorted(p for p in paths if p)


def guard(wt: Path, base: str, report: RunReport) -> bool:
    """Refuse to merge a session that edited anything outside content and media."""
    bad = disallowed_changes(session_paths(wt, base))
    if bad:
        report.fail("session changed files outside content/ and site/: " + ", ".join(bad))
        return False
    return True


def shipped_refresh_due(
    today: date, post_list: list[posts_mod.Post], pushed: dict[str, object]
) -> posts_mod.Post | None:
    """This month's `shipped` post when the run falls in the month's first week and Buffer
    does not hold it yet. It was written two months early, so its changelog is rewritten
    from the month that has just ended."""
    if today.day > 7:
        return None
    for post in post_list:
        if post.slot == "shipped" and (post.date.year, post.date.month) == (
            today.year,
            today.month,
        ):
            return None if post.slug in pushed else post
    return None


def refresh_shots(python: str, report: RunReport) -> None:
    """Retake the site screenshots on main before a writing run, so a showcase shows the
    site as it is this month; a film is made only for a site that has none yet.

    Runs here, outside the writer's network-less sandbox, and commits straight to main:
    the worktree is cut after this, so the session sees the fresh files. A failure (a
    site down, no network) is reported and the run carries on with last month's shots.
    """
    try:
        proc = subprocess.run(
            [python, "shots.py"], cwd=ROOT, text=True, capture_output=True, timeout=SHOTS_TIMEOUT_S
        )
    except subprocess.TimeoutExpired:
        report.say("⚠ shots.py timed out; keeping last month's screenshots")
        return
    if proc.returncode != 0:
        tail = (proc.stdout + proc.stderr).strip().splitlines()[-4:]
        report.say("⚠ shots.py had failures; keeping what it could take:\n" + "\n".join(tail))
    changed = sh(["git", "status", "--porcelain", "--", "site/shots", "site/video"], ROOT).strip()
    if not changed:
        report.say("site screenshots unchanged")
        return
    sh(["git", "add", "site/shots", "site/video"], ROOT)
    sh(["git", "commit", "-q", "-m", "chore(shots): refresh the site screenshots"], ROOT)
    sh(["git", "push", "origin", "main"], ROOT)
    report.say(f"site screenshots refreshed ({len(changed.splitlines())} file(s))")


def land(wt: Path, branch: str, base: str, report: RunReport) -> bool:
    """Merge the worktree's commits into main and push; tidy the worktree."""
    count = int(sh(["git", "rev-list", "--count", f"{base}..HEAD"], wt).strip() or 0)
    # Checked before the empty case: a session that ended ok without committing (a film
    # run's mp4s, a refreshed caption whose PNG did not change) has no commits, and the
    # forced remove below would delete its work while reporting success.
    dirty = sh(["git", "status", "--porcelain"], wt).strip()
    if dirty:
        report.fail(f"uncommitted changes left in {wt}; not merged")
        return False
    if count == 0:
        report.say("nothing committed; worktree removed")
        sh(["git", "worktree", "remove", "--force", str(wt)], ROOT)
        sh(["git", "branch", "-D", branch], ROOT)
        return True
    sh(["git", "merge", "--no-edit", branch], ROOT)
    sh(["git", "push", "origin", "main"], ROOT)
    sh(["git", "worktree", "remove", str(wt)], ROOT)
    sh(["git", "branch", "-d", branch], ROOT)
    report.say(f"merged {count} commit(s) into main and pushed")
    return True


def notify(report: RunReport) -> None:
    """Best-effort Telegram summary through the same Astrid webhook push.py uses."""
    try:
        env = push.load_env(require_secrets=False)
    except Exception as exc:  # noqa: BLE001 - the env file is optional here
        print(f"(no Telegram: {exc})")
        return
    url = env.get("ASTRID_WEBHOOK_URL", "")
    if not url:
        return
    head = "AIREP social author" + ("" if report.ok else " FAILED")
    text = "\n".join([f"{head} · {report.phase} · {datetime.now():%a %d %b %H:%M}", *report.lines])[
        :3500
    ]
    try:
        push.notify(url, env.get("ASTRID_WEBHOOK_SECRET", ""), text)
    except Exception as exc:  # noqa: BLE001
        print(f"(Telegram failed: {exc})")


# ----------------------------------------------------------------------------- phases


def system_append(wt: Path) -> str:
    """The repo's CLAUDE.md plus the unattended-run rules."""
    rules = (wt / "CLAUDE.md").read_text()
    return (
        rules + "\n\n## This is an unattended run\n"
        "Nobody will answer a question: decide and proceed. Never run `git push`, never run "
        "`push.py --live`, never touch `state/`. Change only `content/`, `site/images/` and "
        "`site/video/`: tests, templates, the Python and `deploy/` are not yours, and a commit "
        "that touches them is refused. Commit your work in this worktree when it passes "
        "`ruff check .` and the unit tests; the caller merges it."
    )


def phase_write(
    today: date, python: str, report: RunReport, *, dry_run: bool, only: str | None
) -> None:
    """Write every missing month up to MONTHS_AHEAD, each in its own session, then review it."""
    have = {p.date for p in posts_mod.load_posts()}
    months = by_month(missing_days(have, today))
    if only:
        y, m = (int(x) for x in only.split("-"))
        months = {k: v for k, v in months.items() if k == (y, m)}
    if not months:
        until = calendar.month_name[add_months(today, MONTHS_AHEAD)[1]]
        report.say(f"content already written to the end of {until}")
        return
    if not dry_run:
        refresh_shots(python, report)  # before render_brief, which lists the shots present
    films = existing_films(ROOT / "site")
    for (year, month), days in months.items():
        brief = month_brief(year, month)
        prompt = render_brief("write", brief, days, python=python, films_present=films)
        report.say(f"{brief.name}: {len(days)} posting day(s) to write")
        if dry_run:
            print(prompt)
            continue
        base = sh(["git", "rev-parse", "HEAD"], ROOT).strip()
        made = worktree_for("write", brief.key, report)
        if made is None:
            return
        wt, branch, resumed = made
        # A resumed attempt may already hold every post, and the review: a session is
        # not re-run for work that is done (the sessions are paid for in plan allowance).
        have_all = resumed and not (set(days) - written_days(wt))
        reviewed = have_all and has_review_commit(wt, base)
        res = SessionResult(True)
        if have_all:
            report.say("  writer: skipped, the earlier attempt wrote every day")
        else:
            res = run_session(prompt, wt, phase="write", system_append=system_append(wt))
            report.say(f"  writer: {'ok' if res.ok else 'failed ' + res.reason}, {res.turns} turns")
        if reviewed:
            report.say("  reviewer: skipped, the earlier attempt reviewed the month")
        elif res.ok:
            render_month(wt, python, brief.key, report)  # so the reviewer can see the PNGs
            review = Template((BRIEFS / "review.md").read_text()).safe_substitute(
                month_name=brief.name,
                month=brief.key,
                python=f'"{python}"',
                files="\n".join(
                    f"- content/{p.name}"
                    for p in sorted((wt / "content").glob(f"{brief.key}-*.yaml"))
                ),
            )
            rev = run_session(review, wt, phase="review", system_append=system_append(wt))
            report.say(
                f"  reviewer: {'ok' if rev.ok else 'failed ' + rev.reason}, {rev.turns} turns"
            )
            if rev.text:
                report.say("  " + rev.text.strip().splitlines()[0][:200])
            render_month(wt, python, brief.key, report)  # the reviewer's edits, rendered
            # The sessions commit their own work; a re-render that changed bytes is ours.
            if sh(["git", "status", "--porcelain", "--", "site/images"], wt).strip():
                sh(["git", "add", "site/images"], wt)
                sh(["git", "commit", "-q", "-m", f"chore(build): render {brief.name} posts"], wt)
        good = (
            res.ok
            and guard(wt, base, report)
            and catch_up(wt, report)
            and checks(wt, python, report)
            and completeness("write", wt, days, brief, report)
        )
        if not good or not land(wt, branch, base, report):
            report.fail(f"{brief.name} not merged; worktree kept at {wt}")
            return


def phase_film(
    today: date, python: str, report: RunReport, *, dry_run: bool, only: str | None
) -> None:
    """Film the month-after-next's two videos and convert its Tuesday posts to use them."""
    year, month = (int(x) for x in only.split("-")) if only else add_months(today, MONTHS_AHEAD)
    brief = month_brief(year, month)
    if "(existing)" in brief.films or brief.films.strip().lower() == "none":
        report.say(f"{brief.name}: films already exist ({brief.films}); nothing to film")
        return
    days = [
        d for d in schedule.cadence() if (d.year, d.month) == (year, month) and d.weekday() == 1
    ]
    prompt = render_brief(
        "film", brief, days, python=python, films_present=existing_films(ROOT / "site")
    )
    report.say(f"{brief.name}: films to make: {brief.films}")
    if dry_run:
        print(prompt)
        return
    base = sh(["git", "rev-parse", "HEAD"], ROOT).strip()
    made = worktree_for("film", brief.key, report)
    if made is None:
        return
    wt, branch, _resumed = made
    res = run_session(prompt, wt, phase="film", system_append=system_append(wt))
    report.say(f"  filmer: {'ok' if res.ok else 'failed ' + res.reason}, {res.turns} turns")
    if res.text:
        report.say("  " + res.text.strip().splitlines()[0][:200])
    good = (
        res.ok
        and guard(wt, base, report)
        and catch_up(wt, report)
        and checks(wt, python, report)
        and completeness("film", wt, days, brief, report)
    )
    if not good or not land(wt, branch, base, report):
        report.fail(f"{brief.name} films not merged; worktree kept at {wt}")


def phase_shipped(today: date, python: str, report: RunReport, *, dry_run: bool) -> None:
    """First week of a month: rewrite this month's provisional `shipped` post from the
    month that has just ended, so a changelog never goes out two months stale."""
    post = shipped_refresh_due(today, posts_mod.load_posts(), state_mod.load_state())
    if post is None:
        return
    py, pm = add_months(today, -1)
    prev_month = f"{calendar.month_name[pm]} {py}"
    prompt = Template((BRIEFS / "shipped.md").read_text()).safe_substitute(
        file=f"content/{post.slug}.yaml",
        slug=post.slug,
        prev_month=prev_month,
        since=date(py, pm, 1).isoformat(),
        until=date(today.year, today.month, 1).isoformat(),
        python=f'"{python}"',
    )
    report.say(f"{post.slug}: refreshing the changelog for {prev_month}")
    if dry_run:
        print(prompt)
        return
    base = sh(["git", "rev-parse", "HEAD"], ROOT).strip()
    made = worktree_for("shipped", f"{today.year:04d}-{today.month:02d}", report)
    if made is None:
        return
    wt, branch, _resumed = made
    res = run_session(prompt, wt, phase="shipped", system_append=system_append(wt))
    report.say(f"  refresher: {'ok' if res.ok else 'failed ' + res.reason}, {res.turns} turns")
    if res.text:
        report.say("  " + res.text.strip().splitlines()[0][:200])
    if res.ok:
        subprocess.run(
            [python, "build.py", "--force", "--only", post.slug], cwd=wt, capture_output=True
        )
        if sh(["git", "status", "--porcelain", "--", "site/images"], wt).strip():
            sh(["git", "add", "site/images"], wt)
            sh(["git", "commit", "-q", "-m", f"chore(build): render {post.slug}"], wt)
    good = (
        res.ok and guard(wt, base, report) and catch_up(wt, report) and checks(wt, python, report)
    )
    if not good or not land(wt, branch, base, report):
        report.fail(f"{post.slug} not refreshed; worktree kept at {wt}")


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("phase", choices=("write", "film"))
    parser.add_argument(
        "--dry-run", action="store_true", help="print the plan and briefs; no session"
    )
    parser.add_argument("--month", help="YYYY-MM: only this month (write) or this month's films")
    parser.add_argument("--today", help="YYYY-MM-DD, with --dry-run only")
    parser.add_argument("--python", default=os.environ.get("AIREP_SOCIAL_PYTHON") or sys.executable)
    args = parser.parse_args(argv)
    if args.today and not args.dry_run:
        parser.error("--today is a dry-run aid")
    today = date.fromisoformat(args.today) if args.today else datetime.now(schedule.AEST).date()

    report = RunReport(args.phase)
    # A dry run commits nothing, so it never waits on (or holds up) the Sunday push.
    with contextlib.nullcontext() if args.dry_run else hold_run_lock():
        try:
            # Inside the try: a pull that fails (main diverged, no network at 02:00) is a
            # failed run like any other and must reach Telegram, not only the journal.
            if not args.dry_run:
                sh(["git", "pull", "--ff-only"], ROOT)
            if args.phase == "write":
                phase_write(today, args.python, report, dry_run=args.dry_run, only=args.month)
                if not args.month:  # a one-month rerun by hand is not the monthly run
                    phase_shipped(today, args.python, report, dry_run=args.dry_run)
            else:
                phase_film(today, args.python, report, dry_run=args.dry_run, only=args.month)
        except RuntimeError as exc:
            report.fail(str(exc))
        if not args.dry_run:
            notify(report)
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
