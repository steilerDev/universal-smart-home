# Claude Code agent, colocated with the ESPHome Device Builder.
#
# This image does NOT compile firmware (the builder does the heavy PlatformIO
# work). It only needs to: edit YAML, validate it (`esphome config` — Python
# package only, no toolchain), drive the builder over its /ws API
# (scripts/builder-deploy.py → websockets), and health-check devices
# (scripts/check-device.py → aioesphomeapi). Kept deliberately lean.
FROM node:22-bookworm-slim

# System deps: Python for esphome + the tooling scripts, git for the durability step.
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 python3-pip python3-venv git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# The Claude Code CLI.
RUN npm install -g @anthropic-ai/claude-code

# ESPHome (validation) + the repo's tooling deps (websockets, aioesphomeapi, PyYAML).
COPY requirements-tooling.txt /tmp/requirements-tooling.txt
RUN pip3 install --break-system-packages --no-cache-dir \
        esphome -r /tmp/requirements-tooling.txt \
    && rm -f /tmp/requirements-tooling.txt

# The repo is bind-mounted here at runtime (see docker-compose.yml).
WORKDIR /repo

# Attach with: docker exec -it claude claude
CMD ["sleep", "infinity"]
