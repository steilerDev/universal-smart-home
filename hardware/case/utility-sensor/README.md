# Utility Sensor Case

Custom enclosure for the basement metering unit, designed in Fusion 360.

Unlike the room sensors this device has **no custom PCB** — it is a stock
[Olimex ESP32-POE2](https://www.olimex.com/Products/IoT/ESP32/ESP32-POE2/open-source-hardware)
with the water-meter and RS485 wiring landed straight on screw terminals. The
case is therefore the only custom-fabricated part, which is why it is tracked
here on its own.

## What it has to hold

| Item | Notes |
|------|-------|
| Olimex ESP32-POE2 | Standoffs; RJ45 must reach the wall |
| 8 × water meter leads | Pulse + 3.3V + GND per line — see `devices/utility-sensor.yaml` for the GPIO map |
| RS485 leg → well probe | QDY30A submersible level transmitter |
| RS485 leg → grid meter | Eastron SDM — wired for, not yet populated |

## Design Files

- `*.f3d` — Fusion 360 native source (stored as binary in git)
- `*.step` — STEP export (open without Fusion 360)
- `*.stl` — print-ready STL export
- `renders/` — PNG renders exported from Fusion 360

> ⚠️ **The CAD files are not in the repo yet.** The device was built before this
> repo existed. Export the current Fusion 360 design into this directory
> (`.f3d` + `.step` + `.stl`) so the case stops living only in someone's Fusion
> cloud project.
