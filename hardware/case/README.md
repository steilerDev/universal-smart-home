# Cases

One directory per enclosure. Each holds the Fusion 360 source plus its exports.

| Case | For | Custom PCB? |
|------|-----|-------------|
| [`room-sensor/`](room-sensor/) | Room sensor units (~25×) | Yes — `hardware/pcb/RoomSensor-{Main,Back}Plate` |
| [`utility-sensor/`](utility-sensor/) | Utility sensor (basement metering) | No — Olimex board + screw terminals only |

## File conventions

- `*.f3d` — Fusion 360 native source (the editable master)
- `*.step` — STEP export, opens without Fusion 360
- `*.stl` — print-ready mesh
- `renders/` — PNG renders exported from Fusion 360

CAD files are marked `binary` in `.gitattributes` so git never tries to diff or
merge them. That also means **they do not merge** — coordinate before editing one.
