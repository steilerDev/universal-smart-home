#!/usr/bin/env bash
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
PASS=0
FAIL=0

echo "Validating all device configs in $REPO/devices/ ..."
for f in "$REPO"/devices/*.yaml; do
  name="$(basename "$f" .yaml)"
  # devices/secrets.yaml is the committed symlink to ../secrets.yaml, not a device
  [[ "$name" == "secrets" ]] && continue
  if esphome config "$f" > /dev/null 2>&1; then
    echo "  OK   $name"
    PASS=$((PASS + 1))
  else
    echo "  FAIL $name"
    # `|| true`: esphome exits non-zero here by definition, and under
    # `set -e -o pipefail` that would abort the whole sweep after the first
    # failure instead of validating the remaining devices.
    esphome config "$f" 2>&1 | grep -iE "error|invalid|failed" | head -5 || true
    FAIL=$((FAIL + 1))
  fi
done

echo ""
echo "Results: $PASS passed, $FAIL failed"
[[ $FAIL -eq 0 ]]
