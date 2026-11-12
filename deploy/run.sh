#!/usr/bin/env bash
# The Sunday job: pull, render missing images, schedule the next fortnight in Buffer,
# commit what changed, push. Every step is idempotent, so a re-run after a failure is
# safe: build.py skips existing PNGs and push.py skips slugs already in state/.
set -euo pipefail

# One run at a time with author.py, which commits to main too. A shared lock rather than
# systemd's Conflicts=, which SIGTERMed whichever unit was already running (a push killed
# after Buffer took the posts but before state/pushed.json was committed). The push waits
# out an author run; airep-social.service's start timeout covers the wait.
# flock -o keeps the lock in flock itself, so a git that daemonises a background gc
# never inherits it and holds it after this script ends.
LOCK="${AIREP_SOCIAL_LOCK:-$HOME/.local/state/airep-social/run.lock}"
if [ -z "${AIREP_SOCIAL_LOCKED:-}" ]; then
  mkdir -p "$(dirname "$LOCK")"
  AIREP_SOCIAL_LOCKED=1 exec flock -o "$LOCK" bash "$0" "$@"
fi

cd "$(dirname "$0")/.."

PY="${AIREP_SOCIAL_PYTHON:-python3}"

# Push main; when another push landed meanwhile (the swarm lane, a session), merge it and
# try again. A rejected push left the local commit diverged from origin, and every later
# Sunday then stopped at `git pull --ff-only` with nothing scheduled. A merge, not a
# rebase: this is the shared checkout, and a rebase refuses to run on a dirty tree.
push_main() {
  for _ in 1 2 3; do
    if git push -q origin main; then
      return 0
    fi
    git fetch -q origin main
    if ! git merge -q --no-edit origin/main; then
      git merge --abort || true
      return 1
    fi
  done
  return 1
}

# A pull that fails (local changes in the way, main diverged) stops the run before
# anything is scheduled. set -e ended it with only a journal line, which nobody reads on a
# Sunday, so the pages went quiet; say so on Telegram instead.
if ! pull_out=$(git pull --ff-only 2>&1); then
  printf '%s\n' "$pull_out" >&2
  "$PY" push.py --alert "⚠ AIREP social: nothing scheduled, git pull --ff-only failed:
$(printf '%s\n' "$pull_out" | tail -n 8)" || true
  exit 1
fi

# build.py renders every post, not only this fortnight's, so a film missing weeks ahead
# fails it. Push anyway: push.py HEAD-checks each post's asset and skips (and alerts on)
# one that is missing; the build's failure is re-raised at the end so it is still seen.
build_status=0
"$PY" build.py || build_status=$?
if ! git diff --quiet -- site/images || [ -n "$(git ls-files --others --exclude-standard site/images)" ]; then
  git add site/images
  git commit -q -m "chore(build): render images for the next fortnight"
  # Buffer HEAD-checks each asset at push time, so the images must be on Pages first.
  push_main
  sleep 90  # GitHub Pages usually rebuilds within a minute of a push
fi

# push.py exits 1 whenever the run had an alert (a HEAD miss, a page that needs
# reconnecting), but Buffer already holds every post it created, so the state file
# must be committed whatever the exit code; the code is re-raised at the end so the
# unit still shows as failed and the alert is seen.
status=0
"$PY" push.py --live || status=$?

if ! git diff --quiet -- state/pushed.json; then
  git add state/pushed.json
  git commit -q -m "chore(state): Buffer posts scheduled $(date +%F)"
  push_main
fi

if [ "$status" -eq 0 ]; then
  status=$build_status
fi
exit "$status"
