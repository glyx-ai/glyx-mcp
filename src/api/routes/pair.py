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
        curl -sL glyx.dev/pair | sh

    The script will:
    1. Generate a unique pairing code
    2. Start the glyx daemon (relay server)
    3. Display a QR code for the iOS app to scan
    """
    return PAIR_SCRIPT


PAIR_SCRIPT = r'''#!/bin/bash
# Glyx Device Pairing Script
# Usage: curl -sL glyx.dev/pair | sh

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color
BOLD='\033[1m'

# Generate pairing code (6 alphanumeric characters)
PAIRING_CODE=$(cat /dev/urandom | LC_ALL=C tr -dc 'A-Z0-9' | fold -w 6 | head -n 1)
HOSTNAME=$(hostname)
LOCAL_IP=$(ipconfig getifaddr en0 2>/dev/null || hostname -I 2>/dev/null | awk '{print $1}' || echo "localhost")
RELAY_PORT=8765
RELAY_URL="ws://${HOSTNAME}.local:${RELAY_PORT}"

echo ""
echo -e "${PURPLE}${BOLD}╔═══════════════════════════════════════════════════════════╗${NC}"
echo -e "${PURPLE}${BOLD}║                      GLYX PAIRING                         ║${NC}"
echo -e "${PURPLE}${BOLD}╚═══════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${CYAN}Hostname:${NC}     $HOSTNAME"
echo -e "${CYAN}Local IP:${NC}     $LOCAL_IP"
echo -e "${CYAN}Relay Port:${NC}   $RELAY_PORT"
echo ""

# Check if glyx daemon is installed
if ! command -v glyx-daemon &> /dev/null; then
    echo -e "${YELLOW}Installing glyx daemon...${NC}"

    # Check if pipx is available
    if command -v pipx &> /dev/null; then
        pipx install glyx-daemon 2>/dev/null || pip install --user glyx-daemon
    elif command -v pip &> /dev/null; then
        pip install --user glyx-daemon
    elif command -v pip3 &> /dev/null; then
        pip3 install --user glyx-daemon
    else
        echo -e "${RED}Error: pip not found. Please install Python and pip first.${NC}"
        exit 1
    fi
fi

# Generate QR code payload
QR_PAYLOAD="glyx://pair?code=${PAIRING_CODE}&relay=${RELAY_URL}&name=${HOSTNAME}"

echo -e "${GREEN}${BOLD}Scan this QR code with the Glyx app:${NC}"
echo ""

# Try to generate QR code
if command -v qrencode &> /dev/null; then
    qrencode -t ANSIUTF8 "$QR_PAYLOAD"
elif command -v python3 &> /dev/null; then
    python3 -c "
import sys
try:
    import qrcode
    qr = qrcode.QRCode(border=1)
    qr.add_data('$QR_PAYLOAD')
    qr.print_ascii(invert=True)
except ImportError:
    # Fallback: simple text-based QR representation
    print('QR code libraries not installed.')
    print('Install with: pip install qrcode')
    print()
    print('Or manually enter this URL in the app:')
    print('$QR_PAYLOAD')
"
else
    echo "QR code generation not available."
    echo ""
    echo -e "${YELLOW}Manual pairing info:${NC}"
fi

echo ""
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BOLD}Pairing Code:${NC}  ${GREEN}${BOLD}$PAIRING_CODE${NC}"
echo -e "${BOLD}Relay URL:${NC}     ${BLUE}$RELAY_URL${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "${YELLOW}Waiting for connection from Glyx app...${NC}"
echo -e "${CYAN}Press Ctrl+C to cancel${NC}"
echo ""

# Start the daemon with the pairing code
# The daemon will handle the WebSocket connection and tool execution
if command -v glyx-daemon &> /dev/null; then
    exec glyx-daemon --port $RELAY_PORT --code "$PAIRING_CODE"
else
    # Fallback: Simple WebSocket echo server using Python
    python3 << 'DAEMON_SCRIPT'
import asyncio
import json
import os
import subprocess
import sys

try:
    import websockets
except ImportError:
    print("Installing websockets...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "websockets", "-q"])
    import websockets

PAIRING_CODE = os.environ.get("PAIRING_CODE", "")
PORT = int(os.environ.get("RELAY_PORT", 8765))

connected_clients = set()

async def handle_client(websocket):
    """Handle incoming WebSocket connections."""
    # Check pairing code from query params
    path = websocket.path
    if f"code={PAIRING_CODE}" not in path and PAIRING_CODE:
        await websocket.close(4001, "Invalid pairing code")
        return

    connected_clients.add(websocket)
    print(f"\033[0;32m✓ Client connected!\033[0m")

    # Send device info
    import platform
    device_info = {
        "type": "device_info",
        "hostname": os.uname().nodename,
        "os": f"{platform.system()} {platform.release()}",
        "workingDirectory": os.getcwd(),
        "username": os.getenv("USER", "unknown")
    }
    await websocket.send(json.dumps(device_info))

    try:
        async for message in websocket:
            data = json.loads(message)

            if data.get("type") == "tool_call":
                tool_name = data.get("name")
                tool_input = data.get("input", {})
                call_id = data.get("id")

                result = await execute_tool(tool_name, tool_input)

                response = {
                    "type": "tool_result",
                    "id": call_id,
                    "result": result
                }
                await websocket.send(json.dumps(response))
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        connected_clients.discard(websocket)
        print(f"\033[0;33m⚠ Client disconnected\033[0m")

async def execute_tool(name: str, input_data: dict) -> dict:
    """Execute a tool and return the result."""
    try:
        if name == "run_command":
            cmd = input_data.get("command", "")
            cwd = input_data.get("cwd", os.getcwd())

            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd
            )
            stdout, stderr = await proc.communicate()

            return {
                "success": proc.returncode == 0,
                "stdout": stdout.decode(),
                "stderr": stderr.decode(),
                "exit_code": proc.returncode
            }

        elif name == "read_file":
            path = input_data.get("path", "")
            with open(os.path.expanduser(path), "r") as f:
                content = f.read()
            return {"success": True, "content": content}

        elif name == "write_file":
            path = input_data.get("path", "")
            content = input_data.get("content", "")
            with open(os.path.expanduser(path), "w") as f:
                f.write(content)
            return {"success": True}

        elif name == "list_files":
            path = input_data.get("path", ".")
            files = os.listdir(os.path.expanduser(path))
            return {"success": True, "files": files}

        else:
            return {"success": False, "error": f"Unknown tool: {name}"}

    except Exception as e:
        return {"success": False, "error": str(e)}

async def main():
    print(f"\033[0;32m✓ Daemon ready on port {PORT}\033[0m")
    async with websockets.serve(handle_client, "0.0.0.0", PORT):
        await asyncio.Future()  # Run forever

if __name__ == "__main__":
    os.environ["PAIRING_CODE"] = os.environ.get("PAIRING_CODE", "''' + '${PAIRING_CODE}' + r'''")
    os.environ["RELAY_PORT"] = str(''' + '${RELAY_PORT}' + r''')
    asyncio.run(main())
DAEMON_SCRIPT
fi
'''
