#!/usr/bin/env bash
# The Sunday job: pull, render missing images, schedule the next fortnight in Buffer,
# commit what changed, push. Every step is idempotent, so a re-run after a failure is
# safe: build.py skips existing PNGs and push.py skips slugs already in state/.
set -euo pipefail
cd "$(dirname "$0")/.."

PY="${AIREP_SOCIAL_PYTHON:-python3}"

git pull --ff-only

"$PY" build.py
if ! git diff --quiet -- site/images || [ -n "$(git ls-files --others --exclude-standard site/images)" ]; then
  git add site/images
  git commit -q -m "chore(build): render images for the next fortnight"
  # Buffer HEAD-checks each asset at push time, so the images must be on Pages first.
  git push origin main
  sleep 90  # GitHub Pages usually rebuilds within a minute of a push
fi

"$PY" push.py --live

if ! git diff --quiet -- state/pushed.json; then
  git add state/pushed.json
  git commit -q -m "chore(state): Buffer posts scheduled $(date +%F)"
  git push origin main
fi
