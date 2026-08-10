---
name: deploy-device
description: Deploy an ESPHome device in this repo via the self-hosted Device Builder — validate locally, trigger compile+OTA over the builder's WebSocket API, health-check, then commit+push to persist. Use when asked to deploy, flash, OTA, or "push firmware to" a device instead of compiling locally.
---

# Deploy a device via the ESPHome Device Builder

The agent and the ESPHome Device Builder share a bind mount of this repo, so your
edits to `devices/*.yaml` are visible to the builder **instantly** — no git push
is needed to flash. The builder does the heavy compile + OTA; this environment
only edits, validates, and drives its API over the internal Docker network
(`ws://esphome:6052/ws`, no auth).

## Preconditions (fail fast if missing)

- `ESPHOME_BUILDER_URL` is set to `ws://esphome:6052/ws`. If unset, pass
  `--server ws://esphome:6052/ws` — do **not** fall back to a local `esphome run`
  unless the user asks (that needs the PlatformIO workaround stack in CLAUDE.md).
- `websockets` is installed (otherwise `pip3 install -r requirements-tooling.txt`).

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
- The builder's browser UI (`https://esphome.<domain>`) is Authentik-gated, but the
  WebSocket API on the internal network is not — the client connects unauthenticated.
