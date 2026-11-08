# airep-social

A year of organic LinkedIn and Facebook posts for [AIREP](https://intelliai.au), Intelli
AI's ERP, with no weekly step for anyone. One YAML file per post in `content/`, images
rendered from HTML templates, films from the AIREP film rig, everything scheduled through
Buffer by a Sunday timer on the home box. The plan behind it is the
[AIREP Organic Social Plan](https://claude.ai/artifact/27LBWaY3iycCT6Nd321GGQ) (2026-11-03).

The repo is **public on purpose**: Buffer has no upload API and fetches each asset from a
public URL (HEAD first, then GET), so GitHub Pages serves this repo's `site/` folder at
`https://intelliai-au.github.io/airep-social/site/`. The captions are public a fortnight
early, which is fine.

## Layout

| Path | What |
|------|------|
| `content/YYYY-MM-DD-slug.yaml` | One post: date, slot, both captions, the asset (image + template fields, or a film) |
| `templates/` | The HTML templates (`field_note`, `feature`, `pain`, `shipped`, `price`, `date_post`) and `base.css` |
| `site/images/` | Rendered PNGs (2160 × 2160; the pain series is 2160 × 1130), committed |
| `site/video/` | The six scored 4:5 films from 2026-09-06 |
| `assets/legacy/` | The 2026 PNG series (Field Notes, Feature Posts, Switcher, LinkedIn ads, trial). No Founder image |
| `state/pushed.json` | Every Buffer post id `push.py` has created, by slug and channel |
| `schedule.py` | Cadence, AEST due times, the fortnight plan (pure) |
| `posts.py` | Loads and validates `content/` |
| `build.py` | Renders missing PNGs with Playwright; flattens legacy PNGs to RGB |
| `push.py` | Schedules the next 14 days in Buffer; dry run by default |
| `deploy/` | The systemd user units and the script the timer runs |

## Cadence

Three slots a week, the same asset on both pages, LinkedIn at 07:30 and Facebook at
18:30 AEST (Brisbane has no daylight saving):

- **Tuesday** `feature`: a feature image, or one of the films twice a month
- **Wednesday** `field_note`: one AU compliance or operations fact as a card
- **Thursday** `pain`, `price`, `shipped` (this month's changes from the airep log) or `date_post`

22 Dec to 4 Jan keeps only the Tuesday post. The calendar runs Tue 17 Nov 2026 to
Thu 11 Nov 2027. `posts.py` refuses a file whose slot does not match its weekday.

## How the timer runs

Every Sunday at 18:00 AEST, `airep-social.timer` starts `airep-social.service`, which
runs `deploy/run.sh`:

1. `git pull --ff-only`
2. `build.py`: render any post image that does not exist yet (Playwright, Chromium from
   Astrid's venv, 1080 CSS px at device scale 2). Commit and push `site/images/`, wait
   for Pages.
3. `push.py --live`: for every post dated in the next 14 days whose channel is not yet
   in `state/pushed.json`, HEAD-check the asset URL (retrying for ~3.5 min while Pages rebuilds), then `createPost` with
   `mode: customScheduled` and the slot's `dueAt`. At most **6 posts a channel** per
   run, so Buffer's Free plan (10 queued a channel) never overflows. Both channels are
   checked for `isDisconnected` first.
4. Commit and push `state/pushed.json`.
5. A Telegram message arrives through Astrid: what was queued, each asset's link, the
   next post, and any alert (page disconnected, asset not reachable, content running
   out).

Everything is idempotent, so a failed run can simply run again.

### Install (not yet installed; Keiran's call)

```
# Same style as linux-setup/install.sh: copy the units, reload, enable the timer.
install -m 644 deploy/airep-social.service deploy/airep-social.timer \
    deploy/airep-social-author@.service deploy/airep-social-author@write.timer \
    deploy/airep-social-author@film.timer ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now airep-social.timer airep-social-author@write.timer \
    airep-social-author@film.timer
systemctl --user list-timers 'airep-social*'        # Sunday 18:00, 1st and 3rd Sunday 02:00
```

Run an authoring phase now, watched: `systemctl --user start airep-social-author@write`
then `journalctl --user -u airep-social-author@write -f`.

Keep `linux-setup/systemd/` in step if you want the box rebuilt from there: copy the two
units into it as well.

The first run is worth watching: `systemctl --user start airep-social.service` then
`journalctl --user -u airep-social.service -f`. The plan's own step 7 is a dry run of one
test post per channel 30 minutes ahead; do that by hand with a throwaway content file
before trusting the timer.

## Dry run

```
python push.py                      # today; prints the plan and the Telegram text, sends nothing
python push.py --today 2026-11-15   # pretend it is that Sunday
```

Only `python push.py --live` talks to Buffer and Telegram, and it refuses `--today`: a
pretend date would hand Buffer posts whose `dueAt` is already behind us.

## Vetoing a post

There is no approval gate. Today: open Buffer > Publishing > the channel's Queue and
delete the post before its time. Planned (plan doc, step 7, in Astrid): a Telegram card
per queued post with a **Skip** button that deletes it in Buffer, which works until the
minute it publishes, and a **Posted** card with the live links after each slot. No API
open to us deletes a published post (Buffer says published posts cannot be deleted from
Buffer, Meta's Graph API restricts Page-post deletion to select developers, LinkedIn's
Page API is partner-only), so after publishing it is two taps in the app from the link. `state/pushed.json` still lists it, so the timer will not re-create
it; to run it again later, remove its entry from `state/pushed.json` and the next Sunday
picks it up (if still inside the horizon).

## When Facebook (or LinkedIn) loses authorisation

Buffer emails "no longer authorized" (it did on 2026-05-25) and the Sunday message carries
a `⚠ facebook page is no longer authorised` line until it is fixed. Only the page admin
can fix it: Buffer > Channels > the page > **Reconnect**, sign in to Facebook as the page
admin, and grant the same permissions again. Posts already queued for that channel stay in
Buffer and publish once reconnected; posts the timer skipped are not in
`state/pushed.json`, so the next run schedules them if they are still ahead.

## Filling the env file

`push.py --live` reads `~/.config/airep-social/env` and refuses any mode but 600:

```
mkdir -p ~/.config/airep-social
cp env.example ~/.config/airep-social/env
chmod 600 ~/.config/airep-social/env
```

Then fill in (with the hidden-prompt script, never in chat):

- `BUFFER_API_KEY`: Buffer > Settings > API (the "AIREP" key of 2026-05-28, or a fresh one).
- `BUFFER_LINKEDIN_CHANNEL_ID`, `BUFFER_FACEBOOK_CHANNEL_ID`: once the key is in,
  `python push.py --channels` prints every channel with its id.
- `ASTRID_WEBHOOK_URL` (and `ASTRID_WEBHOOK_SECRET`): in Telegram, `/webhook create`
  with source `generic`, as the Google Ads weekly report uses; the URL is
  `https://nova-kjef.onrender.com/webhooks/<id>`.

## Legacy assets

`assets/legacy/` holds the 2026 PNG series. Which of them already ran on each page is
unknown: ask Buffer (`buffer_api.sent_posts`, or Buffer > Publishing > Sent) before
scheduling one again. To reuse one, reference it as `image: images/legacy/<file>.png`
and `build.py` copies it into `site/` flattened to RGB (LinkedIn and Facebook reject
transparent PNGs). The `AIREP-Founder-*` image is deliberately not here.

## Writing more: the authoring runs (Max login, not the swarm)

`author.py` writes and films ahead with headless Claude Code sessions started through the
Agent SDK with the API key blanked, so they bill the subscription the box is logged in
with (Keiran's Max plan) and never the API or the swarm's budget (his call, 2026-11-08).

- `airep-social-author@write.timer`, first Sunday of the month at 02:00: for every month
  with missing posting days up to the end of the month after next, one session writes
  the month from `deploy/briefs/write.md` and `docs/YEAR.md`, a second session reviews it
  (`deploy/briefs/review.md`), then the script runs `ruff`, the tests and `build.py`,
  checks every day has a post, and merges the worktree into main.
- `airep-social-author@film.timer`, third Sunday at 02:00: one session films the
  month-after-next's two videos with the rig in the airep repo
  (`deploy/briefs/film.md`) and turns that month's first and third Tuesday posts into
  video posts. It runs unsandboxed because the rig talks to a local server.
- A run that fails its checks merges nothing, keeps its worktree under
  `~/.local/state/airep-social/worktrees/` for inspection, and says so on Telegram. A
  video Tuesday whose film never arrived simply stays a feature image.
- `python author.py write --dry-run` prints the months and the exact briefs without
  starting a session; `--month 2027-02` limits a run to one month.

By hand, the same thing is a YAML file per post, `python build.py` to render it, and
`python -m unittest` and `ruff check .` to keep it honest.

## Tests

```
python -m unittest -v
ruff check .
```

The tests cover the cadence and Christmas gap, the 6-a-channel cap, the dry run, the
state file, the content rules and `build.py`'s skip-existing logic. They never touch
Buffer or the network.
