---
name: deploy-device
description: Deploy an ESPHome device in this repo via the self-hosted Device Builder — validate locally, trigger compile+OTA over the builder's WebSocket API, health-check, then commit+push to persist. Use when asked to deploy, flash, OTA, or "push firmware to" a device instead of compiling locally.
---

# Deploy a device via the ESPHome Device Builder

The agent runs in the `claude` container **beside** the builder. The repo is
bind-mounted into both at `/repo`, so your edits to `devices/*.yaml` are visible
to the builder **instantly** — no git push is needed to flash. The builder does
the heavy compile + OTA; this container only edits, validates, and drives its API
over the internal network (`ws://esphome-builder:6052/ws`, no auth).

## Preconditions (fail fast if missing)

- `ESPHOME_BUILDER_URL` is set (preset in the compose env to
  `ws://esphome-builder:6052/ws`). If unset, tell the user and stop — do **not**
  fall back to a local `esphome run` unless they ask (that needs the PlatformIO
  workaround stack in CLAUDE.md).
- `websockets` is installed (baked into the claude image; otherwise
  `pip3 install -r requirements-tooling.txt`).

## Steps

1. **Validate locally** (cheap, no compile):
   ```bash
   esphome config devices/<name>.yaml
   ```
   Fix any errors before proceeding.

2. **Trigger compile + OTA on the builder** and stream the job:
   ```bash
   ./scripts/builder-deploy.py <name>
   ```
   - The shared mount means the builder already sees your edit — no push first.
   - The script calls `firmware/install` and follows the job to a terminal
     `result{success}`. It **exits non-zero on failure** — check it.
   - Multiple devices: `./scripts/builder-deploy.py <a> <b>`; everything: `--all`.
   - Compile without flashing: `--compile-only`.

3. **Health-check** the running device:
   ```bash
   ./scripts/check-device.py <name>
   ```

4. **Persist to remote** (durability — git is the source of truth, but *not*
   required for the deploy above to have worked):
   ```bash
   git add -A && git commit -m "<what changed>"
   git push origin main
   ```

5. **Report**: the streamed build result (SUCCESS/FAILED), the health-check
   summary, and the pushed commit. If the build failed, surface the builder's
   error output — don't retry blindly.

## Notes

- One device name maps to `devices/<name>.yaml` (the builder's config filename).
- Source of truth is the YAML in git; don't edit devices in the builder UI.
- **Fallback (out-of-network):** running the client from outside the Docker
  network reaches the builder through Authentik (`wss://esphome.<domain>/ws`) —
  set the `AUTHENTIK_*` env vars (see `deploy/README.md`) so it mints a Bearer
  JWT; add `--basic` if the outpost rejects Bearer on the WS upgrade.
