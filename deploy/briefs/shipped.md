# Refresh this month's "shipped" post: $file

You are a headless Claude Code run inside a git worktree of `airep-social`. Nobody will
answer a question. This post was written two months early as a provisional changelog;
$prev_month is over now, so rewrite it to cover that month and nothing else.

- Source: `git -C ../../airep/airep log --since=$since --until=$until --no-merges
  --format="%ad %s" --date=short`, with `git -C ../../airep/airep show --stat <sha>` where
  a subject is unclear. User-facing changes only: something a customer sees or uses. No
  refactors, CI, tests, dependency bumps or internal tooling.
- Three items, dated, one plain-English line each. Verify each one in the airep code
  before writing it. Never repeat an item from an earlier shipped post (`grep -l shipped
  content/*.yaml` and read them). If $prev_month has fewer than three honest items, use
  fewer; never pad.
- Keep the file's `date`, `slot`, `template` and `image` path. Update the kicker to
  "Shipped · $prev_month", the headline, the sub-line, the items and both captions.
- Render with $python build.py --force --only $slug and open the PNG with the Read
  tool; shorten anything that clips.
- `ruff check .` and $python -m unittest must pass. Then `git add content site/images`
  and `git commit -m "feat(content): refresh $slug"`. Do not push. Edit nothing else.

Report in two lines: the three items and anything a human should check.
