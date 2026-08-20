#!/usr/bin/env bash
# Scaffold a new room-sensor device YAML.
# Usage: ./scripts/new-device.sh <device-name>
# Example: ./scripts/new-device.sh bedroom-main
#
# The template is written inline rather than copied from an existing device, so
# this cannot rot the way it did when it copied a device file that was later
# removed.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
DEVICE="${1:?Usage: new-device.sh <device-name>}"
TARGET="$REPO/devices/$DEVICE.yaml"

if [[ -f "$TARGET" ]]; then
  echo "ERROR: $TARGET already exists." >&2
  exit 1
fi

# Title-case the hyphenated name for the friendly name: bedroom-main → "Bedroom Main"
FRIENDLY="$(echo "$DEVICE" | tr '-' ' ' | awk '{for(i=1;i<=NF;i++) $i=toupper(substr($i,1,1)) substr($i,2)}1')"

cat > "$TARGET" <<EOF
# ${FRIENDLY}
# Capabilities: base + climate (uncomment the packages this room needs)

substitutions:
  device_name: ${DEVICE}
  device_friendly_name: "${FRIENDLY}"
  device_ip: "CHANGE_ME"
  # GPIO pins are NOT listed here on purpose: every package defaults to the
  # RoomSensor MainPlate Rev 2/3 wiring (I2C SDA=GPIO13 SCL=GPIO33, radar
  # TX=GPIO4 RX=GPIO35, PZEM TX=GPIO3 RX=GPIO1, LED=GPIO32). Override a pin here
  # only for a Rev 1 board — see devices/room-sensor-poe2.yaml for that shape.
  #
  # Uncomment alongside the package that needs them:
  # room_width_m: "4.0"
  # room_depth_m: "5.0"
  # ceiling_height_m: "2.4"

# The base package already disables the serial logger (baud_rate: 0) — the PZEM
# UART owns GPIO1/GPIO3. Logs go over the native API.

packages:
  base:        !include ../packages/base/room-sensor.yaml
  climate:     !include ../packages/sensors/climate.yaml
  # illuminance: !include ../packages/sensors/illuminance.yaml
  # motion:      !include ../packages/sensors/motion.yaml
  # power:       !include ../packages/sensors/power-pzem004t.yaml
  # status_led:  !include ../packages/actuators/status-led.yaml
  # dimmer:      !include ../packages/actuators/dimmer.yaml
  # audio:       !include ../packages/actuators/audio.yaml   # Rev 1 boards only
  # gpio_ext:    !include ../packages/io/gpio-extender.yaml
EOF

echo "Created $TARGET"
echo "Next steps:"
echo "  1. Set device_ip (currently CHANGE_ME)"
echo "  2. Uncomment the packages this room needs, plus their substitutions"
echo "  3. Run: esphome config devices/$DEVICE.yaml"
