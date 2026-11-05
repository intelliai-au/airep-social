# CLAUDE.md — airep-social

The machinery behind the **AIREP Organic Social Plan**
(https://claude.ai/artifact/27LBWaY3iycCT6Nd321GGQ, 2026-11-03). That doc is the source
of truth for every design choice: cadence, voice, formats, the veto-not-approval rule,
hashtags. Change a choice there, then here.

## What this repo is

A year of LinkedIn Page + Facebook Page posts for Intelli AI's ERP, AIREP, scheduled
through Buffer by a Sunday timer on the home box. `content/` holds one YAML per post,
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
  of `pain` / `price` / `shipped` / `date_post`. 22 Dec to 4 Jan keeps only Tuesday.
  `posts.py` refuses a slot on the wrong weekday.
- **Secrets** live only in `~/.config/airep-social/env` (mode 600). Never read the
  Buffer key out of a database, never write one into the tree, never print one.
- **`push.py` is a dry run unless `--live`.** Never run `--live` from a session; the
  timer does, on Sundays.

## Writing a month ("write <month>" lane item)

1. Read the month's theme, films and dated hooks in the plan doc's month table.
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
