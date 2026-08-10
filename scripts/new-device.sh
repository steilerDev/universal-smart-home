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
  i2c_sda_pin: "GPIO04"
  i2c_scl_pin: "GPIO03"
  # Uncomment alongside the package that needs them:
  # led_pin: "GPIO33"
  # led_num_leds: "1"
  # pzem_uart_tx_pin: "GPIO15"
  # pzem_uart_rx_pin: "GPIO33"
  # pzem_address: "0x01"
  # room_width_m: "4.0"
  # room_depth_m: "5.0"
  # ceiling_height_m: "2.4"

# UART0 RX is GPIO3, which every unit uses as I2C SCL — enabling the serial
# logger would claim that pin and take the whole I2C bus down. Logs go over the API.
logger:
  baud_rate: 0

packages:
  base:        !include ../packages/base/room-sensor.yaml
  climate:     !include ../packages/sensors/climate.yaml
  # illuminance: !include ../packages/sensors/illuminance.yaml
  # motion:      !include ../packages/sensors/motion.yaml
  # power:       !include ../packages/sensors/power-pzem004t.yaml
  # status_led:  !include ../packages/actuators/status-led.yaml
  # dimmer:      !include ../packages/actuators/dimmer.yaml
  # audio:       !include ../packages/actuators/audio.yaml
  # gpio_ext:    !include ../packages/io/gpio-extender.yaml
EOF

echo "Created $TARGET"
echo "Next steps:"
echo "  1. Set device_ip (currently CHANGE_ME)"
echo "  2. Uncomment the packages this room needs, plus their substitutions"
echo "  3. Run: esphome config devices/$DEVICE.yaml"
