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

## How

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
   one italic phrase.
5. `ruff check .` and $python -m unittest must pass.
6. `git add content site/images` and `git commit -m "feat(content): $month_name posts"`.
   Do not push. Do not run `push.py --live`. Do not touch `state/`.

Finish with a short report: the files written, any claim you could not verify and so
avoided, and anything a human should look at.
