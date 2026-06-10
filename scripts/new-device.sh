#!/usr/bin/env bash
# Scaffold a new device YAML from the minimal hallway template.
# Usage: ./scripts/new-device.sh <device-name>
# Example: ./scripts/new-device.sh bedroom-main
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
DEVICE="${1:?Usage: new-device.sh <device-name>}"
TARGET="$REPO/devices/$DEVICE.yaml"

if [[ -f "$TARGET" ]]; then
  echo "ERROR: $TARGET already exists." >&2
  exit 1
fi

cp "$REPO/devices/hallway-ground.yaml" "$TARGET"
# Replace the placeholder name/IP so the file is ready to edit
sed -i "s/device_name: hallway-ground/device_name: $DEVICE/" "$TARGET"
sed -i "s/device_friendly_name: \"Hallway Ground\"/device_friendly_name: \"$DEVICE\"/" "$TARGET"
sed -i "s/device_ip: \"10.10.14.30\"/device_ip: \"CHANGE_ME\"/" "$TARGET"

echo "Created $TARGET"
echo "Next steps:"
echo "  1. Set device_ip and device_friendly_name"
echo "  2. Add packages for the capabilities this room needs"
echo "  3. Run: esphome config devices/$DEVICE.yaml"
