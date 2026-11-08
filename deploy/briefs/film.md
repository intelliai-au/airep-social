# Film the two $month_name videos

You are a headless Claude Code run inside a git worktree of `airep-social`, unsandboxed
because the rig talks to a local Django server. Nobody will answer a question. Films for
$month_name per `docs/YEAR.md`: $films.

The rig lives in the airep repo: `../../airep/airep/tools/filming/social/` (read its
README.md, and `../../airep/airep/tools/filming/README.md` for the demo tenant). The
durable build directory on this box is `~/Videos/airep-social/_build/` (env.sh, serve.sh,
reset.sh, baseline.dump, takes/). Read both READMEs fully before running anything.

Before you start, make sure nobody else is filming:
`ps -eo pid,args | grep -E 'social/(film|cut)\.py|reset\.sh' | grep -v grep` must print
nothing. If it does not, stop and report.

For each film:

1. Add its shot list to `films.py` in the airep repo, copying the structure of an
   existing film: frame with `region()` / `view()`, every caption describes the frame it
   sits under, APP_SIZE chosen for legibility (the README explains the arithmetic).
   Commit it to airep main as `feat(filming): social film <name>` once `ruff check .`
   and `ruff format --check .` pass there. `rig.py` is exempt and must never be
   formatted or edited.
2. Reset the tenant (`reset.sh`), film, cut (`cut.py` writes silent and scored
   versions), then `faststart.py` on each mp4 ONE FILE PER CALL. Watch the result:
   extract a few frames (`mpv --frames=1 --start=<s> --o=<png>`), read them, and
   re-shoot if text is clipped or the cursor is off its target. Two attempts per film.
3. Copy the scored mp4 to `site/video/airep_<name>_music.mp4` in this worktree.
4. Convert the first and third Tuesday `feature` posts of $month_name
   (`content/$month-*-feature-*.yaml`) into video posts, like
   `content/2026-11-17-feature-reorder-film.yaml`: `video: video/<file>`,
   `thumbnail_offset_ms` just after the trimmed lead-in, both captions kept (reworded
   to the film if needed); remove `image`, `template`, `fields` and `alt`, and delete the
   PNG that post no longer uses from `site/images/`.
5. `ruff check .`, $python -m unittest, then `git add site/video content site/images`
   and `git commit -m "feat(film): $month_name films"`. Do not push. Do not run
   `push.py --live`. Do not touch `state/`.

If a film cannot be made cleanly in two attempts, leave that Tuesday as an image post
and say why. Report: the films made (length and size), the airep commit, and anything a
human should look at.
