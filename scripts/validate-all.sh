#!/usr/bin/env bash
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
PASS=0
FAIL=0

echo "Validating all device configs in $REPO/devices/ ..."
for f in "$REPO"/devices/*.yaml; do
  name="$(basename "$f" .yaml)"
  if esphome config "$f" > /dev/null 2>&1; then
    echo "  OK   $name"
    PASS=$((PASS + 1))
  else
    echo "  FAIL $name"
    esphome config "$f" 2>&1 | tail -5
    FAIL=$((FAIL + 1))
  fi
done

echo ""
echo "Results: $PASS passed, $FAIL failed"
[[ $FAIL -eq 0 ]]
