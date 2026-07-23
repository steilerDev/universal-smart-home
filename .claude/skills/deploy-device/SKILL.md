---
name: deploy-device
description: Deploy an ESPHome device in this repo via the self-hosted Device Builder — validate locally, push to main, trigger compile+OTA over the builder's WebSocket API, then health-check. Use when asked to deploy, flash, OTA, or "push firmware to" a device instead of compiling locally in the sandbox.
---

# Deploy a device via the ESPHome Device Builder

The builder on the primary Docker host does the heavy compile + OTA. This sandbox
**does not compile** — it edits YAML, pushes to git, and drives the builder's API.
Git is the sync channel; the builder git-syncs `main` and flashes the device.

## Preconditions (fail fast if missing)

- `ESPHOME_BUILDER_URL` and the `AUTHENTIK_*` env vars are set (see `deploy/README.md`).
  If unset, tell the user to configure them and stop — do **not** fall back to a local
  `esphome run` unless they ask (that needs the PlatformIO workaround stack in CLAUDE.md).
- `websockets` is installed: `pip3 install -r requirements-tooling.txt`.

## Steps

1. **Validate locally** (cheap, no compile):
   ```bash
   esphome config devices/<name>.yaml
   ```
   Fix any errors before proceeding.

2. **Commit + push to `main`** (git is just the storage backend — no PR):
   ```bash
   git add -A && git commit -m "<what changed>"
   git push origin main
   ```
   The builder's git-sync sidecar pulls `origin/main` within ~15s.

3. **Trigger compile + OTA on the builder** and stream the job:
   ```bash
   ./scripts/builder-deploy.py <name>
   ```
   - The script waits out the sync poll, calls `firmware/install`, and follows the
     job to a terminal `result{success}`. It **exits non-zero on failure** — check it.
   - Multiple devices: `./scripts/builder-deploy.py <a> <b>`; everything: `--all`.
   - Compile without flashing: `--compile-only`.

4. **Health-check** the running device:
   ```bash
   ./scripts/check-device.py <name>
   ```

5. **Report**: the streamed build result (SUCCESS/FAILED), the health-check summary,
   and the pushed commit. If the build failed, surface the builder's error output —
   don't retry blindly.

## Notes

- One device name maps to `devices/<name>.yaml` (the builder's config filename).
- Source of truth is the YAML in git; don't edit devices in the builder UI.
- If the WS connection is rejected on the upgrade, retry with `--basic` (Authentik
  `goauthentik.io/token` header variant).
