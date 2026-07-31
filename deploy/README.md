# ESPHome Device Builder + Claude agent — colocated stack

This directory deploys **two** containers on the primary Docker host:

- **`esphome-builder`** — the ESPHome Device Builder (compile + OTA server),
  fronted by the existing **Authentik** proxy provider for browser access.
- **`claude`** — the Claude Code agent, running *inside* the Docker network,
  **behind** the Authentik gate.

The repo is bind-mounted into **both** at `/repo`, and the two share an internal
network, which removes the two frictions of the git-driven design:

```
host checkout /opt/docker/home_esp ──bind-mount /repo──► esphome-builder  (runs /repo/devices)
                                    └─bind-mount /repo──► claude           (edits /repo/devices)
                                                            │  edits are instantly visible ↑ (same files)
  claude ── ws://esphome-builder:6052/ws (no auth) ─────────┘  compile + OTA
  browsers ── https://esphome.<domain> ── Authentik SSO ──► esphome-builder  (unchanged)
```

- **No auth for the agent** — it reaches the builder directly on the internal
  `esphome-net`. The builder's native auth stays unset; Authentik only gates the
  browser UI.
- **No git-sync** — the shared mount means the agent's YAML edits are visible to
  the builder immediately, with no commit required to flash.
- **Git stays the source of truth** — `commit + push` is a durability step *after*
  a successful deploy, not part of the deploy path.

## Why the config dir points at `/repo/devices`

The builder's config scanner (`list_yaml_files`) is **top-level only** and skips
`secrets.yaml` and dotfiles. Our device YAMLs live in `devices/` and `!include
../packages/...`, so the container mounts the **whole repo** at `/repo` but runs
`esphome-device-builder /repo/devices`. Includes, `external_components: ../components`,
and the `devices/secrets.yaml → ../secrets.yaml` symlink all resolve because the
parent tree is present on disk.

## 1. Provision the checkout on the host

```bash
sudo mkdir -p /opt/docker && cd /opt/docker
git clone https://github.com/steilerDev/universal-smart-home home_esp
cd home_esp
# secrets.yaml is gitignored and lives at the checkout root; place it once:
cp secrets.template.yaml secrets.yaml && $EDITOR secrets.yaml
```

`secrets.yaml` sits at the checkout **root**; the committed `devices/secrets.yaml`
symlink points at it, so the builder finds secrets when compiling `devices/*.yaml`.

## 2. Authentik (browser SSO only — no change needed)

The existing Proxy Provider + Application for `esphome.<domain>` stays exactly as
it is and keeps SSO-gating the browser UI. **No machine-to-machine service account
is needed** — the agent lives inside the network and never traverses the outpost.

## 3. Start the stack

```bash
cd deploy
cp .env.example .env && $EDITOR .env
#   ESPHOME_REPO_DIR   → /opt/docker/home_esp  (the checkout above)
#   CLAUDE_CONFIG_DIR  → absolute path to the host ~/.claude to reuse
#   AUTHENTIK_NETWORK  → your Authentik outpost network (docker network ls)
docker compose up -d
docker compose ps                 # esphome-builder + claude, no published builder port
```

`CLAUDE_CONFIG_DIR` is bind-mounted to `/root/.claude` in the agent container so it
reuses your existing Claude login and settings — no API key in the repo. Give an
**absolute** path (Docker does not expand `~`).

## 4. Run the agent

```bash
docker exec -it claude claude
```

`ESPHOME_BUILDER_URL` is preset in the compose environment to
`ws://esphome-builder:6052/ws`, so deploys work with no further configuration:

```bash
esphome config devices/room-sensor-poe2.yaml   # validate
./scripts/builder-deploy.py room-sensor-poe2   # compile + OTA on the builder
./scripts/check-device.py room-sensor-poe2     # health check
git add -A && git commit -m "…" && git push origin main   # persist (durability)
```

The `deploy-device` skill codifies this loop.

## Fallback: running the client from outside the network

If you ever run `scripts/builder-deploy.py` from *outside* the Docker network
(e.g. a dev sandbox), it reaches the builder through Authentik instead. Set:

```bash
export ESPHOME_BUILDER_URL='wss://esphome.<domain>/ws'
export AUTHENTIK_TOKEN_URL='https://auth.<domain>/application/o/token/'
export AUTHENTIK_CLIENT_ID='<proxy-provider-client-id>'
export AUTHENTIK_SVC_USER='<service-account>'
export AUTHENTIK_SVC_TOKEN='<app-password>'
```

The client mints an OAuth2 client-credentials JWT and presents it as
`Authorization: Bearer <JWT>` on the WS upgrade (`--basic` switches to the
`goauthentik.io/token` variant if the outpost strips Bearer). This path needs an
Authentik service account bound to the ESPHome application, and the Authentik
hostnames allowed in that environment's network policy. It is **not** required for
the in-network `claude` container above.

## Notes

- **Source of truth is the YAML in git.** Treat the builder UI as deploy/observe
  only; set friendly names via device-YAML `substitutions`, so the gitignored
  builder state (`.device-builder*.json`) stays disposable.
- The builder is **never published to the host** — it is reachable only via the
  Authentik outpost (browser) and the internal `esphome-net` (agent).
- The Device Builder is the default command of `ghcr.io/esphome/esphome` as of
  ESPHome 2026.6.0. Pin a tag instead of `:latest` for reproducibility.
