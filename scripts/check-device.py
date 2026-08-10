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
import re
import sys
from pathlib import Path
from typing import Any

import yaml

try:
    from aioesphomeapi import (
        APIClient,
        BinarySensorInfo,
        BinarySensorState,
        ButtonInfo,
        CoverInfo,
        CoverState,
        LightInfo,
        LightState,
        MediaPlayerInfo,
        MediaPlayerEntityState,
        NumberInfo,
        NumberState,
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
# binary_sensors/switches/covers/lights/numbers: object_id suffixes to assert present
#
# A package included several times with different `vars` (see water-flow) sets
# "per_instance": True. Its suffixes are then `str.format`-templates expanded once
# per include against that include's vars, e.g. "water_flow_{flow_key}".
BASE_PACKAGES = ("base/room-sensor", "base/utility-sensor")

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
    "base/utility-sensor": {
        "label": "base",
        "description": "Ethernet · OTA · API connectivity (esp-idf, no I2C)",
        "sensors": [],
    },
    "sensors/climate": {
        "label": "climate",
        "description": "ENS160 (air quality) + AHT20 (temp/humidity)",
        "sensors": [
            ("temperature",      -20,   60,    "°C"),
            ("humidity",           0,  100,    "%"),
        ],
        # The ENS160 eco2/tvoc/aqi sensors are `internal: true` in the package,
        # so they are never published over the native API. The derived
        # "Air Quality" text sensor is the observable proof the ENS160 is alive:
        # its lambda returns empty unless the AQI sensor has a valid state.
        #
        # Empty is tolerated: the ENS160 reports invalid during its warm-up after
        # every reset, so a check run right after an OTA legitimately sees "".
        # It reads e.g. 'Excellent' once the sensor settles.
        "text_sensors": ["air_quality"],
        "tolerate_empty_text": True,
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
        "text_sensors": ["radar_gates", "radar_log"],
        "switches": ["radar_calibrate"],
    },
    "sensors/power-pzem004t": {
        "label": "power_monitor",
        "description": "PZEM-004T power monitor",
        # The PZEM is mains-powered: with no high voltage connected it cannot
        # answer at all, so NaN is the expected reading rather than a fault.
        # Flip to False once mains is wired to assert on real measurements.
        "tolerate_nan": True,
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
    "sensors/well-level": {
        "label": "well_level",
        "description": "QDY30A submersible level transmitter (Modbus)",
        # Published value is water above the pump intake, so negative is a valid
        # (if alarming) reading. NaN means the Modbus master got no answer.
        "sensors": [("waserstand_brunnen", -2000, 2000, "cm")],
        # ON is not a failure here — it means the probe is no longer submerged
        # and the level reading has bottomed out at its floor.
        "binary_sensors": ["well_probe_uncovered"],
    },
    "sensors/water-flow": {
        "label": "water_flow_{flow_key}",
        "description": "Pulse water meter — {flow_name}",
        "per_instance": True,
        "sensors": [
            ("water_flow_{flow_key}",   0, 500,  "L/min"),
            ("water_volume_{flow_key}", 0, None, "L"),
        ],
        "buttons": ["water_volume_reset_{flow_key}"],
    },
    "sensors/energy-sdm": {
        "label": "energy_meter",
        "description": "Eastron SDM three-phase grid meter (Modbus)",
        "tolerate_nan": True,
        "sensors": [
            ("grid_voltage_phase_1",      0, 300,   "V"),
            ("grid_current_phase_1",      0, 200,   "A"),
            ("grid_power_total",     -50000, 50000, "W"),
            ("grid_import_active_energy", 0, None,  "kWh"),
        ],
    },
}


def resolve_spec(spec: dict[str, Any], pkg_vars: dict[str, str]) -> dict[str, Any]:
    """Expand a per-instance spec's suffix templates against one include's vars."""
    if not spec.get("per_instance"):
        return spec
    out = dict(spec)
    out["label"] = spec["label"].format(**pkg_vars)
    out["description"] = spec["description"].format(**pkg_vars)
    out["sensors"] = [
        (sfx.format(**pkg_vars), lo, hi, unit)
        for sfx, lo, hi, unit in spec.get("sensors", [])
    ]
    for key in ("binary_sensors", "switches", "covers", "lights", "text_sensors",
                "numbers", "buttons"):
        if key in spec:
            out[key] = [sfx.format(**pkg_vars) for sfx in spec[key]]
    return out


def active_package_specs(packages_raw: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """(package key, resolved spec) for every include that has checks defined.

    Handles both include forms: a bare "../packages/x.yaml" string, and the
    `!include {file:, vars:}` mapping used to instantiate a package more than
    once. Packages without per-instance vars are reported once even if the
    device happens to include them twice.
    """
    resolved: list[tuple[str, dict[str, Any]]] = []
    seen_singletons: set[str] = set()
    for include in packages_raw.values():
        if isinstance(include, dict):
            path, pkg_vars = str(include.get("file", "")), include.get("vars", {}) or {}
        else:
            path, pkg_vars = str(include), {}
        for key, spec in PACKAGE_CHECKS.items():
            if key not in path:
                continue
            if not spec.get("per_instance"):
                if key in seen_singletons:
                    break
                seen_singletons.add(key)
            resolved.append((key, resolve_spec(spec, pkg_vars)))
            break
    return resolved


# ── YAML helpers ─────────────────────────────────────────────────────────────

def _make_loader() -> type[yaml.SafeLoader]:
    """SafeLoader that ignores !include and !secret tags (returns the raw node).

    `!include` has two forms: a scalar path, and the mapping form
    `!include {file: ..., vars: {...}}` used to instantiate a package more than
    once — so it has to construct whichever node it is handed.
    """
    def include(loader: yaml.SafeLoader, node: yaml.Node) -> Any:
        if isinstance(node, yaml.MappingNode):
            return loader.construct_mapping(node, deep=True)
        return loader.construct_scalar(node)

    loader = type("IgnoreLoader", (yaml.SafeLoader,), {})
    loader.add_constructor("!include", include)
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

def normalize_object_id(value: str) -> str:
    """Collapse an ESPHome object_id to the form HA slugifies it into.

    ESPHome builds object_ids with `sanitize(snake_case(name))`, which lowercases
    and spaces→underscores but keeps dashes verbatim: "Water Flow - EG Kalt"
    becomes "water_flow_-_eg_kalt". HA slugifies the same name to
    "water_flow_eg_kalt". Normalizing here lets the checks be written the way the
    entity actually appears in Home Assistant.
    """
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def object_id_suffix(object_id: str, prefix: str) -> str:
    """Strip the device name prefix from an object_id (both normalized)."""
    oid = normalize_object_id(object_id)
    pfx = normalize_object_id(prefix)
    if pfx and oid.startswith(pfx + "_"):
        return oid[len(pfx) + 1:]
    return oid


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
    tolerate_nan: bool = False,
) -> tuple[bool, str]:
    info = entities_by_suffix.get(suffix)
    if info is None:
        return False, f"  [{FAIL}] {suffix}: entity not found on device"
    state = states_by_key.get(info.key)
    if state is None:
        return False, f"  [{WARN}] {suffix}: entity present but no state received"
    v = state.state
    if not isinstance(v, (int, float)):
        return False, f"  [{FAIL}] {suffix}: unexpected state type {type(v).__name__} — possible entity name collision"
    if math.isnan(v):
        if tolerate_nan:
            return True, f"  [{WARN}] {suffix}: NaN — expected, hardware not connected"
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


def check_text_sensor(
    suffix: str,
    entities_by_suffix: dict[str, Any],
    states_by_key: dict[int, Any],
    tolerate_empty: bool = False,
) -> tuple[bool, str]:
    """Assert a text sensor exists, and (unless tolerated) carries a value.

    The templated text sensors in this repo return {} when their backing sensor
    has no state, so "" means the source has not produced a reading yet. For
    sensors with a warm-up period that is expected rather than a fault — see
    tolerate_empty.
    """
    info = entities_by_suffix.get(suffix)
    if info is None:
        return False, f"  [{FAIL}] {suffix}: entity not found on device"
    state = states_by_key.get(info.key)
    if state is None:
        return False, f"  [{WARN}] {suffix}: entity present but no state received"
    val = state.state
    if not val:
        if tolerate_empty:
            return True, f"  [{WARN}] {suffix}: empty — sensor still warming up"
        return False, f"  [{FAIL}] {suffix}: empty — backing sensor has no state"
    return True, f"  [{PASS}] {suffix}: {val!r}"


def check_number(
    suffix: str,
    entities_by_suffix: dict[str, Any],
    states_by_key: dict[int, Any],
) -> tuple[bool, str]:
    """Assert a config `number` exists and carries a restored/initial value.

    These are calibration inputs (pulses per litre, temperature offset): a NaN
    here means the sensor reading derived from it is meaningless, so unlike a
    plain sensor it is never tolerated.
    """
    info = entities_by_suffix.get(suffix)
    if info is None:
        return False, f"  [{FAIL}] {suffix}: entity not found"
    state = states_by_key.get(info.key)
    if state is None:
        return False, f"  [{WARN}] {suffix}: entity present but no state received"
    if math.isnan(state.state):
        return False, f"  [{FAIL}] {suffix}: NaN — no value restored"
    unit = getattr(info, "unit_of_measurement", "") or ""
    return True, f"  [{PASS}] {suffix}: {state.state:g} {unit}".rstrip()


def check_button(
    suffix: str,
    entities_by_suffix: dict[str, Any],
    states_by_key: dict[int, Any],
) -> tuple[bool, str]:
    """Assert a button exists. Buttons are stateless — presence is all there is."""
    if suffix not in entities_by_suffix:
        return False, f"  [{FAIL}] {suffix}: entity not found"
    return True, f"  [{PASS}] {suffix}: present"


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
    friendly = subs.get("device_friendly_name")

    if not host:
        sys.exit("Could not find device_ip substitution in device YAML")

    noise_psk = secrets.get("home_assistant_encryption")
    if not noise_psk:
        sys.exit("home_assistant_encryption not found in secrets.yaml")

    # Derive the object_id prefix: "Room Sensor POE2" → "room_sensor_poe2_".
    # A device without device_friendly_name (utility-sensor) does not set
    # ESPHome's friendly_name, so its object_ids are not device-prefixed at all.
    prefix = friendly.lower().replace(" ", "_").replace("-", "_") + "_" if friendly else ""

    # Determine which packages are active on this device
    active_packages = active_package_specs(device_cfg.get("packages", {}))

    print(f"\n{'─' * 60}")
    print(f"  ESPHome device check: {device_name}  ({host})")
    print(f"  Friendly name prefix: {prefix or '(none — entities are unprefixed)'}")
    print(f"  Active packages: {[spec['label'] for _, spec in active_packages]}")
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
    text_sensors:   dict[str, TextSensorInfo]   = {}
    numbers:        dict[str, NumberInfo]       = {}
    buttons:        dict[str, ButtonInfo]       = {}

    for e in entities:
        sfx = object_id_suffix(e.object_id, prefix)
        if isinstance(e, NumberInfo):
            numbers[sfx] = e
        elif isinstance(e, ButtonInfo):
            buttons[sfx] = e
        elif isinstance(e, SensorInfo):
            sensors[sfx] = e
        elif isinstance(e, TextSensorInfo):
            text_sensors[sfx] = e
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

    for pkg_key, spec in active_packages:
        if pkg_key in BASE_PACKAGES:
            total_pass += 1
            continue

        label = spec["label"]
        desc = spec["description"]
        pkg_pass = pkg_fail = 0
        lines = []

        tolerate_nan = spec.get("tolerate_nan", False)
        for suffix, lo, hi, unit in spec.get("sensors", []):
            ok, msg = check_sensor(suffix, lo, hi, unit, sensors, states_by_key, tolerate_nan)
            lines.append(msg)
            if ok: pkg_pass += 1
            else:   pkg_fail += 1

        tolerate_empty = spec.get("tolerate_empty_text", False)
        for suffix in spec.get("text_sensors", []):
            ok, msg = check_text_sensor(suffix, text_sensors, states_by_key, tolerate_empty)
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

        for suffix in spec.get("buttons", []):
            ok, msg = check_button(suffix, buttons, states_by_key)
            lines.append(msg)
            if ok: pkg_pass += 1
            else:   pkg_fail += 1

        for suffix in spec.get("numbers", []):
            ok, msg = check_number(suffix, numbers, states_by_key)
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
    for _, spec in active_packages:
        for sfx, *_ in spec.get("sensors", []):
            matched_suffixes.add(sfx)
        for key in ("binary_sensors", "switches", "covers", "lights", "text_sensors",
                    "numbers", "buttons"):
            matched_suffixes.update(spec.get(key, []))

    all_suffixes = (
        list(sensors) + list(binary_sensors) + list(switches) + list(covers) +
        list(lights) + list(media_players) + list(text_sensors) + list(numbers) +
        list(buttons)
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
