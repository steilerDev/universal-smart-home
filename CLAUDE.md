# universal-smart-home — Project Guide

## Project Overview

ESPHome-based smart home system. ~25 room sensor units (Olimex ESP32-POE2, PoE Ethernet) deployed across the house. Repository is the single source of truth for all device configurations.

## Repository Structure

```
devices/          — One YAML per physical device (substitutions + package includes)
packages/
  base/           — Board config, Ethernet, OTA, API, I2C bus
  sensors/        — motion, climate, illuminance, power-pzem004t
  actuators/      — status-led, dimmer, relay (via gpio extender), audio
  io/             — gpio-extender (PCF8574 — buttons + power circuits + blinds)
hardware/
  room-sensor/
    pcb/board-a/  — First PCB distribution board (design files go here)
    pcb/board-b/  — Second PCB distribution board
    case/         — Fusion 360 case files (.f3d stored as plain binary)
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
- **I2C bus:** SDA=GPIO03, SCL=GPIO04
- **Motion UART:** TX=GPIO02, RX=GPIO36 (DFRobot C4002 mmWave)
- **NeoPixel LED:** GPIO33 (WS2812, 1 LED per unit)
- **GPIO expander:** PCF8574 @ 0x20 (8 channels: 2 inputs = buttons, 6 outputs via cover/switch)
  - Channels 0,1 → Button 1, Button 2 (binary_sensor, INPUT)
  - Channels 2,3 → Power Circuit 1, 2 (switch, OUTPUT)
  - Channels 4,5 → Blind 1 open/close relays (internal switch → time_based cover)
  - Channels 6,7 → Blind 2 open/close relays (internal switch → time_based cover)
- **I2C sensors:** ENS160 @ 0x53, BH1750 @ 0x23, KRIDA dimmer @ 0x10
- **Audio:** ES8311 @ 0x18 + NS4150B amplifier (I2S media player for notifications/TTS; voice assistant stub commented out in audio.yaml)
- **Power monitor:** PZEM-004T (UART: ESP TX=GPIO1 → PZEM RX, ESP RX=GPIO39 ← PZEM TX; GPIO1 conflicts with UART0 logger — power package disables serial logger)
- **Schematic:** https://app.cirkitdesigner.com/project/281a6c22-06b7-4593-8d16-d8be4f0f2b7c (requires login — can't be fetched programmatically)

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

**Strapping pins — constraints at boot:**
- GPIO0: must be HIGH at boot (board handles this)
- GPIO2: must be LOW/floating at boot — use as output only, no external pull-up
- GPIO5: must be HIGH at boot
- GPIO12: must be LOW at boot (board handles this for 3.3V flash)

**Our PCB assignments and any known conflicts:**
| GPIO | Use | Notes |
|------|-----|-------|
| GPIO0  | Ethernet CLK_OUT | ✓ |
| GPIO1  | PZEM-004T UART TX | ⚠️ UART0 TX (logger serial). power-pzem004t.yaml sets baud_rate: 0 to release it |
| GPIO2  | Motion UART TX | ⚠️ strapping pin. Safe: TX only, not driven at boot, board has pull-down |
| GPIO3  | I2C SDA | ⚠️ nominally UART0 RX. Works: GPIO matrix lets I2C claim it; logger loses serial RX but TX (GPIO1) still works. Proven on device. |
| GPIO4  | I2C SCL | ✓ |
| GPIO12 | Ethernet PHY power | ✓ |
| GPIO18 | Ethernet MDIO | ✓ |
| GPIO23 | Ethernet MDC | ✓ |
| GPIO33 | NeoPixel LED | ✓ |
| GPIO36 | Motion UART RX | ✓ input-only |
| GPIO39 | PZEM-004T UART RX | ✓ input-only |

**Available for future sensors/actuators** (not used by board or our PCB):
GPIO5, GPIO13, GPIO14, GPIO15, GPIO19, GPIO20, GPIO21, GPIO22, GPIO25, GPIO26, GPIO27, GPIO32, GPIO34¹, GPIO35¹

¹ Input-only pins.

**Power budget:** 3.3V 500mA · 5V 1.5A · 12/24V 0.75/1.5A · 25W total

> Before assigning any GPIO to a new component, check it against this table first.

## ESPHome Build Environment

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

## Prototype Device

**File:** `devices/room-sensor-poe2.yaml`  
**IP:** `10.10.14.20`  
**ESPHome name:** `room-sensor-poe2` (must match for OTA continuity)  
**Capabilities:** base + climate + illuminance + gpio_extender
