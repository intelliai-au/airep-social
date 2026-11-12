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

git pull --ff-only

# build.py renders every post, not only this fortnight's, so a film missing weeks ahead
# fails it. Push anyway: push.py HEAD-checks each post's asset and skips (and alerts on)
# one that is missing; the build's failure is re-raised at the end so it is still seen.
build_status=0
"$PY" build.py || build_status=$?
if ! git diff --quiet -- site/images || [ -n "$(git ls-files --others --exclude-standard site/images)" ]; then
  git add site/images
  git commit -q -m "chore(build): render images for the next fortnight"
  # Buffer HEAD-checks each asset at push time, so the images must be on Pages first.
  git push origin main
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
  git push origin main
fi

if [ "$status" -eq 0 ]; then
  status=$build_status
fi
exit "$status"
