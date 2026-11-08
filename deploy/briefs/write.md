# Write the AIREP social posts for $month_name

You are a headless Claude Code run inside a git worktree of `airep-social`. Nobody will
answer a question, so decide and proceed. CLAUDE.md (in your system prompt) is law:
company voice, caption rules, real dates, nothing unshipped, no invented numbers.

## What to write

One `content/YYYY-MM-DD-<slug>.yaml` per posting day below. The slot is fixed by the
weekday; `posts.py` refuses anything else.

$dates

- Theme for the month: $theme
- Dated hooks: $hooks
- Films named for this month: $films. $film_rule

## The Thursday mix

`shipped` on the last Thursday (three real, user-facing changes from
`git -C ../../airep/airep log --since="<first of the month before>" --format="%ad %s" --date=short`,
dated, no internal refactors); a `date_post` for each dated hook above; `price` once;
`pain` on the rest.

## The Fridays: Intelli AI's website-build service (slot `website`)

Fridays sell websites, not AIREP: a different reader (a tradie, a studio, a shop wanting
a site) and a different link. This month's angle: $web

- Facts and prices come from `docs/WEBSITES.md` only ($2,500 + GST build, from $30 + GST
  a month, live in about two weeks, you own it, no lock-in). Every Friday caption links
  `https://intelliai.au/websites/` exactly once; never `/pricing/`.
- The only sites a post may show, and the screenshots and films that exist for them:
$sites
  A site not on that list is never shown or named, whatever you know about it.
- The mix: first Friday a showcase (`template: website`, `fields.shot:` one of the
  screenshots above, `fields.frame: phone` or `laptop`, chips in `rows: [{text: …}]`, a
  footer line, and `sub` from that site's facts in `sites.yaml`); second Friday a web
  Field Note (`template: field_note` with `foot_link: "intelliai.au/websites →"`); third
  Friday the scroll film of a site that has one (`video: video/website_<slug>_scroll.mp4`,
  `thumbnail_offset_ms: 0`), else a showcase; fourth Friday the offer card
  (`template: price` with `foot_link: "intelliai.au/websites →"` and the three plans);
  a fifth Friday a showcase. Rotate the sites so none appears twice in the month.
- Hashtags default to `[WebDesign, SmallBusiness, Australia]` for this slot; a post about
  one site may swap the third for its city (`Ipswich`, `Brisbane`, `Melbourne`).
- Voice stays the company's. Say what the site does for the business and what it cost
  to build, never "stunning", never adjectives about design.

## How

0. If `content/` already holds files for this month, an earlier attempt wrote them and
   was cut short: keep them (fix anything that breaks a rule), write only the missing
   days, and still render, test and commit everything below.
1. Read `docs/YEAR.md`, two existing files of each slot in `content/`, and
   `templates/<slot>.html` to see which fields each template takes.
2. Check every feature claim against the airep code in `../../airep/airep` (grep the
   view, model or template) before writing it. A claim you cannot verify is not toned
   down; write a different post.
3. Mock-screen numbers come from the seeded Northwind Commercial Kitchens data
   (`core/management/commands/seed_demo_data.py` in airep). Never invent customers,
   quotes or statistics.
4. Render with $python build.py, then open each new PNG under `site/images/`
   with the Read tool. Shorten any copy that overflows or clips; headline emphasis is
   one italic phrase. If Chromium cannot start inside this sandbox, carry on without the
   render: the caller renders every post after you, and the review run looks at them.
5. `ruff check .` and $python -m unittest must pass.
6. `git add content site/images` and `git commit -m "feat(content): $month_name posts"`.
   Do not push. Do not run `push.py --live`. Do not touch `state/`.

Finish with a short report: the files written, any claim you could not verify and so
avoided, and anything a human should look at.
