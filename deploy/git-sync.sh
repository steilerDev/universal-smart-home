#!/bin/sh
# Poll-only git sync for the ESPHome Device Builder config directory.
#
# Keeps the builder's checkout at origin/<ref> so it always compiles exactly
# what is on the branch. There is deliberately NO network endpoint here —
# nothing to expose, authenticate, or route through Authentik. The deploy agent
# pushes to git; this loop pulls it in; the agent then triggers the build over
# the builder's /ws API.
#
# Only `reset --hard` runs (tracked files only), so untracked builder state
# (.device-builder*.json job history/labels) and the host-provisioned,
# gitignored secrets.yaml are left untouched.
set -eu

REPO="${GIT_SYNC_REPO:-/repo}"
REF="${GIT_SYNC_REF:-main}"
INTERVAL="${GIT_SYNC_INTERVAL:-15}"

echo "git-sync: repo=$REPO ref=$REF interval=${INTERVAL}s"
# The repo is bind-mounted from the host and may be owned by another uid.
git config --global --add safe.directory "$REPO" || true

while true; do
  if git -C "$REPO" fetch --quiet origin "$REF" 2>/dev/null; then
    local_head="$(git -C "$REPO" rev-parse HEAD 2>/dev/null || echo none)"
    remote_head="$(git -C "$REPO" rev-parse "origin/$REF" 2>/dev/null || echo none)"
    if [ "$local_head" != "$remote_head" ]; then
      echo "git-sync: $local_head -> $remote_head"
      git -C "$REPO" reset --hard "origin/$REF" --quiet
    fi
  else
    echo "git-sync: fetch failed (will retry in ${INTERVAL}s)"
  fi
  sleep "$INTERVAL"
done
