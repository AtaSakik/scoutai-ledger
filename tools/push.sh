#!/usr/bin/env bash
# Push the commit this run just made to main.
#
# The three workflows that write (ledger, upkeep, open-data) share the
# concurrency group "ledger-writes", so they never run at the same time. That
# was not enough on its own: actions/checkout fetches the commit main pointed at
# when the run was QUEUED. On 2026-11-27 the 15:07 ledger run waited behind a
# late upkeep run, started after upkeep had pushed, built on the older main, and
# its push was rejected, so that hour's snapshot was never published. Each
# workflow now checks out `ref: main` (the tip when the job starts); this is the
# second line: if main still moved, rebase this run's commit onto it and push
# again. The runs write different files (a new hour's snapshot, upgraded proofs
# of past hours, data/), so the rebase does not conflict; if it ever does, stop
# loudly rather than guess.
set -euo pipefail

for attempt in 1 2 3 4; do
  if git push origin HEAD:main; then
    exit 0
  fi
  echo "push rejected (attempt $attempt): rebasing onto the newer main"
  git fetch origin main
  if ! git rebase origin/main; then
    git rebase --abort || true
    echo "::error::could not rebase onto origin/main: both sides changed the same file"
    exit 1
  fi
  sleep $((attempt * 3))
done
echo "::error::push still rejected after 4 attempts"
exit 1
