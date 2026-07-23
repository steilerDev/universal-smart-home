# ESPHome Device Builder — self-hosted build/deploy server

This directory deploys the **ESPHome Device Builder** on the primary Docker host as
the build + OTA server for this repo, fronted by the existing **Authentik** proxy
provider. The Claude Code agent edits YAML, pushes to `main`, and triggers builds
over the builder's WebSocket API — no local PlatformIO toolchain in the sandbox.

```
agent → git push main → GitHub
agent → wss://esphome.<domain>/ws  (Authentik Bearer JWT) → outpost → builder
builder host: git-sync sidecar pulls origin/main every 15s → builder compiles + OTA
```

## Why the config dir points at `devices/`

The builder's config scanner (`list_yaml_files`) is **top-level only** and skips
`secrets.yaml` and dotfiles. Our device YAMLs live in `devices/` and `!include
../packages/...`, so the container mounts the **whole repo** at `/repo` but runs
`esphome-device-builder /repo/devices`. Includes, `external_components: ../components`,
and the `devices/secrets.yaml → ../secrets.yaml` symlink all resolve because the
parent tree is present on disk.

## 1. Provision the checkout on the host

```bash
sudo mkdir -p /srv/esphome && cd /srv/esphome
git clone https://github.com/steilerDev/universal-smart-home
cd universal-smart-home
# secrets.yaml is gitignored and survives `git reset --hard`; place it once:
cp secrets.template.yaml secrets.yaml && $EDITOR secrets.yaml
```

`secrets.yaml` sits at the checkout **root**; the committed `devices/secrets.yaml`
symlink points at it, so the builder finds secrets when compiling `devices/*.yaml`.

## 2. Configure Authentik (single hostname, single auth layer)

The existing Proxy Provider + Application for `esphome.<domain>` stays unchanged and
keeps SSO-gating the browser UI. Add **machine-to-machine** access for the agent:

1. **Service account** — Directory → Users → Create service account, e.g.
   `svc-esphome-deploy`. Generate an **App password** token (save it).
2. **Authorize it** — bind the service account (or a group it's in) to the ESPHome
   Application so its token is allowed through the proxy.
3. **Client ID** — Providers → your ESPHome proxy provider → copy the **Client ID**.

The agent then fetches a JWT *issued for the proxy provider* and presents it as a
Bearer token on the WebSocket. Authentik's proxy accepts
`Authorization: Bearer <JWT>` (and the `goauthentik.io/token` Basic variant) and
forwards the WS upgrade to the builder. No path exemptions, no extra ports.

Verify the token endpoint by hand:

```bash
curl -s -X POST https://auth.<domain>/application/o/token/ \
  -d grant_type=client_credentials \
  -d client_id='<proxy-provider-client-id>' \
  -d username='svc-esphome-deploy' \
  -d password='<app-password>' \
  -d scope='openid profile' | jq .access_token
```

Leave the builder's own `ESPHOME_USERNAME` / `ESPHOME_PASSWORD` **unset** — Authentik
is the only auth layer (setting native auth would collide with the `Authorization`
header the outpost consumes). The builder is only reachable via the outpost's
internal network, never published to the host.

## 3. Start it

```bash
cd deploy
cp .env.example .env && $EDITOR .env    # set ESPHOME_REPO_DIR + AUTHENTIK_NETWORK
docker compose up -d
docker compose logs -f esphome-git-sync # confirm it reaches origin/main
```

Find your Authentik network name with `docker network ls` (the outpost's network).

## 4. Point the agent at it

Set these in the sandbox environment (`/etc/sandbox-persistent.sh`) so
`scripts/builder-deploy.py` and the `deploy-device` skill can reach the builder:

```bash
export ESPHOME_BUILDER_URL='wss://esphome.<domain>/ws'
export AUTHENTIK_TOKEN_URL='https://auth.<domain>/application/o/token/'
export AUTHENTIK_CLIENT_ID='<proxy-provider-client-id>'
export AUTHENTIK_SVC_USER='svc-esphome-deploy'
export AUTHENTIK_SVC_TOKEN='<app-password>'
```

The Authentik hostnames must be reachable from the sandbox — allow them in the
network policy the same way the device IPs are (`sbx policy allow network esphome.<domain>`).

Then, from the repo root:

```bash
pip3 install -r requirements-tooling.txt
git push origin main
./scripts/builder-deploy.py room-sensor-poe2
./scripts/check-device.py room-sensor-poe2
```

## Notes

- **git-sync** only runs `git reset --hard origin/<ref>` (tracked files). Untracked
  builder state (`.device-builder*.json` job history/labels) and `secrets.yaml`
  persist. It has no listening port.
- **Source of truth is the YAML in git.** Treat the builder UI as deploy/observe
  only; set friendly names via device-YAML `substitutions`, not the UI, so the
  gitignored builder state stays disposable.
- **`--basic`** on the deploy client switches to the `goauthentik.io/token` Basic
  header if your outpost strips `Authorization: Bearer` on the WS upgrade.
- The Device Builder is the default command of `ghcr.io/esphome/esphome` as of
  ESPHome 2026.6.0. Pin a tag instead of `:latest` for reproducibility.
