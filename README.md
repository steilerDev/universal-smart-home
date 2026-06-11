# universal-smart-home

ESPHome firmware for ~25 room sensor units deployed across the house. Each unit is an [Olimex ESP32-POE2](https://www.olimex.com/Products/IoT/ESP32/ESP32-POE2/open-source-hardware) on PoE Ethernet — no WiFi, no cloud dependency. All devices integrate with Home Assistant via the native ESPHome API.

---

## Hardware — Room Sensor

> Full details: [Hardware — Room Sensor](https://notes.steiler.de/doc/hardware-room-sensor-f93N9HhTLD) · [Schematic](https://app.cirkitdesigner.com/project/281a6c22-06b7-4593-8d16-d8be4f0f2b7c) · [BOM spreadsheet](https://docs.google.com/spreadsheets/d/1IDwVHU_nB87WG1chJAw_y0TpFDG4_Gb6cJKhXvnkDOo/edit?usp=sharing)

| Component | Part |
|-----------|------|
| MCU | Olimex ESP32-POE2 (ESP32-WROVER-E, PoE Ethernet) |
| Climate | ENS160 + AHT21 — eCO2, TVOC, AQI, temp, humidity |
| Illuminance | BH1750 |
| Presence | DFRobot C4002 mmWave radar |
| Dimmer | KRIDA I2C AC trailing-edge MOSFET dimmer |
| GPIO Expander | PCF8574 — 2 buttons, 2 power circuits, 2 roller blinds |
| Status LED | WS2812 NeoPixel |
| Audio | ES8311 + NS4150B (notifications / TTS) |
| Power Monitor | PZEM-004T AC energy meter |

PCB case design files are in `hardware/room-sensor/`.

---

## Repository Layout

```
devices/          — One YAML per physical device (substitutions + package includes)
packages/
  base/           — Board, Ethernet, OTA, HA API, I2C bus
  sensors/        — climate, illuminance, motion, power-pzem004t
  actuators/      — status-led, dimmer, audio
  io/             — gpio-extender (PCF8574 — buttons, power circuits, blinds)
components/       — Local custom ESPHome components (dfrobot_c4002, krida_dimmer)
hardware/
  room-sensor/
    pcb/          — PCB design files (board-a, board-b)
    case/         — Fusion 360 case files
scripts/          — validate-all, deploy, new-device, check-device
secrets.template.yaml
```

---

## Deployed Devices

| Device | IP | Packages |
|--------|----|---------|
| `room-sensor-poe2` (prototype) | 10.10.14.20 | base, climate, illuminance, gpio\_extender, dimmer, motion |
| `hallway-ground` | 10.10.14.30 | base, motion, status\_led |
| `living-room` | _TBD_ | _TBD_ |
| _(more rooms coming)_ | | |

---

## Quick Start

> Full guide: [Development Guide](https://notes.steiler.de/doc/development-guide-VQrIlahCvb)

```bash
pip3 install esphome --break-system-packages
cp secrets.template.yaml secrets.yaml  # fill in OTA password + HA encryption key

esphome config devices/<name>.yaml     # validate
esphome run devices/<name>.yaml        # compile + OTA flash
./scripts/check-device.py <name>       # post-deploy health check
```

Add a new device:

```bash
./scripts/new-device.sh <room-name>
```

---

## Packages

> Full reference: [Packages Reference](https://notes.steiler.de/doc/packages-reference-xvuuEMVoV6)

Each device YAML picks only the packages it needs. Every device requires `base`; the rest are optional.

| Package | Provides |
|---------|----------|
| `base/room-sensor` | Board, Ethernet PoE, OTA, HA API, I2C bus |
| `sensors/climate` | ENS160 + AHT20 — air quality, temp, humidity |
| `sensors/illuminance` | BH1750 light level |
| `sensors/motion` | DFRobot C4002 presence + target tracking |
| `sensors/power-pzem004t` | PZEM-004T AC power monitoring |
| `actuators/dimmer` | KRIDA I2C AC dimmer (light entity) |
| `actuators/status-led` | WS2812 NeoPixel |
| `actuators/audio` | ES8311 I2S media player |
| `io/gpio-extender` | PCF8574 — buttons, switches, blind covers |

---

## Utility Sensor _(planned)_

A separate ESP32 unit for whole-house metering over RS-485:

- **Water flow** — YF-B series hall-effect sensors at each supply line
- **Well level** — QDY30A submersible sensor (Modbus)
- **Grid power** — Eastron SDM72D-M (Modbus / [ESPHome SDM](https://esphome.io/components/sensor/sdm_meter/))

Schematic (WIP): https://app.cirkitdesigner.com/project/46fdfdfb-f6f8-4aec-ac91-cfc2bc7dc07d
