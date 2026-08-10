# universal-smart-home

ESPHome firmware for the house: ~25 room sensor units plus a handful of special-purpose
nodes. Every device is an [Olimex ESP32-POE2](https://www.olimex.com/Products/IoT/ESP32/ESP32-POE2/open-source-hardware)
on PoE Ethernet — no WiFi, no cloud dependency. All devices integrate with Home
Assistant via the native ESPHome API. This repo is the single source of truth for
every device configuration.

---

## Hardware — Room Sensor

> [Schematic](https://app.cirkitdesigner.com/project/281a6c22-06b7-4593-8d16-d8be4f0f2b7c)

| Component | Part |
|-----------|------|
| MCU | [Olimex ESP32-POE2](https://www.olimex.com/Products/IoT/ESP32/ESP32-POE2/open-source-hardware) (ESP32-WROVER-E, PoE Ethernet) |
| Climate | [ENS160](https://esphome.io/components/sensor/ens160/) + [AHT21](https://esphome.io/components/sensor/aht10/) — eCO2, TVOC, AQI, temp, humidity |
| Illuminance | [BH1750](https://esphome.io/components/sensor/bh1750/) |
| Presence | [DFRobot C4002](https://www.dfrobot.com/product-3081.html) mmWave radar (custom component) |
| Dimmer | [KRIDA I2C AC dimmer](https://www.tindie.com/products/bugrovs2012/i2c-mosfet-trailing-edge-ac-dimmer-light) trailing-edge MOSFET (custom component) |
| GPIO Expander | [PCF8574](https://esphome.io/components/pcf8574/) — 2 buttons, 2 power circuits, 2 roller blinds |
| Status LED | WS2811/WS2812 via [esp32_rmt_led_strip](https://esphome.io/components/light/esp32_rmt_led_strip/) |
| Audio | [ES8311](https://esphome.io/components/audio_dac/es8311/) + NS4150B (notifications / TTS) |
| Power | [PZEM-004T](https://esphome.io/components/sensor/pzemac/) AC energy monitor |

PCB design files live in `hardware/pcb/`, the enclosure in `hardware/case/room-sensor/`.

---

## Hardware — Utility Sensor

The basement metering node. Same Olimex board, **no custom PCB** — the field wiring
lands on screw terminals — but it does have its own case (`hardware/case/utility-sensor/`).

| Component | Part |
|-----------|------|
| MCU | Olimex ESP32-POE2, running the `esp-idf` framework (8 × PCNT pulse counters) |
| Water flow | 8 × YF-B series hall-effect meters, one per supply line |
| Well level | QDY30A submersible level transmitter (Modbus RTU over RS485) |
| Grid power | Eastron SDM three-phase meter (Modbus RTU) — wired for, **not yet populated** |

Schematic (WIP): https://app.cirkitdesigner.com/project/46fdfdfb-f6f8-4aec-ac91-cfc2bc7dc07d

### Metered lines

| Line | GPIO | Line | GPIO |
|------|------|------|------|
| EG Kalt | GPIO04 | EG Warm | GPIO36 |
| OG Kalt | GPIO33 | OG Warm | GPIO13 |
| EG Heizung | GPIO15 | OG Heizung | GPIO02 |
| Anbau Heizung | GPIO14 | Brunnen | GPIO05 |

### Calibration

Both are build-time values in `devices/utility-sensor.yaml` — change and re-flash.

- **Water meters** — `flow_pulses_per_liter` per line. Meter datasheets quote
  `F = K * Q` (F in Hz, Q in L/min), so pulses/L is `K * 60`; the YF-B's K = 6.6 gives
  396. Each line carries its own value, so lines with a different meter model just get
  a different number.

  After changing a line's calibration, **re-flash and then press its
  `Water Volume Reset - <line>` button in HA**. The running total is stored in flash
  keyed by entity, so it survives the OTA and would otherwise keep the volume that
  was accumulated with the old pulses/L.
- **Well level** — the probe measures the water column above *itself*. The published
  value is the column above the **pump intake**:
  `raw + (well_pump_depth_cm - well_sensor_depth_cm)`. The offset is +100 cm in this
  install (probe at 15 m, intake at 16 m); it would be negative if the probe hung
  below the intake. Negative readings mean the water is below the intake and are not
  clamped away.

  ⚠️ Because the probe sits **above** the intake it cannot see a surface below itself,
  so the last 100 cm above the intake all read 100 cm — a floor, not a level. The
  `Well Probe Uncovered` binary sensor (`device_class: problem`) is ON exactly then, so
  automations can treat that reading as "≤100 cm, unknown" rather than trusting it.
  Hanging the probe below the intake would remove the blind spot.

### Home Assistant water dashboard

The `Water Volume - <line>` sensors carry `device_class: water` +
`state_class: total_increasing`, which is what HA's water dashboard filters on. A unit
of `L` alone is not enough — the entity simply never appears in the picker without
both of those.

---

## Repository Layout

```
devices/          — One YAML per physical device (substitutions + package includes)
packages/
  base/           — Board, Ethernet, OTA, HA API (room-sensor / utility-sensor variants)
  sensors/        — climate, illuminance, motion, power-pzem004t, water-flow,
                    well-level, energy-sdm
  actuators/      — status-led, dimmer, audio
  io/             — gpio-extender (PCF8574 — buttons, power circuits, blinds)
  displays/       — trmnl (e-ink dashboard)
components/       — Local custom ESPHome components (dfrobot_c4002, krida_dimmer, trmnl)
hardware/
  pcb/            — KiCad projects, symbol/footprint libs, LCSC BOM
  case/           — Fusion 360 enclosures, one directory per device
deploy/           — Device Builder deployment notes
scripts/          — validate-all, builder-deploy, deploy, new-device, check-device
sounds/           — WAV assets for the audio package
secrets.template.yaml
```

---

## Deployed Devices

| Device | IP | Packages |
|--------|----|---------|
| `room-sensor-poe2` (prototype) | 10.10.14.20 | base, power, climate, motion, status\_led |
| `eink-dashboard` | 10.10.14.25 | base, trmnl |
| `utility-sensor` | 10.10.14.11 | base, well\_level, 8 × water\_flow |

---

## Quick Start

Firmware is compiled and OTA-flashed by the self-hosted **ESPHome Device Builder**,
not by compiling locally — see [`deploy/README.md`](deploy/README.md).

```bash
cp secrets.template.yaml secrets.yaml  # fill in OTA password + HA encryption key

esphome config devices/<name>.yaml     # 1. validate (cheap, no compile)
./scripts/builder-deploy.py <name>     # 2. compile + OTA on the builder
./scripts/check-device.py <name>       # 3. post-deploy health check
```

Add a new device:

```bash
./scripts/new-device.sh <room-name>
```

Local compilation (`pip3 install esphome --break-system-packages`, then
`esphome run devices/<name>.yaml`) still works as a fallback; see `CLAUDE.md` for the
PlatformIO workarounds it needs.

---

## Packages

Each device YAML picks only the packages it needs. Every device requires exactly one
`base` package; the rest are optional.

| Package | Provides |
|---------|----------|
| `base/room-sensor` | Board (arduino), Ethernet PoE, OTA, HA API, I2C bus |
| `base/utility-sensor` | Board (esp-idf), Ethernet PoE, OTA, HA API — no I2C |
| `sensors/climate` | [ENS160](https://esphome.io/components/sensor/ens160/) + [AHT20](https://esphome.io/components/sensor/aht10/) — air quality, temp, humidity |
| `sensors/illuminance` | [BH1750](https://esphome.io/components/sensor/bh1750/) light level |
| `sensors/motion` | [DFRobot C4002](https://www.dfrobot.com/product-3081.html) presence + target tracking |
| `sensors/power-pzem004t` | [PZEM-004T](https://esphome.io/components/sensor/pzemac/) AC voltage/current/power/energy |
| `sensors/water-flow` | Pulse water meter for one supply line — include once per line with `vars` |
| `sensors/well-level` | QDY30A submersible level transmitter over Modbus |
| `sensors/energy-sdm` | Eastron SDM three-phase grid meter over Modbus |
| `actuators/dimmer` | [KRIDA I2C AC dimmer](https://www.tindie.com/products/bugrovs2012/i2c-mosfet-trailing-edge-ac-dimmer-light) (light entity) |
| `actuators/status-led` | WS2811/WS2812 status LED via [esp32_rmt_led_strip](https://esphome.io/components/light/esp32_rmt_led_strip/) |
| `actuators/audio` | [ES8311](https://esphome.io/components/audio_dac/es8311/) I2S media player |
| `io/gpio-extender` | [PCF8574](https://esphome.io/components/pcf8574/) — buttons, switches, blind covers |
| `displays/trmnl` | TRMNL BYOS e-ink dashboard client (custom component) |

`sensors/water-flow` is the one package meant to be included several times per device.
Use the mapping form of `!include` to pass it per-instance variables:

```yaml
packages:
  flow_eg_kalt: !include
    file: ../packages/sensors/water-flow.yaml
    vars:
      flow_key: eg_kalt
      flow_name: "EG Kalt"
      flow_pin: "GPIO04"
      flow_pulses_per_liter: "396"
```
