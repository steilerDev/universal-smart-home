#!/usr/bin/env python3
"""Trigger a compile + OTA on the self-hosted ESPHome Device Builder over its WebSocket API.

The heavy build (PlatformIO toolchain, ~1 GB) and the OTA upload happen on the
builder host, not in this sandbox. This client only:

  1. mints an Authentik machine-to-machine JWT (OAuth2 client-credentials),
  2. opens the builder's single ``/ws`` endpoint through Authentik with that JWT,
  3. calls ``firmware/install`` for each device and streams the job to completion,
  4. exits non-zero if any job failed.

Assumes the device YAMLs already live on the builder (git-synced) — push to
``main`` first, then run this. See deploy/README.md and .claude/skills/deploy-device.

Usage:
    ./scripts/builder-deploy.py room-sensor-poe2
    ./scripts/builder-deploy.py room-sensor-poe2 hallway-ground
    ./scripts/builder-deploy.py --all
    ./scripts/builder-deploy.py room-sensor-poe2 --compile-only

Environment:
    ESPHOME_BUILDER_URL    wss://esphome.<domain>/ws           (required)
    AUTHENTIK_TOKEN_URL    https://auth.<domain>/application/o/token/
    AUTHENTIK_CLIENT_ID    <proxy provider client_id>
    AUTHENTIK_SVC_USER     <service-account username>
    AUTHENTIK_SVC_TOKEN    <service-account app-password>
    AUTHENTIK_CLIENT_SECRET  (optional; for confidential providers)
    AUTHENTIK_SCOPE        (optional; default "openid profile")

If none of the AUTHENTIK_* vars are set, the client connects without auth
(useful only when the builder is reached directly with native auth disabled).
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

try:
    import websockets
except ImportError:
    sys.exit("websockets not installed — run: pip3 install websockets")

REPO_ROOT = Path(__file__).resolve().parent.parent
DEVICES_DIR = REPO_ROOT / "devices"
OTA_PORT = "OTA"  # builder's OTA sentinel (matches the frontend firmwareInstall default)


# ── logging ─────────────────────────────────────────────────────────────────
GREEN, RED, YELLOW, CYAN, DIM, RESET = (
    "\033[32m", "\033[31m", "\033[33m", "\033[36m", "\033[2m", "\033[0m"
)


def log(msg: str) -> None:
    print(f"{CYAN}▸{RESET} {msg}", flush=True)


def err(msg: str) -> None:
    print(f"{RED}✗{RESET} {msg}", file=sys.stderr, flush=True)


# ── device resolution ────────────────────────────────────────────────────────

def resolve_configs(names: list[str], want_all: bool) -> list[str]:
    """Map device names → ``<name>.yaml`` config filenames the builder knows."""
    if want_all:
        files = sorted(p.name for p in DEVICES_DIR.glob("*.yaml"))
        if not files:
            sys.exit(f"No device YAMLs found in {DEVICES_DIR}")
        return files
    configs = []
    for name in names:
        stem = name[:-5] if name.endswith(".yaml") else name
        path = DEVICES_DIR / f"{stem}.yaml"
        if not path.exists():
            sys.exit(f"Device config not found: {path}")
        configs.append(f"{stem}.yaml")
    return configs


# ── Authentik machine-to-machine token ───────────────────────────────────────

def _ssl_context(insecure: bool) -> ssl.SSLContext | None:
    if not insecure:
        return None  # let the library use the default verifying context
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def fetch_jwt(insecure: bool) -> str | None:
    """Obtain a JWT issued *for the proxy provider* via OAuth2 client-credentials.

    Returns None when no Authentik env is configured (unauthenticated builder).
    """
    token_url = os.environ.get("AUTHENTIK_TOKEN_URL")
    client_id = os.environ.get("AUTHENTIK_CLIENT_ID")
    if not token_url or not client_id:
        return None

    form = {"grant_type": "client_credentials", "client_id": client_id,
            "scope": os.environ.get("AUTHENTIK_SCOPE", "openid profile")}
    user = os.environ.get("AUTHENTIK_SVC_USER")
    token = os.environ.get("AUTHENTIK_SVC_TOKEN")
    secret = os.environ.get("AUTHENTIK_CLIENT_SECRET")
    if user and token:
        # Service account: identify by username, authenticate by app-password.
        form["username"] = user
        form["password"] = token
    if secret:
        form["client_secret"] = secret
    if not (secret or (user and token)):
        sys.exit("AUTHENTIK_TOKEN_URL/CLIENT_ID set but no credentials — "
                 "provide AUTHENTIK_SVC_USER+AUTHENTIK_SVC_TOKEN or AUTHENTIK_CLIENT_SECRET")

    data = urllib.parse.urlencode(form).encode()
    req = urllib.request.Request(
        token_url, data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, context=_ssl_context(insecure), timeout=30) as r:
            payload = json.loads(r.read())
    except urllib.error.HTTPError as e:
        sys.exit(f"Authentik token request failed: HTTP {e.code} — {e.read().decode(errors='replace')}")
    except Exception as e:  # noqa: BLE001
        sys.exit(f"Authentik token request failed: {e}")

    jwt = payload.get("access_token")
    if not jwt:
        sys.exit(f"Authentik token response had no access_token: {payload}")
    log(f"Authenticated to Authentik (token expires in {payload.get('expires_in', '?')}s)")
    return jwt


def auth_headers(jwt: str | None, use_basic: bool) -> dict[str, str]:
    if jwt is None:
        return {}
    if use_basic:
        # Reserved-username Basic flow: goauthentik.io/token:<jwt> behaves as Bearer.
        blob = base64.b64encode(f"goauthentik.io/token:{jwt}".encode()).decode()
        return {"Authorization": f"Basic {blob}"}
    return {"Authorization": f"Bearer {jwt}"}


# ── WebSocket protocol helpers ────────────────────────────────────────────────

class Builder:
    """Thin command/response + streaming wrapper over the builder's /ws protocol."""

    def __init__(self, ws) -> None:
        self._ws = ws
        self._id = 0

    def _next_id(self) -> str:
        self._id += 1
        return str(self._id)

    async def _send(self, command: str, args: dict | None = None) -> str:
        mid = self._next_id()
        msg = {"command": command, "message_id": mid}
        if args:
            msg["args"] = args
        await self._ws.send(json.dumps(msg))
        return mid

    async def call(self, command: str, args: dict | None = None) -> dict:
        """Send a command, return its ``result`` (raises on ``error_code``)."""
        mid = await self._send(command, args)
        async for raw in self._ws:
            data = json.loads(raw)
            if data.get("message_id") != mid:
                continue  # server_info / unrelated stream — ignore
            if "error_code" in data:
                raise RuntimeError(f"{command}: {data['error_code']} — {data.get('details', '')}")
            if "result" in data:
                return data["result"]
        raise RuntimeError(f"{command}: connection closed before result")

    async def follow(self, command: str, args: dict, on_output, timeout: float) -> dict:
        """Send a streaming command; forward ``output`` events, return terminal ``result``."""
        mid = await self._send(command, args)
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"{command}: no terminal result within {timeout}s")
            raw = await asyncio.wait_for(self._ws.recv(), timeout=remaining)
            data = json.loads(raw)
            if data.get("message_id") != mid:
                continue
            if "error_code" in data:
                raise RuntimeError(f"{command}: {data['error_code']} — {data.get('details', '')}")
            event = data.get("event")
            if event == "output":
                on_output(data.get("data", ""))
            elif event == "result" or "result" in data:
                return data.get("data") if event == "result" else data["result"]


def _job_id(result: dict) -> str:
    jid = result.get("id") or result.get("job_id")
    if not jid:
        raise RuntimeError(f"firmware/install returned no job id: {result}")
    return str(jid)


def _succeeded(terminal: dict | None) -> bool:
    if not isinstance(terminal, dict):
        return False
    if "success" in terminal:
        return bool(terminal["success"])
    if "code" in terminal:
        return terminal["code"] == 0
    return str(terminal.get("status", "")).upper() in {"COMPLETED", "SUCCESS"}


async def deploy_one(builder: Builder, config: str, compile_only: bool, timeout: float) -> bool:
    command = "firmware/compile" if compile_only else "firmware/install"
    args = {"configuration": config}
    if not compile_only:
        args["port"] = OTA_PORT
    log(f"{config}: {command} …")
    result = await builder.call(command, args)
    job_id = _job_id(result)

    def emit(line: str) -> None:
        for ln in str(line).splitlines() or [""]:
            print(f"  {DIM}{config}|{RESET} {ln}", flush=True)

    terminal = await builder.follow("firmware/follow_job", {"job_id": job_id}, emit, timeout)
    ok = _succeeded(terminal)
    tag = f"{GREEN}✓ SUCCESS{RESET}" if ok else f"{RED}✗ FAILED{RESET}"
    print(f"{tag}  {config}  ({terminal})", flush=True)
    return ok


async def run(args) -> int:
    # Validate device names first so typos fail before any network/auth setup.
    configs = resolve_configs(args.devices, args.all)

    server = args.server or os.environ.get("ESPHOME_BUILDER_URL")
    if not server:
        sys.exit("Builder URL not set — pass --server or set ESPHOME_BUILDER_URL "
                 "(e.g. wss://esphome.<domain>/ws)")

    jwt = fetch_jwt(args.insecure)
    headers = auth_headers(jwt, args.basic)

    log(f"Connecting to {server} …")
    connect_kwargs = {"ssl": _ssl_context(args.insecure)} if server.startswith("wss") else {}
    try:
        ws = await websockets.connect(server, additional_headers=headers, **connect_kwargs)
    except TypeError:
        # websockets < 14 used extra_headers
        ws = await websockets.connect(server, extra_headers=headers, **connect_kwargs)

    async with ws:
        # First frame is the ServerInfoMessage push.
        info = json.loads(await asyncio.wait_for(ws.recv(), timeout=15))
        log(f"Server: version={info.get('server_version', '?')} "
            f"requires_auth={info.get('requires_auth')}")

        builder = Builder(ws)
        if args.sync_timeout > 0:
            log(f"Allowing {args.sync_timeout:.0f}s for the builder's git-sync poll "
                f"to pick up the pushed commit …")
            await asyncio.sleep(args.sync_timeout)

        results = []
        for cfg in configs:
            try:
                results.append(await deploy_one(builder, cfg, args.compile_only, args.timeout))
            except Exception as e:  # noqa: BLE001
                err(f"{cfg}: {e}")
                results.append(False)

    ok = sum(results)
    total = len(results)
    print(f"\n{'─' * 50}")
    tag = GREEN if ok == total else RED
    print(f"  {tag}{ok}/{total} succeeded{RESET}")
    print(f"{'─' * 50}")
    return 0 if ok == total else 1


def main() -> None:
    p = argparse.ArgumentParser(description="Deploy ESPHome devices via the Device Builder /ws API.")
    p.add_argument("devices", nargs="*", help="device name(s) (→ <name>.yaml)")
    p.add_argument("--all", action="store_true", help="deploy every devices/*.yaml")
    p.add_argument("--server", help="builder /ws URL (default $ESPHOME_BUILDER_URL)")
    p.add_argument("--compile-only", action="store_true", help="compile without OTA upload")
    p.add_argument("--timeout", type=float, default=900, help="per-job timeout seconds (default 900)")
    p.add_argument("--sync-timeout", type=float, default=20,
                   help="seconds to wait for the builder git-sync poll before deploying (default 20)")
    p.add_argument("--basic", action="store_true",
                   help="use Authentik Basic (goauthentik.io/token) instead of Bearer")
    p.add_argument("--insecure", action="store_true", help="skip TLS certificate verification")
    args = p.parse_args()

    if not args.devices and not args.all:
        p.error("give at least one device name or --all")
    sys.exit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
