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
# Usage: curl -sL https://glyx-mcp-996426597393.us-central1.run.app/pair | bash
#
# This script:
# 1. Generates a unique device ID
# 2. Starts the daemon to listen for tasks
# 3. Displays a QR code for the Glyx iOS app to scan
# 4. Daemon runs in foreground, streaming task output

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
NC='\033[0m'
BOLD='\033[1m'
DIM='\033[2m'

# Config
GLYX_DIR="$HOME/.glyx"
DEVICE_ID_FILE="$GLYX_DIR/device_id"
DAEMON_PID_FILE="$GLYX_DIR/daemon.pid"
DAEMON_LOG_FILE="$GLYX_DIR/daemon.log"
GLYX_API_URL="https://glyx-mcp-996426597393.us-central1.run.app"

# Create config directory
mkdir -p "$GLYX_DIR"

# Cleanup function
cleanup() {
    echo ""
    echo -e "${YELLOW}Shutting down...${NC}"
    if [[ -f "$DAEMON_PID_FILE" ]]; then
        DAEMON_PID=$(cat "$DAEMON_PID_FILE")
        if kill -0 "$DAEMON_PID" 2>/dev/null; then
            kill "$DAEMON_PID" 2>/dev/null || true
            echo -e "${DIM}Daemon stopped${NC}"
        fi
        rm -f "$DAEMON_PID_FILE"
    fi
    exit 0
}
trap cleanup INT TERM

# Get or create device ID
if [[ -f "$DEVICE_ID_FILE" ]]; then
    DEVICE_ID=$(cat "$DEVICE_ID_FILE")
    echo -e "${DIM}Using existing device ID${NC}"
else
    # Generate new UUID
    if command -v uuidgen &>/dev/null; then
        DEVICE_ID=$(uuidgen | tr '[:upper:]' '[:lower:]')
    else
        DEVICE_ID=$(cat /dev/urandom | LC_ALL=C tr -dc 'a-f0-9' | fold -w 8 | head -n 1)
        DEVICE_ID="${DEVICE_ID}-$(cat /dev/urandom | LC_ALL=C tr -dc 'a-f0-9' | fold -w 4 | head -n 1)"
        DEVICE_ID="${DEVICE_ID}-$(cat /dev/urandom | LC_ALL=C tr -dc 'a-f0-9' | fold -w 4 | head -n 1)"
        DEVICE_ID="${DEVICE_ID}-$(cat /dev/urandom | LC_ALL=C tr -dc 'a-f0-9' | fold -w 4 | head -n 1)"
        DEVICE_ID="${DEVICE_ID}-$(cat /dev/urandom | LC_ALL=C tr -dc 'a-f0-9' | fold -w 12 | head -n 1)"
    fi
    echo "$DEVICE_ID" > "$DEVICE_ID_FILE"
    echo -e "${GREEN}Generated new device ID${NC}"
fi

# Get hostname
if command -v tailscale &>/dev/null && tailscale status &>/dev/null 2>&1; then
    HOSTNAME=$(tailscale status --json 2>/dev/null | grep -o '"Self":{[^}]*"HostName":"[^"]*"' | sed 's/.*"HostName":"\([^"]*\)".*/\1/' 2>/dev/null || hostname -s)
else
    HOSTNAME=$(hostname -s)
fi

USER=$(whoami)

# Detect installed agents
AGENTS=""
command -v claude &>/dev/null && AGENTS="${AGENTS}claude,"
command -v cursor &>/dev/null && AGENTS="${AGENTS}cursor,"
command -v codex &>/dev/null && AGENTS="${AGENTS}codex,"
command -v aider &>/dev/null && AGENTS="${AGENTS}aider,"
AGENTS="${AGENTS%,}"

# Check for glyx-daemon
DAEMON_CMD=""
if command -v glyx-daemon &>/dev/null; then
    DAEMON_CMD="glyx-daemon"
elif [[ -f "$HOME/.local/bin/glyx-daemon" ]]; then
    DAEMON_CMD="$HOME/.local/bin/glyx-daemon"
elif command -v uvx &>/dev/null; then
    DAEMON_CMD="uvx --from glyx-mcp glyx-daemon"
elif command -v pipx &>/dev/null; then
    DAEMON_CMD="pipx run glyx-mcp glyx-daemon"
fi

# Start daemon in background if available
DAEMON_RUNNING=false
if [[ -n "$DAEMON_CMD" ]]; then
    # Kill existing daemon if running
    if [[ -f "$DAEMON_PID_FILE" ]]; then
        OLD_PID=$(cat "$DAEMON_PID_FILE")
        kill "$OLD_PID" 2>/dev/null || true
        rm -f "$DAEMON_PID_FILE"
    fi

    # Start daemon
    echo -e "${DIM}Starting daemon...${NC}"
    GLYX_DEVICE_ID="$DEVICE_ID" GLYX_API_URL="$GLYX_API_URL" \
        $DAEMON_CMD --device-id "$DEVICE_ID" > "$DAEMON_LOG_FILE" 2>&1 &
    DAEMON_PID=$!
    echo "$DAEMON_PID" > "$DAEMON_PID_FILE"

    # Give it a moment to start
    sleep 1

    if kill -0 "$DAEMON_PID" 2>/dev/null; then
        DAEMON_RUNNING=true
        echo -e "${GREEN}Daemon started (PID: $DAEMON_PID)${NC}"
    else
        echo -e "${YELLOW}Daemon failed to start. Check $DAEMON_LOG_FILE${NC}"
    fi
fi

# Build QR payload
QR_PAYLOAD="glyx://pair?device_id=${DEVICE_ID}&host=${HOSTNAME}&user=${USER}&name=${HOSTNAME}"
[[ -n "$AGENTS" ]] && QR_PAYLOAD="${QR_PAYLOAD}&agents=${AGENTS}"

# Clear screen and show header
clear
echo ""
echo -e "${BOLD}${CYAN}  ▄▄ ▄▄   ${NC}"
echo -e "${BOLD}${CYAN} █▀▀ █    █  █ █  █ ${NC}"
echo -e "${BOLD}${CYAN} █ █ █    ▀▄▄█ ▄▄▄█ ${NC}"
echo -e "${BOLD}${CYAN} ▀▀▀ ▀▀▀▀ ▀  ▀ ▀  ▀ ${NC}"
echo ""
echo -e "${DIM}Scan with the Glyx iOS app${NC}"
echo ""

# Generate QR code
if command -v qrencode &>/dev/null; then
    qrencode -t ANSIUTF8 "$QR_PAYLOAD"
elif command -v python3 &>/dev/null; then
    python3 -c "
import sys
try:
    import qrcode
    qr = qrcode.QRCode(border=1)
    qr.add_data('$QR_PAYLOAD')
    qr.print_ascii(invert=True)
except ImportError:
    print('Install qrcode: pip3 install qrcode')
    print()
    print('Manual entry URL:')
    print('$QR_PAYLOAD')
" 2>/dev/null || {
    echo -e "${RED}QR code generation requires qrencode or python3 qrcode${NC}"
    echo -e "${DIM}Install: brew install qrencode${NC}"
    echo ""
    echo -e "${CYAN}Manual entry URL:${NC}"
    echo "$QR_PAYLOAD"
}
else
    echo -e "${RED}QR code generation requires qrencode or python3${NC}"
    echo ""
    echo -e "${CYAN}Manual entry URL:${NC}"
    echo "$QR_PAYLOAD"
fi

echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BOLD}Device Details${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "  ${DIM}Device ID:${NC} ${CYAN}${DEVICE_ID}${NC}"
echo -e "  ${DIM}Host:${NC}      ${BOLD}${HOSTNAME}${NC}"
echo -e "  ${DIM}User:${NC}      ${USER}"
[[ -n "$AGENTS" ]] && echo -e "  ${DIM}Agents:${NC}    ${AGENTS}"
if $DAEMON_RUNNING; then
    echo -e "  ${DIM}Daemon:${NC}    ${GREEN}● Running${NC}"
else
    echo -e "  ${DIM}Daemon:${NC}    ${YELLOW}○ Not running${NC}"
fi
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

if $DAEMON_RUNNING; then
    echo -e "${GREEN}Ready!${NC} Scan the QR code with Glyx iOS app."
    echo -e "${DIM}Tasks will execute automatically once paired.${NC}"
else
    echo -e "${YELLOW}Daemon not found.${NC} Install with:"
    echo -e "  ${CYAN}pipx install glyx-mcp${NC}"
    echo -e "  ${DIM}or${NC}"
    echo -e "  ${CYAN}uv tool install glyx-mcp${NC}"
fi
echo ""
echo -e "${DIM}Logs: tail -f $DAEMON_LOG_FILE${NC}"
echo -e "${DIM}Press Ctrl+C to stop${NC}"

# Keep script running, tailing daemon logs
if $DAEMON_RUNNING; then
    echo ""
    echo -e "${DIM}─── Daemon Output ───${NC}"
    tail -f "$DAEMON_LOG_FILE" 2>/dev/null || while true; do sleep 1; done
else
    while true; do
        sleep 1
    done
fi
'''
