# universal-smart-home — Project Guide

## Project Overview

ESPHome-based smart home system. ~25 room sensor units (Olimex ESP32-POE2, PoE Ethernet) deployed across the house, plus a few special-purpose nodes on the same board (e-ink dashboard, utility/metering sensor). Repository is the single source of truth for all device configurations.

## Repository Structure

```
devices/          — One YAML per physical device (substitutions + package includes)
packages/
  base/           — room-sensor (arduino + I2C) / utility-sensor (esp-idf, no I2C)
  sensors/        — motion, climate, illuminance, power-pzem004t,
                    water-flow, well-level, energy-sdm
  actuators/      — status-led, dimmer, relay (via gpio extender), audio
  io/             — gpio-extender (PCF8574 — buttons + power circuits + blinds)
  displays/       — trmnl (e-ink dashboard BYOS client)
hardware/
  pcb/
    RoomSensor-BackPlate/  — Back plate PCB (PCF8574 expander, connectors)
    RoomSensor-MainPlate/  — Main plate PCB (Olimex socket, screw terminals)
    bom-lcsc.csv           — Combined BOM for LCSC ordering
  case/         — Fusion 360 case files (.f3d stored as plain binary),
                  one directory per device (room-sensor/, utility-sensor/)
  room-sensor.kicad_sym   — Custom KiCad symbol library
  room-sensor.pretty/     — Custom KiCad footprint library
scripts/
  validate-all.sh — Validate all device configs
  deploy.sh       — OTA deploy a single device
  new-device.sh   — Scaffold new device from minimal template
secrets.template.yaml  — Committed template
secrets.yaml           — GITIGNORED — create from template, fill in values
devices/secrets.yaml   — Symlink to ../secrets.yaml (committed, allows ESPHome to find secrets)
```

## Hardware — Room Sensor

- **Board:** Olimex ESP32-POE2 (`board: esp32dev`, framework: arduino)
- **Ethernet:** LAN8720, MDC=GPIO23, MDIO=GPIO18, CLK_OUT=GPIO0, power=GPIO12

> **Rev 2/3 is the only live wiring.** MainPlate/BackPlate **Rev 2/3** is what
> every package defaults to and what the prototype at 10.10.14.20 actually runs —
> no device YAML overrides pins any more. The earlier Rev 1 / hand-wired pinout is
> retained below purely as history; that hardware is gone. The BackPlate expander
> wiring is identical across both revisions.

| Function | Rev 2/3 (package default) | Rev 1 (superseded, no live hardware) |
|----------|---------------------------|--------------------------------------|
| I2C SDA | GPIO13 | GPIO04 |
| I2C SCL | GPIO33 | GPIO03 |
| Motion UART — ESP TX → radar RX | GPIO4 | GPIO02 |
| Motion UART — ESP RX ← radar TX | GPIO35 | GPIO36 |
| PZEM UART — ESP TX → PZEM RX | GPIO3 | GPIO33 |
| PZEM UART — ESP RX ← PZEM TX | GPIO1 | GPIO39 |
| Status LED data (DOut) | GPIO32 | GPIO32 |
| PCF8574 INT | GPIO36 | — (not routed) |
| Audio (ES8311) | **not populated** | GPIO1/5/13/14/15 |

- **Status LED:** WS2811/WS2812 via `esp32_rmt_led_strip` (the deprecated
  `neopixelbus` platform was replaced). MainPlate terminal C1 is
  `+5V / DIn / DOut / GND`: the ESP drives **DOut**, while **DIn** is the chain
  return that continues to the BackPlate LED-Bus header (EX1). More than one LED
  can therefore hang off a unit — set `led_num_leds` to match the wiring.
- **GPIO expander:** PCF8574 @ 0x20 (8 channels), INT → GPIO36 on Rev 2/3.
  Three 2-channel relay modules plus a button terminal:
  - Channels 0,1 → relay module R3 → Power Circuit 1, 2 (switch, OUTPUT)
  - Channels 2,3 → relay module R2 → Blind 1 open/close (internal → time_based cover)
  - Channels 4,5 → relay module R1 → Blind 2 open/close (internal → time_based cover)
  - Channels 6,7 → Button 1, Button 2 (binary_sensor, INPUT) on terminal EX3
  - ⚠️ **Channel 5 is double-landed** — it feeds both relay R1's second channel and
    EX3's *third* button terminal. Use one or the other. The firmware spends it on
    Blind 2, so only two buttons are exposed.
  - ESPHome's `pcf8574` platform has no interrupt support, so buttons are polled
    and GPIO36 sits idle — but the trace is populated, so don't reassign it.
- **I2C sensors:** ENS160 @ 0x53, BH1750 @ 0x23, KRIDA dimmer @ 0x10 (BackPlate L1)
- **Audio:** ES8311 @ 0x18 + NS4150B amplifier — **Rev 1 only**, and never populated.
  Rev 2/3 dropped the section entirely and reused two of its pins (GPIO13 → I2C SDA,
  GPIO1 → PZEM RX), so `packages/actuators/audio.yaml` deliberately has no defaults.
  Rev 1 pinout, for reference: BCK=GPIO5, LRCK=GPIO13, DOUT=GPIO14, DIN=GPIO15, MCLK=GPIO1
  (`use_mclk: true`; GPIO1 is one of the 3 valid CLK_OUT pins — GPIO0/1/3 — and
  requires `logger: baud_rate: 0`).
- **Power monitor:** PZEM-004T on the BackPlate "Energy" header (E1), reaching the
  ESP over the board-to-board connector.
  ⚠️ On Rev 2/3 this UART sits on **GPIO1/GPIO3 — UART0's own console pins**, with
  their roles swapped versus native UART0. Any device including the power package
  MUST also set `logger: baud_rate: 0`. ESPHome does **not** catch this: it happily
  assigns the logger `hardware_uart: UART0` and the config validates, but both
  peripherals then drive the same pads and the meter never answers.
- **Schematic:** https://app.cirkitdesigner.com/project/281a6c22-06b7-4593-8d16-d8be4f0f2b7c (requires login — can't be fetched programmatically)

## Hardware — Utility Sensor

Basement metering node (`devices/utility-sensor.yaml`, 10.10.14.10). Same Olimex
ESP32-POE2, **no custom PCB** — field wiring lands on screw terminals — but it does
have a custom case (`hardware/case/utility-sensor/`).

- **Framework:** `esp-idf` (not arduino) — 8 simultaneous `pulse_counter` channels
  ride the ESP32 PCNT peripheral. Uses `packages/base/utility-sensor.yaml`, which
  omits the I2C bus because GPIO03/GPIO04 are taken by other functions here.
- **No `friendly_name`.** The device predates this repo and its HA entities are
  unprefixed (`sensor.water_flow_eg_kalt`). Adding `friendly_name` would re-slug
  every entity_id and orphan history — don't. Same reason the `"Waserstand Brunnen"`
  typo stays.
- **Water meters:** 8 × YF-B series hall-effect pulse sensors.
- **Well level:** QDY30A submersible transmitter, Modbus RTU holding register 0x0004.
- **Grid power:** Eastron SDM three-phase meter — package exists
  (`sensors/energy-sdm.yaml`) but is **not enabled**; the RS485 leg is unpopulated.

| GPIO | Use | Notes |
|------|-----|-------|
| GPIO02 | Flow — OG Heizung | ⚠️ strapping (must be LOW at boot); input, meter passive at boot |
| GPIO03 | Well Modbus TX | nominally UART0 RX — costs the serial console's RX half only |
| GPIO04 | Flow — EG Kalt | ✓ |
| GPIO05 | Flow — Brunnen | ⚠️ strapping (must be HIGH at boot) |
| GPIO13 | Flow — OG Warm | ✓ |
| GPIO14 | Flow — Anbau Heizung | ✓ |
| GPIO15 | Flow — EG Heizung | ⚠️ strapping |
| GPIO33 | Flow — OG Kalt | terminal silkscreened "16"; actually wired to GPIO33 |
| GPIO35 | Well Modbus RX | ✓ input-only |
| GPIO36 | Flow — EG Warm | ✓ input-only |
| GPIO01 | (reserved) SDM Modbus TX | UART0 TX — enabling energy-sdm requires `logger: baud_rate: 0` |
| GPIO39 | (reserved) SDM Modbus RX | ✓ input-only |

> Do NOT add pull-ups to the GPIO02/05/15 meter inputs — they are strapping pins and
> the current wiring only works because the meters are passive at boot.

**Calibration model** — everything is build-time (change the YAML, re-flash). No
calibration lives in device flash, so a device is fully described by this repo.
- Water meters — `flow_pulses_per_liter` per include, one per line. Datasheets give
  `F = K * Q` (Hz vs L/min) → pulses/L = `K * 60`; YF-B K=6.6 → 396.

  The `Water Volume - <line>` totals use `restore: true`, whose stored value is keyed
  off the sensor's object_id — so it **survives OTA**. After recalibrating a line,
  deploy and then press its `Water Volume Reset - <line>` button
  (`sensor.integration.reset`), or the total keeps the volume accumulated under the
  old pulses/L. There is no other way to clear it short of erasing flash.
- Well level — `well_sensor_depth_cm` and `well_pump_depth_cm`, both measured
  downward from the well head. Published value is the column above the pump intake:
  `raw + (pump_depth - sensor_depth)`. Negative is meaningful (water below the
  intake) and deliberately not clamped.

  **This install: probe 1500, intake 1600 → offset +100 cm.** The probe hangs ABOVE
  the intake, and a submersible transmitter cannot report a surface below itself, so
  every level in the last 100 cm above the intake reads 100 cm. The published value
  is a floor in that band, not a measurement. `binary_sensor.well_probe_uncovered`
  (`device_class: problem`) is ON exactly when that is the case — use it to gate any
  dry-run automation instead of trusting the 100 cm reading.

**HA energy dashboard (water):** a water source must carry `device_class: water` AND
`state_class: total_increasing`. Unit alone (`L`) is not enough — that was why the
volume sensors never showed up in the picker.

## ESP32-POE2 GPIO Constraints

Source: [Olimex ESP32-POE2 user manual](https://github.com/OLIMEX/ESP32-POE2/blob/main/DOCUMENTS/ESP32-POE2-user-manual.pdf)
Module: ESP32-WROVER-E (has PSRAM)

**NEVER USE — hard-reserved by board hardware:**
| GPIO | Reserved for |
|------|-------------|
| GPIO16, GPIO17 | PSRAM (WROVER internal) |
| GPIO0  | Ethernet LAN8720 CLK_OUT |
| GPIO12 | Ethernet PHY power enable |
| GPIO18 | Ethernet MDIO |
| GPIO23 | Ethernet MDC |
| GPIO19, GPIO21, GPIO22 | Ethernet RMII TXD0 / TX_EN / TXD1 |
| GPIO25, GPIO26, GPIO27 | Ethernet RMII RXD0 / RXD1 / CRS_DV |

The six RMII pins are fixed in ESP-IDF's EMAC driver and cannot be remapped.
`esphome config` rejects any other use of them whenever `ethernet:` is present.

**Strapping pins — constraints at boot:**
- GPIO0: must be HIGH at boot (board handles this)
- GPIO2: must be LOW/floating at boot — use as output only, no external pull-up
- GPIO5: must be HIGH at boot
- GPIO12: must be LOW at boot (board handles this for 3.3V flash)

**MainPlate Rev 2/3 assignments — the package defaults:**
| GPIO | Use | Notes |
|------|-----|-------|
| GPIO0  | Ethernet CLK_OUT | ✓ |
| GPIO1  | PZEM-004T UART RX (← PZEM TX) | ⚠️ UART0 TX pin, used here as RX. Forces `logger: baud_rate: 0` when the power package is on |
| GPIO2  | (free) expansion header J2 | ⚠️ strapping pin, 2.2k on board |
| GPIO3  | PZEM-004T UART TX (→ PZEM RX) | ⚠️ UART0 RX pin, used here as TX. Same logger caveat |
| GPIO4  | Motion UART TX (→ radar RX) | ✓ |
| GPIO5  | (free) expansion header J2 | ⚠️ strapping pin, HIGH at boot; 10k on board |
| GPIO12 | Ethernet PHY power | ✓ |
| GPIO13 | I2C SDA | ✓ |
| GPIO14 | (free) expansion header J2 | ✓ |
| GPIO15 | (free) expansion header J2 | ⚠️ strapping pin; 10k on board |
| GPIO18 | Ethernet MDIO | ✓ |
| GPIO23 | Ethernet MDC | ✓ |
| GPIO32 | Status LED data out (WS2811/WS2812, esp32_rmt_led_strip) | ✓ terminal C1 "DOut" |
| GPIO33 | I2C SCL | ✓ |
| GPIO34 | (free) expansion header J2 — silkscreened "10k/BUT" | ✓ input-only |
| GPIO35 | Motion UART RX (← radar TX) | ✓ input-only |
| GPIO36 | PCF8574 INT | ✓ input-only; routed but unusable — ESPHome polls the expander |
| GPIO39 | (free) expansion header J2 — silkscreened "PWR_Sense" | ✓ input-only |

**Rev 1 assignments** (superseded, no board still wired this way — kept only so
old photos, notes and the schematic history stay readable):
GPIO1 audio MCLK · GPIO2 motion TX · GPIO3 I2C SCL · GPIO4 I2C SDA ·
GPIO5 I2S BCK · GPIO13 I2S LRCLK · GPIO14 I2S DOUT · GPIO15 I2S DIN ·
GPIO32 status LED · GPIO33 PZEM TX · GPIO36 motion RX · GPIO39 PZEM RX

**ESP32 MCLK constraint:** Hardware CLK_OUT is limited to GPIO0/1/3 only. On Rev 1
that left only GPIO1 for audio MCLK (GPIO0 = Ethernet, GPIO3 = I2C SCL). Rev 2/3
spends GPIO1 and GPIO3 on the PZEM UART, so **no CLK_OUT pin remains** — another
reason audio cannot come back on this revision without a board change.

**Available for future sensors/actuators on Rev 2/3:** GPIO2, GPIO5, GPIO14,
GPIO15, GPIO34¹, GPIO39¹ — all six brought out on expansion header J2. Plus
GPIO13 and GPIO33 on any device that omits I2C entirely (the e-ink dashboard
reuses those for its e-paper SPI bus and parks the unused I2C bus on GPIO04/GPIO03).

¹ Input-only pins.

> GPIO19/21/22/25/26/27 were previously listed here as free. They are **not** — see
> the RMII rows in the hard-reserved table above. GPIO20 does not exist on the
> ESP32-WROVER.

**Power budget:** 3.3V 500mA · 5V 1.5A · 12/24V 0.75/1.5A · 25W total

> Before assigning any GPIO to a new component, check it against this table first.

## Deploy via Device Builder (default path)

Firmware is built and OTA-flashed by a **self-hosted ESPHome Device Builder** on the
primary Docker host, **not** by compiling in this sandbox. This repo is bind-mounted
into both the agent's environment and the builder container, so edits to
`devices/*.yaml` are visible to the builder **instantly** — no git-sync, no push
required to flash. The agent reaches the builder on the internal Docker network
(`ws://esphome:6052/ws`, no auth); Authentik only gates the browser UI at
`https://esphome.<domain>`. Use the `deploy-device` skill, or run directly:

```bash
esphome config devices/<name>.yaml     # 1. validate locally (cheap, no compile)
./scripts/builder-deploy.py <name>     # 2. compile + OTA on the builder, streamed
./scripts/check-device.py <name>       # 3. health-check
git add -A && git commit -m "…" && git push origin main   # 4. persist (durability, not needed to flash)
```

- Endpoint + deploy details: `deploy/README.md`.
- Set `ESPHOME_BUILDER_URL=ws://esphome:6052/ws`, or pass `--server` to the script.
- `scripts/builder-deploy.py` speaks the builder's single `/ws` endpoint. A deploy is
  **two jobs**: `firmware/install` only *compiles* on this builder version, and the
  OTA is a separate `firmware/upload` job — calling install alone reports success
  while the device keeps its old firmware. `--all` deploys every device;
  `--compile-only` skips the OTA.
- `firmware/upload` failing with `[Errno 113] No route to host` on port 3232 means
  **nothing answers at that IP** — check `device_ip` before blaming the network. This
  bit us once: the utility sensor was documented at 10.10.14.11 but actually lives at
  10.10.14.10, and the misleading error looked like a container routing problem.
  Both this environment and the builder can reach 10.10.14.0/24 fine.

The local-compile path below is the deeper **fallback** for when the builder is
unavailable; it requires the PlatformIO/SSL workarounds in "Known Build Issues & Fixes".

## ESPHome Build Environment (local fallback)

### Installation

```bash
pip3 install esphome --break-system-packages
```

### Running ESPHome

Always run from the repo root:

```bash
esphome config devices/<name>.yaml       # validate
esphome compile devices/<name>.yaml      # compile firmware
esphome run devices/<name>.yaml          # compile + OTA flash (tails logs forever — see deploy pattern below)
```

### Deploy pattern (background + monitor)

`esphome run` blocks indefinitely after flashing (it tails device logs). Always deploy in background and monitor for completion:

1. Run deploy with `run_in_background: true` (Bash tool parameter).
2. Set up a Monitor on the output file:
   ```bash
   tail -f <output-file> | grep --line-buffered -E "SUCCESS|successfully|OTA|upload|error|Error|FAILED|WARNING|hash"
   ```
3. Wait for all three confirmations: `SUCCESS` (build) → `OTA successful` → `Successfully uploaded`.
4. After success, kill the deploy process with `pkill -f "esphome (run|logs).*<device-name>"`. **TaskStop only removes task tracking — it does NOT kill the OS process.** Each zombie `esphome run` holds a native API connection slot; ESPHome allows max 5 connections. Leaving them running fills all slots and blocks HA from reconnecting.


### Post-deploy log check (required)

After every OTA deploy, pull the device logs and verify no components are marked FAILED:

```bash
timeout 15 esphome logs devices/<name>.yaml --device <ip> 2>&1 | grep -E "FAILED|dfrobot|C4002|begin|error"
```

Key patterns to check:
- `[E][component:224]: <component> is marked FAILED` — component crashed during setup
- For C4002 specifically: `dump_config` will show `FAILED: no bytes received` (power/wiring) or `FAILED: N bytes received but frame invalid` (baud mismatch)
- OTA rollback: `[W][safe_mode:094]: OTA rollback detected!` — new firmware crashed, old firmware restored

### Secrets resolution

ESPHome resolves `!secret` relative to the config file's directory. The repo keeps `secrets.yaml` at root (gitignored). `devices/secrets.yaml` is a committed symlink → `../secrets.yaml` so ESPHome finds secrets when running against `devices/*.yaml`.

### API encryption format

The correct format for `packages/base/room-sensor.yaml` is:
```yaml
api:
  encryption:
    key: !secret home_assistant_encryption
```
(Not `encryption: !secret ...` — that's invalid in ESPHome 2026.x)

## Known Build Issues & Fixes

### 1. PlatformIO SSL verification failure

PlatformIO's own HTTP session fails SSL verification against the sandbox proxy. Fix:

```bash
# Disable proxy strict SSL (one-time, persists in ~/.platformio/appstate.json)
pio settings set enable_proxy_strict_ssl No

# Also set CA bundle env vars when running esphome:
REQUESTS_CA_BUNDLE=/home/agent/.local/lib/python3.14/site-packages/certifi/cacert.pem \
SSL_CERT_FILE=/home/agent/.local/lib/python3.14/site-packages/certifi/cacert.pem \
esphome compile devices/room-sensor-poe2.yaml
```

### 2. PlatformIO Python deps fail: "pioarduino-core" vs "platformio"

The pioarduino fork installs its PlatformIO replacement as `pioarduino-core`, but `penv_setup.py` checks for `platformio`. On the second `configure_default_packages` call (triggered by the dual arduino+espidf framework), `get_packages_to_install` yields `platformio` again, and `uv pip install --upgrade` then conflicts with the editable esptool already installed by `_install_esptool_from_tl_install` (exit code 2).

**Fix applied** to `~/.platformio/platforms/espressif32/builder/penv_setup.py`:

In `get_packages_to_install()` — treat `pioarduino-core` as satisfying the `platformio` requirement:
```python
effective_name = "pioarduino-core" if name == "platformio" and "pioarduino-core" in installed_packages else name
if effective_name not in installed_packages:
    yield package
elif name == "platformio":
    ...
    installed_ver = installed_packages.get(effective_name)
```

In `install_python_deps()` — pass `UV_SYSTEM_CERTS=1` so uv uses the OS cert store (includes sandbox proxy CA) instead of its bundled certs. Without this, uv fails with `invalid peer certificate: UnknownIssuer` when fetching from GitHub through the proxy:
```python
if uv_cache_dir:
    uv_env = dict(os.environ)
    uv_env["UV_CACHE_DIR"] = str(uv_cache_dir)
    uv_env["UV_SYSTEM_CERTS"] = "1"
```

**After any edit to `penv_setup.py`, delete the .pyc cache before compiling:**
```bash
rm -f ~/.platformio/platforms/espressif32/builder/__pycache__/penv_setup.cpython-314.pyc
```

**Note:** These fixes live in the PlatformIO platform cache (`~/.platformio/`), not in the repo. They must be re-applied if the platform package is reinstalled/updated.

### 3. Framework download (first run only)

The first compile downloads ~1GB of toolchains (arduino-esp32, esp-idf, xtensa toolchain). These cache in `~/.platformio/packages/` and are not re-downloaded.

### 4. Network access requirements

All of the following domains must be allowed in the sandbox network policy. Run on the host machine:

```bash
# GitHub — framework + toolchain downloads (pioarduino releases all come from here)
sbx policy allow network --sandbox <name> "**.github.com"
sbx policy allow network --sandbox <name> "**.githubusercontent.com"

# PlatformIO registry — tool packages (scons, cmake, ninja, etc.)
sbx policy allow network --sandbox <name> "**.platformio.org"

# Python packages
sbx policy allow network --sandbox <name> "pypi.org"
sbx policy allow network --sandbox <name> "files.pythonhosted.org"

# Espressif IDF component registry — fetched during CMake configuration
sbx policy allow network --sandbox <name> "**.espressif.com"
```

Or allow all at once with wildcards (simplest for a dev sandbox):
```bash
sbx policy allow network --sandbox <name> "**.github.com"
sbx policy allow network --sandbox <name> "**.githubusercontent.com"
sbx policy allow network --sandbox <name> "**.platformio.org"
sbx policy allow network --sandbox <name> "pypi.org"
sbx policy allow network --sandbox <name> "files.pythonhosted.org"
sbx policy allow network --sandbox <name> "**.espressif.com"
```

### 5. OTA deployment — device network access

The device at `10.10.14.20` is on the local home network. The sandbox may not reach it directly. If OTA upload fails:
- Check: `sbx policy allow network 10.10.14.20` on host
- Or run `./scripts/deploy.sh room-sensor-poe2` from the host machine directly

## Post-Deploy Health Check

`scripts/check-device.py` connects to a device via the native API and validates all entities from its active packages.

```bash
./scripts/check-device.py <device-name>
./scripts/check-device.py room-sensor-poe2
```

**What it checks (per package):**
- `base` — native API reachable, ESPHome version confirmed
- `climate` — temperature, humidity, eCO2, TVOC, AQI present + in plausible ranges
- `illuminance` — illuminance sensor present + non-NaN
- `gpio_extender` — buttons, power circuits, blind covers all report state
- `motion`, `status_led`, `dimmer`, `audio`, `power_monitor` — pre-wired for future devices

**Requirements:**
- `aioesphomeapi` (already installed: `pip3 install aioesphomeapi`)
- `secrets.yaml` must have `home_assistant_encryption` as a flat base64 string
- Device must be reachable on port 6053 from the sandbox (allow `10.10.14.20` in network policy if needed)

**Entity name notes:**
- Object IDs are derived from `device_friendly_name`: "Room Sensor POE2" → prefix `room_sensor_poe2_`
- ENS160 eCO2 entity slugifies as `eco2` (not `e_co2`)

## Adding a New Device

```bash
./scripts/new-device.sh <room-name>
# Edit devices/<room-name>.yaml:
#   - Set device_name, device_friendly_name, device_ip
#   - Add packages for the capabilities this room needs
esphome config devices/<room-name>.yaml   # validate before deploying
```

## Deployed Devices

| File | IP | ESPHome name | Capabilities |
|------|----|--------------|--------------|
| `devices/room-sensor-poe2.yaml` (prototype, MainPlate Rev 2/3) | 10.10.14.20 | `room-sensor-poe2` | base, climate, illuminance, motion, status_led — BackPlate not connected, so power/gpio_ext/dimmer are off |
| `devices/eink-dashboard.yaml` | 10.10.14.25 | `eink-dashboard` | base, trmnl |
| `devices/utility-sensor.yaml` | 10.10.14.10 | `utility-sensor` | base, well_level, 8 × water_flow |

ESPHome names must not change — OTA continuity and HA entity IDs both key off them.

## PCB Manufacturing & Parts Sourcing

### Workflow

- **PCB manufacturing:** AISLER (aisler.net) — bare board, no assembly
- **Parts:** LCSC (lcsc.com) — all components ordered separately and hand-soldered

### KiCad Schematic Metadata

- **`MPN`** (Manufacturer Part Number) — the only custom field used. Required by AISLER; cross-reference against LCSC table below for ordering.
- **`LCSC`** — not present in schematic. Use LCSC# column below to build cart on lcsc.com.

**BOM export from KiCad:** Use the Symbol Fields Table — accessible via the spreadsheet icon in the schematic editor toolbar (KiCad 10). There is no menu path. Export as CSV.

### Chosen Components — RoomSensor-MainPlate

| Ref | Function | MPN (in schematic) | LCSC# | Stock | Price |
|-----|----------|--------------------|-------|-------|-------|
| S1, S2 | 1×5 female socket 8.5mm | C50950 | C50950 | 147k | $0.08 |
| S3 | 1×8 female socket 8.5mm | C27438 | C27438 | 214k | $0.11 |
| A1 | 1×10 female socket 8.5mm | PM254-1-10-Z-8.5 | C2897373 | 29k | $0.19 |
| E1 | 2×13 dual female socket 8.5mm | C64320 | C64320 | 3.5k | $0.22 |
| C1, C2 | 4-pin screw terminal 2.54mm | KF128-2.54-4P | C474922 | 3.9k | $0.47 |
| C3 | 7-pin screw terminal 2.54mm | KF128-2.54-7P | C474925 | 340 ⚠️ | $0.78 |
| C4 | XH 6-pin PCB header 2.5mm | ZX-XH2.54-6PZZ | C7429636 | 95k | $0.03 |
| C5 | XH 4-pin PCB header 2.5mm | ZX-XH2.54-4PZZ | C7429634 | 650k | $0.01 |
| J1 | IDC 2×5 box header 2.54mm (PCB side) | MTB10-10S | C358743 | 47k | $0.08 |

Note: C4/C5 are not yet placed in the schematic — MPNs listed for when they are added.

### Chosen Components — RoomSensor-BackPlate

| Ref | Function | MPN (in schematic) | LCSC# | Stock | Price |
|-----|----------|--------------------|-------|-------|-------|
| R1–R3, L1, E1 | 1×4 tall female socket 11mm | HX PM2.54-1x4P ZC H11 | C41427519 | 3.8k | $0.21 |
| EX1–EX3 | 4-pin screw terminal 2.54mm | KF128-2.54-4P | C474922 | 3.9k | $0.47 |
| C1 | IDC 2×5 box header 2.54mm (PCB side) | MTB10-10S | C358743 | 47k | $0.08 |
| U1 | PCF8574 DIP-16 GPIO expander | PCF8574P | C398073 | 351 | $0.77 |
| SW1, SW2 | Voltage selector | *(solder pads — no part)* | — | — | — |

**Notes:**
- KF128 (C474922/C474925) uses the same `TerminalBlock_Phoenix:TerminalBlock_Phoenix_MPT-0,5-x-2.54` KiCad footprint family as Phoenix MPT — direct drop-in.
- PCF8574**P** = DIP-16, I2C address 0x20. Do NOT use PCF8574**AP** (C398072) — that's address 0x38, firmware-incompatible.
- XH connectors (C4/C5) are 2.5mm pitch, not 2.54mm — use JST_XH KiCad footprints.
