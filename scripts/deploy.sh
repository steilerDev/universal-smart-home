#!/usr/bin/env bash
# Deploy (compile + OTA flash) a single device.
# Usage: ./scripts/deploy.sh <device-name> [--device <ip-or-hostname>]
# Example: ./scripts/deploy.sh living-room
#          ./scripts/deploy.sh living-room --device 10.10.14.20
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
DEVICE="${1:?Usage: deploy.sh <device-name> [--device <ip>]}"
shift
esphome run "$REPO/devices/$DEVICE.yaml" "$@"
