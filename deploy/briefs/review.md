# Review the new posts for $month_name

You are a second, independent headless run. Another run just wrote the files below.
Nobody will answer a question. Check each file against CLAUDE.md and `docs/YEAR.md`:

- Voice: Intelli AI, the company. Never first person singular, never Keiran, no
  "thought leadership" prose, no exclamation marks.
- Captions: at most four short lines each, one intelliai.au link, hashtags only through
  the `hashtags` list (LinkedIn), the Facebook caption shorter than LinkedIn's.
- Every feature claim exists on airep main (`../../airep/airep`); every date is right
  (BAS 28 Feb / 28 Apr / 28 Jul / 28 Oct, STP finalisation 14 Jul, EOFY 30 Jun).
- No competitor names, no invented customers, quotes or statistics; mock screens use
  the seeded Northwind data.
- Open each rendered PNG with the Read tool: no clipped or overflowing text, one italic
  emphasis phrase in the headline, the kicker labels short.
- Friday `website` posts: every price and promise matches `docs/WEBSITES.md`; the caption
  links `intelliai.au/websites/` once; the site shown is in `sites.yaml` and its facts
  come from there; `fields.shot` names a file that exists under `site/shots/`; no
  design adjectives, no claims about the client's results.

Fix what you can in place, then re-render that post with
$python build.py --force --only <slug> (if Chromium cannot start inside this
sandbox, carry on: the caller re-renders every post of the month after you). Delete a
post that cannot be made honest (and its PNG) and say so. Then `ruff check .`, $python -m unittest,
and `git commit -am "review: $month_name posts"` if you changed anything. Do not push.

Files:
$files

Report in a few lines: what you changed, what you deleted and why, what remains for a
human to look at.
