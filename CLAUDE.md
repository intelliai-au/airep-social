# CLAUDE.md — airep-social

The machinery behind the **AIREP Organic Social Plan**
(https://claude.ai/artifact/27LBWaY3iycCT6Nd321GGQ, 2026-11-03). That doc is the source
of truth for every design choice: cadence, voice, formats, the veto-not-approval rule,
hashtags. Change a choice there, then here.

## What this repo is

A year of LinkedIn Page + Facebook Page posts for Intelli AI's ERP, AIREP, plus a Friday
post for Intelli AI's website-build service (since 2026-11-08), scheduled through Buffer
by a Sunday timer on the home box. **From 23 Nov 2026 to 26 Feb 2027 the plan is
website-led** (see "The website-led quarter" below). **The plan has been stopped since
16 Nov 2026:** the timers are disabled and the Buffer queue is empty. Keiran decides when
it goes live again. `content/` holds one YAML per post,
`build.py` renders the images, `push.py` schedules the next fortnight, `site/` is served
by GitHub Pages so Buffer can fetch each asset from a public URL. See README.md.

## Rules a writing session must keep

- **Company voice only.** Every caption is Intelli AI, the company. Nothing is written as
  Keiran, and the legacy `AIREP-Founder-*` image is excluded (his 2026-10-25 decision).
- **One image or one video, at most three short lines and one link to intelliai.au.**
  `posts.py` enforces the line count and the link; LinkedIn gets at most three hashtags
  (`#ERP #SmallBusiness #Australia` by default), Facebook none.
- **A feature post names only what is on airep main today.** Check the claim in
  `../airep/airep` before writing it; a post about something unshipped is refused, not
  toned down.
- **Never:** invented customer quotes or statistics, competitor names, stock photos,
  AI-generated pictures of people. Mock screens use the seeded Northwind Commercial
  Kitchens demo data (`core/management/commands/seed_demo_data.py` in airep).
- **Dated posts carry real dates:** BAS 28 Feb / 28 Apr / 28 Jul / 28 Oct, STP
  finalisation 14 Jul, EOFY 30 Jun.
- **Cadence:** Tue `feature` (image, or film twice a month), Wed `field_note`, Thu one
  of `pain` / `price` / `shipped` / `date_post`, Fri `website`. Inside the website-led
  quarter it is Tue `website` or `feature`, Wed `website`, Thu `website`. 22 Dec to 4 Jan
  keeps only Tuesday. `posts.py` refuses a slot on the wrong weekday.
- **`website` posts** sell the website-build service, not AIREP. Prices and promises come
  from `docs/WEBSITES.md` (a mirror of intelliai.au's front page): $2,500 + GST with every
  feature included, then "Hosting and fixes" at $120 + GST a month. Never $80 or a
  hosting-only price. The caption links `https://intelliai.au/` once, never `/websites/`
  (now only a redirect), and the `foot_link` is `"intelliai.au →"`. A showcase shows only a site in
  `sites.yaml` (live client sites already listed on intelliai.au/work/), with facts from
  there; a pitch demo or a concept site for a business that has not said yes is never
  shown, named or hinted at. The screenshots under `site/shots/` are taken by
  `shots.py` on main before a writing run; a content session never edits them. No design
  adjectives, no claims about a client's results. Organic only: no paid ads.
- **Secrets** live only in `~/.config/airep-social/env` (mode 600). Never read the
  Buffer key out of a database, never write one into the tree, never print one.
- **`push.py` is a dry run unless `--live`.** Never run `--live` from a session; the
  timer does, on Sundays.

## The website-led quarter (23 Nov 2026 to 26 Feb 2027)

Keiran's call on 18 Nov 2026: three months that lead with website sales. The posts are
all written already, about half of them films.

- **Slots** (`schedule.WEBSITE_LED_SLOTS`): Tue is `website` or `feature`, and Wed and
  Thu are `website`. An AIREP `feature` runs at most once a fortnight, on a Tuesday, and
  links `https://intelliai.au/airep/`. That is an editorial rule; the code doesn't
  enforce it.
- **Reserved days** (`schedule.RESERVED`): Wed 2 Dec, Wed 16 Dec, Wed 13 Jan and Wed 3 Feb
  carry the four intelliai.au front-page films (`website-film-spreadsheets`,
  `-one-invoice`, `-software`, `-demo` in airep `core/static/core/video/`, in that order),
  copied to `site/video/website_film_<name>_9x16.mp4` on 18 Nov 2026. The author run
  skips them. Each film sits after the post on the same theme (1 Dec five logins, 15 Dec
  the monthly, 12 Jan the software bill); to swap two days, rename the files and change
  `date:`. If the front page's prices change, re-copy the films (airep's
  `test_the_films_prices_match_the_page` keeps them matched there).
- **Christmas:** the posts on 22 Dec and 29 Dec don't push the 48-hour demo.
- **Films:** `shots.py` films each site in `sites.yaml` (`website_<slug>_scroll.mp4`,
  `website_<slug>-pricing_scroll.mp4` and similar, plus `website_<slug>_laptop.mp4`).
  Each site's `hide:` list covers anything that names a person or a live count, such as
  GRIPswich's coach names, places left and members' board. The bakery films
  (`website_film_9x16.mp4`, `website_film_16x9.mp4`) are copies of the front page's
  `website-film`.
- After 26 Feb the AIREP grid resumes, unless Keiran extends the window.

## Writing a month (the `write` author run, or a session by hand)

`author.py write` does the steps below unattended on the box's Claude Code login (the
Max subscription, never an API key), on the first Sunday of each month, keeping content
written to the end of the month after next; `author.py film` makes a month's two videos
on the third Sunday. **The swarm lane is not used for content** (Keiran, 2026-11-08).
Buffer stays on the **Free plan**: `push.py` never leaves more than six queued a channel
(`schedule.CHANNEL_CAP`, counting what earlier Sundays queued).
A session asked to "write <month>" by hand follows the same steps; `deploy/briefs/`
holds the exact briefs the runs use. A content session changes only `content/`,
`site/images/` and `site/video/`: never tests, templates, the Python, `deploy/`,
`sites.yaml` or `site/shots/`.

1. Read the month's theme, films, dated hooks and website angle in `docs/YEAR.md` (a
   copy of the plan doc's month table, kept in step with it).
2. Add one `content/YYYY-MM-DD-<slug>.yaml` per cadence day (`python -c "import
   schedule; print(schedule.cadence())"` lists them). Copy an existing file of the same
   slot for the field layout; `templates/<slot>.html` shows what each field is.
3. `python build.py` renders the missing PNGs (Astrid's venv has Playwright + Chromium:
   `../nova/Nova/venv/bin/python`). Look at the PNGs before committing them.
4. `python -m unittest` and `ruff check .` must be green. Commit content + images.

## Validation

```
ruff check . && python -m unittest -v
python push.py --today 2026-11-15      # dry run of a Sunday; sends nothing
```
