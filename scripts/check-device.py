#!/usr/bin/env python3
"""Post-deploy health check for ESPHome room sensor devices.

Connects via native API (port 6053, noise encryption), lists all entities,
collects states for a few seconds, and reports pass/fail per package.

Usage:
    ./scripts/check-device.py <device-name>
    ./scripts/check-device.py room-sensor-poe2
"""
from __future__ import annotations

import asyncio
import math
import sys
from pathlib import Path
from typing import Any

import yaml

try:
    from aioesphomeapi import (
        APIClient,
        BinarySensorInfo,
        BinarySensorState,
        CoverInfo,
        CoverState,
        LightInfo,
        LightState,
        MediaPlayerInfo,
        MediaPlayerEntityState,
        SensorInfo,
        SensorState,
        SwitchInfo,
        SwitchState,
        TextSensorInfo,
        TextSensorState,
    )
except ImportError:
    sys.exit("aioesphomeapi not installed — run: pip3 install aioesphomeapi")

REPO_ROOT = Path(__file__).resolve().parent.parent

# Map package path fragment → checks
# sensors: list of (suffix, min, max, unit)  — min/max=None to skip range check
# binary_sensors/switches/covers/lights: list of object_id suffixes to assert present
PACKAGE_CHECKS: dict[str, dict[str, Any]] = {
    "base/room-sensor": {
        "label": "base",
        "description": "Ethernet · OTA · API connectivity",
        "sensors": [],
        "binary_sensors": [],
        "switches": [],
        "covers": [],
        "lights": [],
    },
    "sensors/climate": {
        "label": "climate",
        "description": "ENS160 (eCO2/TVOC/AQI) + AHT20 (temp/humidity)",
        "sensors": [
            ("temperature",      -20,   60,    "°C"),
            ("humidity",           0,  100,    "%"),
            ("eco2",             400, 8000,    "ppm"),
            ("tvoc",               0, 65000,   "ppb"),
            ("air_quality_index",  0,    6,    "AQI"),
        ],
    },
    "sensors/illuminance": {
        "label": "illuminance",
        "description": "BH1750 ambient light",
        "sensors": [("illuminance", 0, 150000, "lx")],
    },
    "sensors/motion": {
        "label": "motion",
        "description": "DFRobot C4002 mmWave radar",
        "binary_sensors": ["presence"],
    },
    "sensors/power-pzem004t": {
        "label": "power_monitor",
        "description": "PZEM-004T power monitor",
        "sensors": [
            ("voltage", 0, 300,   "V"),
            ("current", 0, 100,   "A"),
            ("power",   0, 23000, "W"),
            ("energy",  0, None,  "kWh"),
        ],
    },
    "io/gpio-extender": {
        "label": "gpio_extender",
        "description": "PCF8574 I/O expander (buttons / relays / blinds)",
        "binary_sensors": ["button_1", "button_2"],
        "switches": ["power_circuit_1", "power_circuit_2"],
        "covers": ["blind_1", "blind_2"],
    },
    "actuators/status-led": {
        "label": "status_led",
        "description": "WS2812 NeoPixel status LED",
        "lights": ["status_led"],
    },
    "actuators/dimmer": {
        "label": "dimmer",
        "description": "KRIDA I2C AC dimmer",
        "lights": ["main_light"],
    },
    "actuators/audio": {
        "label": "audio",
        "description": "ES8311 I2S media player",
        "media_players": ["media_player"],
    },
}


# ── YAML helpers ─────────────────────────────────────────────────────────────

def _make_loader() -> type[yaml.SafeLoader]:
    """SafeLoader that ignores !include and !secret tags (returns raw string)."""
    loader = type("IgnoreLoader", (yaml.SafeLoader,), {})
    loader.add_constructor("!include", lambda l, n: l.construct_scalar(n))
    loader.add_constructor("!secret", lambda l, n: l.construct_scalar(n))
    return loader


def load_device(device_name: str) -> dict:
    path = REPO_ROOT / "devices" / f"{device_name}.yaml"
    if not path.exists():
        sys.exit(f"Device config not found: {path}")
    with open(path) as f:
        return yaml.load(f, Loader=_make_loader())


def load_secrets() -> dict:
    path = REPO_ROOT / "secrets.yaml"
    if not path.exists():
        sys.exit("secrets.yaml not found — create it from secrets.template.yaml")
    with open(path) as f:
        return yaml.safe_load(f)


# ── Entity helpers ────────────────────────────────────────────────────────────

def object_id_suffix(object_id: str, prefix: str) -> str:
    """Strip the device name prefix from an object_id."""
    if object_id.startswith(prefix):
        return object_id[len(prefix):]
    return object_id


# ── Checks ───────────────────────────────────────────────────────────────────

PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"
WARN = "\033[33mWARN\033[0m"
INFO = "\033[36mINFO\033[0m"


def check_sensor(
    suffix: str,
    lo: float | None,
    hi: float | None,
    unit: str,
    entities_by_suffix: dict[str, SensorInfo],
    states_by_key: dict[int, SensorState],
) -> tuple[bool, str]:
    info = entities_by_suffix.get(suffix)
    if info is None:
        return False, f"  [{FAIL}] {suffix}: entity not found on device"
    state = states_by_key.get(info.key)
    if state is None:
        return False, f"  [{WARN}] {suffix}: entity present but no state received"
    v = state.state
    if math.isnan(v):
        return False, f"  [{FAIL}] {suffix}: value is NaN (sensor not responding)"
    range_ok = (lo is None or v >= lo) and (hi is None or v <= hi)
    tag = PASS if range_ok else FAIL
    range_str = f"[{lo}, {hi}]" if lo is not None and hi is not None else ""
    msg = f"  [{tag}] {suffix}: {v:.2f} {unit}"
    if not range_ok:
        msg += f"  ← out of expected range {range_str}"
    return range_ok, msg


def check_binary(
    suffix: str,
    entities_by_suffix: dict[str, Any],
    states_by_key: dict[int, Any],
) -> tuple[bool, str]:
    info = entities_by_suffix.get(suffix)
    if info is None:
        return False, f"  [{FAIL}] {suffix}: entity not found"
    state = states_by_key.get(info.key)
    val = state.state if state else "?"
    return True, f"  [{PASS}] {suffix}: {'ON' if val is True else 'OFF' if val is False else val}"


def check_switch(suffix, entities_by_suffix, states_by_key):
    return check_binary(suffix, entities_by_suffix, states_by_key)


def check_cover(
    suffix: str,
    entities_by_suffix: dict[str, Any],
    states_by_key: dict[int, Any],
) -> tuple[bool, str]:
    info = entities_by_suffix.get(suffix)
    if info is None:
        return False, f"  [{FAIL}] {suffix}: entity not found"
    state = states_by_key.get(info.key)
    pos = f"{state.position * 100:.0f}%" if state else "?"
    return True, f"  [{PASS}] {suffix}: position {pos}"


def check_light(suffix, entities_by_suffix, states_by_key):
    info = entities_by_suffix.get(suffix)
    if info is None:
        return False, f"  [{FAIL}] {suffix}: entity not found"
    state = states_by_key.get(info.key)
    val = "ON" if (state and state.state) else "OFF"
    return True, f"  [{PASS}] {suffix}: {val}"


# ── Main ──────────────────────────────────────────────────────────────────────

async def run(device_name: str) -> int:
    device_cfg = load_device(device_name)
    secrets = load_secrets()

    subs = device_cfg.get("substitutions", {})
    host = subs.get("device_ip")
    friendly = subs.get("device_friendly_name", device_name)

    if not host:
        sys.exit("Could not find device_ip substitution in device YAML")

    noise_psk = secrets.get("home_assistant_encryption")
    if not noise_psk:
        sys.exit("home_assistant_encryption not found in secrets.yaml")

    # Derive the object_id prefix: "Room Sensor POE2" → "room_sensor_poe2_"
    prefix = friendly.lower().replace(" ", "_").replace("-", "_") + "_"

    # Determine which packages are active on this device
    packages_raw = device_cfg.get("packages", {})
    active_packages: list[str] = []
    for pkg_path in packages_raw.values():
        # pkg_path is like "../packages/sensors/climate.yaml"
        for key in PACKAGE_CHECKS:
            if key in str(pkg_path):
                active_packages.append(key)
                break

    print(f"\n{'─' * 60}")
    print(f"  ESPHome device check: {device_name}  ({host})")
    print(f"  Friendly name prefix: {prefix}")
    print(f"  Active packages: {[PACKAGE_CHECKS[p]['label'] for p in active_packages]}")
    print(f"{'─' * 60}")

    client = APIClient(host, 6053, None, noise_psk=noise_psk)

    try:
        await client.connect(login=True)
    except Exception as e:
        print(f"\n[{FAIL}] Could not connect to {host}:6053 — {e}")
        return 1

    device_info = await client.device_info()
    print(f"\n  [{INFO}] Connected: {device_info.name}  ESPHome {device_info.esphome_version}")
    print(f"  [{INFO}] MAC: {device_info.mac_address}  Model: {device_info.model or 'unknown'}")

    entities, _ = await client.list_entities_services()

    # Index by type and object_id suffix
    sensors:        dict[str, SensorInfo]      = {}
    binary_sensors: dict[str, BinarySensorInfo] = {}
    switches:       dict[str, SwitchInfo]      = {}
    covers:         dict[str, CoverInfo]        = {}
    lights:         dict[str, LightInfo]        = {}
    media_players:  dict[str, MediaPlayerInfo]  = {}

    for e in entities:
        sfx = object_id_suffix(e.object_id, prefix)
        if isinstance(e, SensorInfo):
            sensors[sfx] = e
        elif isinstance(e, BinarySensorInfo):
            binary_sensors[sfx] = e
        elif isinstance(e, SwitchInfo):
            switches[sfx] = e
        elif isinstance(e, CoverInfo):
            covers[sfx] = e
        elif isinstance(e, LightInfo):
            lights[sfx] = e
        elif isinstance(e, MediaPlayerInfo):
            media_players[sfx] = e

    # Collect states for a few seconds
    states_by_key: dict[int, Any] = {}
    state_event = asyncio.Event()
    expected_count = len(entities)
    received: set[int] = set()

    def on_state(state):
        states_by_key[state.key] = state
        received.add(state.key)
        if len(received) >= expected_count:
            state_event.set()

    client.subscribe_states(on_state)
    try:
        await asyncio.wait_for(state_event.wait(), timeout=5.0)
    except asyncio.TimeoutError:
        pass  # use whatever states arrived

    print(f"\n  [{INFO}] Entities: {len(entities)} found, {len(states_by_key)} states received\n")

    # ── Base connectivity (always checked) ──────────────────────────────────
    print(f"[{PASS}] base — Ethernet/OTA/API connectivity")
    print(f"  [{PASS}] native API: connected  ESPHome {device_info.esphome_version}")

    total_pass = total_fail = 0

    for pkg_key in active_packages:
        if pkg_key == "base/room-sensor":
            total_pass += 1
            continue

        spec = PACKAGE_CHECKS[pkg_key]
        label = spec["label"]
        desc = spec["description"]
        pkg_pass = pkg_fail = 0
        lines = []

        for suffix, lo, hi, unit in spec.get("sensors", []):
            ok, msg = check_sensor(suffix, lo, hi, unit, sensors, states_by_key)
            lines.append(msg)
            if ok: pkg_pass += 1
            else:   pkg_fail += 1

        for suffix in spec.get("binary_sensors", []):
            ok, msg = check_binary(suffix, binary_sensors, states_by_key)
            lines.append(msg)
            if ok: pkg_pass += 1
            else:   pkg_fail += 1

        for suffix in spec.get("switches", []):
            ok, msg = check_switch(suffix, switches, states_by_key)
            lines.append(msg)
            if ok: pkg_pass += 1
            else:   pkg_fail += 1

        for suffix in spec.get("covers", []):
            ok, msg = check_cover(suffix, covers, states_by_key)
            lines.append(msg)
            if ok: pkg_pass += 1
            else:   pkg_fail += 1

        for suffix in spec.get("lights", []):
            ok, msg = check_light(suffix, lights, states_by_key)
            lines.append(msg)
            if ok: pkg_pass += 1
            else:   pkg_fail += 1

        pkg_ok = pkg_fail == 0
        total_pass += pkg_pass
        total_fail += pkg_fail
        tag = PASS if pkg_ok else FAIL
        print(f"[{tag}] {label} — {desc}  ({pkg_pass}/{pkg_pass+pkg_fail} checks)")
        for l in lines:
            print(l)

    # ── Entities not matched to any package ─────────────────────────────────
    matched_suffixes: set[str] = set()
    for pkg_key in active_packages:
        spec = PACKAGE_CHECKS.get(pkg_key, {})
        for sfx, *_ in spec.get("sensors", []):
            matched_suffixes.add(sfx)
        for sfx in spec.get("binary_sensors", []):
            matched_suffixes.add(sfx)
        for sfx in spec.get("switches", []):
            matched_suffixes.add(sfx)
        for sfx in spec.get("covers", []):
            matched_suffixes.add(sfx)
        for sfx in spec.get("lights", []):
            matched_suffixes.add(sfx)

    all_suffixes = (
        list(sensors) + list(binary_sensors) + list(switches) +
        list(covers) + list(lights) + list(media_players)
    )
    extra = [s for s in all_suffixes if s not in matched_suffixes]
    if extra:
        print(f"\n[{INFO}] Extra entities (not mapped to a package check):")
        for s in extra:
            print(f"  {s}")

    print(f"\n{'─' * 60}")
    overall = PASS if total_fail == 0 else FAIL
    print(f"  Result: [{overall}]  {total_pass} passed, {total_fail} failed")
    print(f"{'─' * 60}\n")

    await client.disconnect()
    return 0 if total_fail == 0 else 1


def main() -> None:
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <device-name>")
        print(f"       {sys.argv[0]} room-sensor-poe2")
        sys.exit(1)
    sys.exit(asyncio.run(run(sys.argv[1])))


if __name__ == "__main__":
    main()
