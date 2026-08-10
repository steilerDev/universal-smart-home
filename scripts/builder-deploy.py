#!/usr/bin/env python3
"""Trigger a compile + OTA on the self-hosted ESPHome Device Builder over its WebSocket API.

The heavy build (PlatformIO toolchain, ~1 GB) and the OTA upload happen on the
builder host, not in this container. This client only:

  1. opens the builder's single ``/ws`` endpoint,
  2. calls ``firmware/install`` for each device and streams the job to completion,
  3. exits non-zero if any job failed.

The agent and the builder share a bind mount of this repo, so edits to
``devices/*.yaml`` are already visible to the builder — just run this, no push
needed to flash. The builder is reached on the internal Docker network with no
auth (``requires_auth: false``); Authentik only gates its browser UI.
See deploy/README.md and .claude/skills/deploy-device.

Usage:
    ./scripts/builder-deploy.py room-sensor-poe2
    ./scripts/builder-deploy.py room-sensor-poe2 hallway-ground
    ./scripts/builder-deploy.py --all
    ./scripts/builder-deploy.py room-sensor-poe2 --compile-only

Environment:
    ESPHOME_BUILDER_URL    ws://esphome:6052/ws        (required)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
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
                 "(e.g. ws://esphome:6052/ws)")

    log(f"Connecting to {server} …")
    async with await websockets.connect(server) as ws:
        # First frame is the ServerInfoMessage push.
        info = json.loads(await asyncio.wait_for(ws.recv(), timeout=15))
        log(f"Server: version={info.get('server_version', '?')} "
            f"requires_auth={info.get('requires_auth')}")

        builder = Builder(ws)
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
    args = p.parse_args()

    if not args.devices and not args.all:
        p.error("give at least one device name or --all")
    sys.exit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
