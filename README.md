<p align="center">
  <img src="https://img.shields.io/badge/glyx-mcp-7C3AED?style=for-the-badge&logoColor=white" alt="glyx-mcp" />
</p>

<h1 align="center">glyx-mcp</h1>

<p align="center">
  <strong>The backend that powers <a href="https://glyx.ai">Glyx</a> — a mobile DevOps command center for your iPhone.</strong>
</p>

<p align="center">
  Control AI coding agents, execute commands, and manage your dev machines from anywhere.
</p>

<p align="center">
  <a href="https://github.com/glyx-ai/glyx-mcp/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/glyx-ai/glyx-mcp/ci.yml?branch=main&style=flat-square&label=CI" alt="CI" /></a>
  <a href="https://github.com/glyx-ai/glyx-mcp/actions/workflows/deploy.yml"><img src="https://img.shields.io/github/actions/workflow/status/glyx-ai/glyx-mcp/deploy.yml?branch=main&style=flat-square&label=Deploy" alt="Deploy" /></a>
  <img src="https://img.shields.io/badge/python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python" />
  <img src="https://img.shields.io/badge/iOS-17+-000000?style=flat-square&logo=apple&logoColor=white" alt="iOS" />
  <a href="https://github.com/glyx-ai/glyx-mcp/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-MIT-green?style=flat-square" alt="License" /></a>
</p>

---

## What is Glyx?

Glyx lets you run AI coding agents on your dev machine and control them from your phone. Think of it as a remote control for Claude Code, Cursor, Codex, and Aider — with real-time streaming, push notifications, and human-in-the-loop approvals.

**This repo** is the server that makes it all work. It runs on your machine and bridges the Glyx iOS app to your local coding agents.

## How it works

```
┌──────────────┐       ┌──────────────────┐       ┌──────────────┐
│              │       │                  │       │              │
│   Glyx iOS   │◄─────►│    Supabase      │◄─────►│  glyx-mcp    │
│   (phone)    │       │   (Realtime)     │       │  (your Mac)  │
│              │       │                  │       │              │
└──────────────┘       └──────────────────┘       └──────┬───────┘
                                                         │
                                                         ▼
                                                  ┌──────────────┐
                                                  │ Claude Code  │
                                                  │ Cursor       │
                                                  │ Codex        │
                                                  │ Aider        │
                                                  └──────────────┘
```

1. You dispatch a task from the iOS app
2. The task lands in Supabase
3. Your local glyx-mcp executor picks it up and runs the agent
4. Output streams back to your phone in real-time
5. If the agent needs input, you get a push notification

## Quick start

One command. That's it.

```bash
curl -sL glyx.ai/pair | bash
```

This will:
- Install [uv](https://github.com/astral-sh/uv) if needed
- Clone this repo to `~/.glyx/glyx-mcp`
- Install dependencies
- Show a QR code — scan it with the Glyx iOS app to pair

<details>
<summary>What the pairing screen looks like</summary>

```
   ██████╗ ██╗  ██╗   ██╗██╗  ██╗
  ██╔════╝ ██║  ╚██╗ ██╔╝╚██╗██╔╝
  ██║  ███╗██║   ╚████╔╝  ╚███╔╝
  ██║   ██║██║    ╚██╔╝   ██╔██╗
  ╚██████╔╝██████╗ ██║   ██╔╝ ██╗
   ╚═════╝ ╚═════╝ ╚═╝   ╚═╝  ╚═╝

  ╭──────── Scan with Glyx iOS ────────╮
  │                                    │
  │         ████████████████           │
  │         ██ QR CODE  ██             │
  │         ████████████████           │
  │                                    │
  ╰──── Point your camera at this ─────╯

  Device   MacBook-Pro (you)
  IP       192.168.1.5:8000
  Agents   claude  cursor  codex
```

Rendered with [Rich](https://github.com/Textualize/rich) + [segno](https://github.com/heuer/segno) for a polished terminal experience.
</details>

## Features

| Feature | Description |
|---------|-------------|
| **Agent dispatch** | Run Claude Code, Cursor, Codex, or Aider from your phone |
| **Real-time streaming** | See agent output as it happens via Supabase Realtime |
| **Human-in-the-loop** | Agents can ask you questions — respond inline with a countdown timer |
| **Push notifications** | Get notified when agents need input or finish (via [Knock](https://knock.app)) |
| **QR pairing** | One scan to connect your phone to your machine |
| **Token provisioning** | iOS sends your auth session to the local server — no API keys on disk |
| **Auto-detection** | Discovers which agents you have installed (claude, cursor, codex, aider) |

## Architecture

The project has two roles:

### Cloud API (deployed to Google Cloud Run)

REST API that the iOS app talks to. Handles auth, task management, HITL requests, webhooks, and serves the pairing script.

```
src/api/
  routes/         # FastAPI endpoints (auth, tasks, HITL, devices, pair, etc.)
  webhooks/       # GitHub + Linear webhook handlers
  integrations/   # Claude Code, Linear integrations
  session.py      # Token provisioning + session management
  server.py       # Combined FastAPI + FastMCP server
```

### Local executor (runs on your machine)

Subscribes to Supabase Realtime, picks up tasks assigned to your device, and executes them using local coding agents.

```
src/api/local_executor.py    # Realtime subscriber + agent runner
src/glyx_mcp/logging.py      # Rich-powered terminal logging
scripts/pair_display.py      # Pairing screen (Rich + segno QR)
```

### Auth flow

The local executor authenticates to Supabase using **your** session tokens (not a service role key). During QR pairing, the iOS app provisions tokens to your local server:

```
iOS scans QR → POST /api/auth/provision → tokens stored in ~/.glyx/session (0600)
```

Tokens auto-refresh every 50 minutes.

## Development

```bash
# Clone
git clone https://github.com/glyx-ai/glyx-mcp.git
cd glyx-mcp

# Install
uv sync --extra dev

# Run locally
uv run task dev

# Lint + type check
uv run task lint

# Tests
uv run task test
```

### Environment

Copy `.env.example` to `.env`. The key variables:

| Variable | Required | Description |
|----------|----------|-------------|
| `SUPABASE_URL` | Yes | Supabase project URL |
| `SUPABASE_ANON_KEY` | Yes | Supabase publishable key |
| `SUPABASE_SERVICE_ROLE_KEY` | Dev only | For local development without iOS pairing |
| `KNOCK_API_KEY` | Optional | Push notifications via Knock |
| `LOGFIRE_TOKEN` | Optional | Observability via Logfire |

## Deployment

Pushing to `main` auto-deploys to Google Cloud Run via GitHub Actions + Terraform.

```bash
# Manual deploy
uv run task deploy
```

Infrastructure is defined in `infra/` (Terraform).

## Project structure

```
glyx-mcp/
├── src/
│   ├── api/                  # FastAPI server + routes
│   │   ├── routes/           # REST endpoints
│   │   ├── webhooks/         # GitHub, Linear webhooks
│   │   ├── integrations/     # Agent integrations
│   │   ├── session.py        # Auth + token management
│   │   ├── local_executor.py # Realtime task executor
│   │   └── server.py         # App entrypoint
│   ├── glyx_mcp/             # MCP protocol server
│   ├── python-sdk/           # Glyx Python SDK
│   └── framework/            # Agent framework
├── scripts/                  # Dev tools + pairing display
├── infra/                    # Terraform (GCP)
├── supabase/                 # Migrations
└── tests/                    # pytest suite
```

## Related projects

| Project | Description |
|---------|-------------|
| [glyx-ios](https://github.com/glyx-ai/glyx-ios) | iOS app (Swift/SwiftUI) |
| [glyx](https://github.com/glyx-ai/glyx) | Web frontend (Next.js) at [glyx.ai](https://glyx.ai) |

## License

MIT
