"""Device pairing endpoint for Glyx iOS app."""

from __future__ import annotations

import secrets
import socket
from typing import Any

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

router = APIRouter(tags=["Pairing"])


def get_local_ip() -> str:
    """Get the local IP address of this machine."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "localhost"


def get_hostname() -> str:
    """Get the hostname of this machine."""
    return socket.gethostname()


@router.get("/pair", response_class=PlainTextResponse, summary="Get pairing script")
async def get_pair_script() -> str:
    """
    Returns a shell script that sets up device pairing for the Glyx iOS app.

    Usage:
        curl -sL api.glyx.ai/pair | bash

    The script will:
    1. Generate a unique pairing code
    2. Start the glyx daemon (relay server)
    3. Display a QR code for the iOS app to scan
    """
    return PAIR_SCRIPT


PAIR_SCRIPT = r'''#!/bin/bash
# Glyx Device Pairing Script
# Usage: curl -sL glyx.ai/pair | bash
#
# This script:
# 1. Clones/updates glyx-mcp repo
# 2. Generates a unique device ID
# 3. Starts the unified FastAPI/FastMCP server with Rich logs
# 4. Displays a QR code for the Glyx iOS app to scan

set -e

# Config
GLYX_DIR="$HOME/.glyx"
REPO_DIR="$GLYX_DIR/glyx-mcp"
DEVICE_ID_FILE="$GLYX_DIR/device_id"
REPO_URL="https://github.com/glyx-ai/glyx-mcp.git"

# Create config directory
mkdir -p "$GLYX_DIR"

# Cleanup function
cleanup() {
    echo ""
    echo "Shutting down..."
    # Kill background server if running
    jobs -p | xargs -r kill 2>/dev/null || true
    exit 0
}
trap cleanup INT TERM

# Check for uv
if ! command -v uv &>/dev/null; then
    echo "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi

# Clone or update repo
if [[ -d "$REPO_DIR/.git" ]]; then
    echo "Updating glyx-mcp..."
    cd "$REPO_DIR"
    git pull --quiet
else
    echo "Cloning glyx-mcp..."
    git clone --quiet "$REPO_URL" "$REPO_DIR"
    cd "$REPO_DIR"
fi

# Get or create device ID
if [[ -f "$DEVICE_ID_FILE" ]]; then
    DEVICE_ID=$(cat "$DEVICE_ID_FILE")
else
    DEVICE_ID=$(uuidgen 2>/dev/null || cat /proc/sys/kernel/random/uuid 2>/dev/null || python3 -c "import uuid; print(uuid.uuid4())")
    DEVICE_ID=$(echo "$DEVICE_ID" | tr '[:upper:]' '[:lower:]')
    echo "$DEVICE_ID" > "$DEVICE_ID_FILE"
fi

# Get hostname
HOSTNAME=$(hostname -s)
USER=$(whoami)

# Detect installed agents
AGENTS=""
command -v claude &>/dev/null && AGENTS="${AGENTS}claude,"
command -v cursor &>/dev/null && AGENTS="${AGENTS}cursor,"
command -v codex &>/dev/null && AGENTS="${AGENTS}codex,"
command -v aider &>/dev/null && AGENTS="${AGENTS}aider,"
AGENTS="${AGENTS%,}"

# Build QR payload
QR_PAYLOAD="glyx://pair?device_id=${DEVICE_ID}&host=${HOSTNAME}&user=${USER}&name=${HOSTNAME}"
[[ -n "$AGENTS" ]] && QR_PAYLOAD="${QR_PAYLOAD}&agents=${AGENTS}"

# Show QR code
clear
echo ""
echo "   ██████╗ ██╗  ██╗   ██╗██╗  ██╗"
echo "  ██╔════╝ ██║  ╚██╗ ██╔╝╚██╗██╔╝"
echo "  ██║  ███╗██║   ╚████╔╝  ╚███╔╝ "
echo "  ██║   ██║██║    ╚██╔╝   ██╔██╗ "
echo "  ╚██████╔╝██████╗ ██║   ██╔╝ ██╗"
echo "   ╚═════╝ ╚═════╝ ╚═╝   ╚═╝  ╚═╝"
echo ""
echo "        Scan with the Glyx iOS app"
echo ""

if command -v qrencode &>/dev/null; then
    qrencode -t ANSIUTF8 "$QR_PAYLOAD"
elif python3 -c "import qrcode" 2>/dev/null; then
    python3 -c "import qrcode; qr = qrcode.QRCode(border=1); qr.add_data('$QR_PAYLOAD'); qr.print_ascii(invert=True)"
else
    echo "Manual entry: $QR_PAYLOAD"
    echo "(Install qrencode for QR code: brew install qrencode)"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Device: $HOSTNAME ($USER)"
echo "ID: $DEVICE_ID"
[[ -n "$AGENTS" ]] && echo "Agents: $AGENTS"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "Starting server..."
echo ""

# Sync dependencies and start server
cd "$REPO_DIR"
uv sync
GLYX_DEVICE_ID="$DEVICE_ID" exec uv run task dev
'''
