# Deploying firmware via the ESPHome Device Builder

Firmware is compiled and OTA-flashed by the self-hosted **ESPHome Device Builder**
container, not by compiling in the agent's environment.

```
host checkout ──bind-mount──► esphome (builder)   (runs the builder on devices/)
              └─bind-mount──► coder / agent      (edits devices/*.yaml)
                                 │  same files — edits are visible instantly ↑
  agent ── ws://esphome:6052/ws (no auth) ──────┘  compile + OTA
  browsers ── https://esphome.<domain> ── Authentik SSO ──► esphome (builder)
```

- **Shared mount, no git-sync** — the agent and the builder see the *same* files on
  disk, so a YAML edit is visible to the builder immediately. No commit or push is
  required to flash.
- **Git stays the source of truth** — `commit + push` is a durability step *after* a
  successful deploy, not part of the deploy path.
- **No auth for the agent** — it reaches the builder directly on the internal Docker
  network. The builder's native auth is unset (`requires_auth: false`); Authentik only
  gates the browser UI.

## Builder endpoint

| | |
|---|---|
| WebSocket API (agent) | `ws://esphome:6052/ws` |
| Browser UI | `https://esphome.<domain>` (Authentik SSO) |

Set `ESPHOME_BUILDER_URL=ws://esphome:6052/ws` in the agent's environment, or pass
`--server` to `scripts/builder-deploy.py`.

## Deploy loop

```bash
esphome config devices/room-sensor-poe2.yaml   # 1. validate locally (cheap, no compile)
./scripts/builder-deploy.py room-sensor-poe2   # 2. compile + OTA on the builder, streamed
./scripts/check-device.py room-sensor-poe2     # 3. health check
git add -A && git commit -m "…" && git push origin main   # 4. persist (durability)
```

The `deploy-device` skill codifies this loop.

`scripts/builder-deploy.py` speaks the builder's single `/ws` endpoint, streams job
output, and exits non-zero if any job fails. `--all` deploys every device;
`--compile-only` skips the OTA upload.

**A deploy is two jobs, not one.** On this builder (1.0.12 / ESPHome 2026.6.2)
`firmware/install` only *compiles* — its job ends at "Successfully compiled program"
and never contacts the device. The OTA is a separate `firmware/upload` job
(`job_type: upload`). The script runs `firmware/install` → `firmware/upload`, each
followed via `firmware/follow_job`. Calling install alone reports a green deploy
while the device keeps running its old firmware.

## Troubleshooting

| Symptom | Cause |
|---------|-------|
| `firmware/upload`: `Connecting to <ip> port 3232 failed: [Errno 113] No route to host` | **Nothing answers at that IP.** Port 3232 is the ESPHome OTA port; ARP finding no host produces this error, which reads like a routing fault but usually means `device_ip` is wrong (or the device is powered down). Verify the address before touching any network config. |
| `firmware/install` says SUCCESS but the device behaves as before | Expected — install only compiles. The OTA is the separate `firmware/upload` job; see above. |

## Why the builder's config dir points at `devices/`

The builder's config scanner (`list_yaml_files`) is **top-level only** and skips
`secrets.yaml` and dotfiles. Our device YAMLs live in `devices/` and
`!include ../packages/...`, so the container mounts the **whole repo** but runs the
dashboard against the `devices/` subdirectory. Includes,
`external_components: ../components`, and the `devices/secrets.yaml → ../secrets.yaml`
symlink all resolve because the parent tree is present on disk.

`secrets.yaml` is gitignored and lives at the checkout **root**; the committed
`devices/secrets.yaml` symlink points at it, so the builder finds secrets when
compiling `devices/*.yaml`.

## Notes

- **Source of truth is the YAML in git.** Treat the builder UI as deploy/observe only;
  set friendly names via device-YAML `substitutions`, so the gitignored builder state
  (`.device-builder*.json`) stays disposable.
- The builder image's default `CMD` is `dashboard /config`; its entrypoint rewrites the
  `dashboard` subcommand to the Device Builder backend (`esphome-device-builder`). Any
  other first arg is passed to the plain `esphome` CLI, so the builder `command` **must**
  begin with `dashboard`. Verified on 2026.6.2 and 2026.6.5. Pin a tag instead of
  `:latest` for reproducibility.
