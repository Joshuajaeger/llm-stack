# LLM Stack

A local, private LLM server for Apple Silicon Macs with a web UI, user accounts, and remote access via Tailscale.

You run it once on a Mac. Anyone you invite can use it from anywhere in the world over a private network. Their chats never leave your device.

## Architecture

```text
            ┌────────────────────────────┐
            │        Open WebUI          │
            │  browser UI · accounts ·   │
            │  admin approval            │
            └────────────┬───────────────┘
                         │ HTTP (loopback)
            ┌────────────▼───────────────┐
            │     FastAPI Router         │
            │  OpenAI-compatible API ·   │
            │  auth · input limits       │
            └────────────┬───────────────┘
                         │ HTTP (loopback)
            ┌────────────▼───────────────┐
            │       MLX Server           │
            │  fast inference on         │
            │  Apple Silicon (Metal)     │
            └────────────────────────────┘
```

## Quick Start

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/Joshuajaeger/llm-stack/main/install.sh)
```

This clones the repo, creates a virtualenv, installs dependencies, picks an MLX model sized to your Mac, downloads it, and writes per-install secrets to a chmod-600 `.env`.

To start:

```bash
cd ~/llm-stack
source .venv/bin/activate
source .env
make up
```

Open in your browser:

```text
http://127.0.0.1:8080
```

The first account you create becomes the admin.

## Remote Access (Tailscale)

[Tailscale](https://tailscale.com) is the recommended way to use the stack from outside your network. It builds an encrypted, private mesh — only people you invite can reach the server, from any network, with no port forwarding.

1. Install Tailscale on the Mac and run `tailscale up`.
2. Set the deployment mode:

   ```bash
   # In .env
   export DEPLOY_MODE="tailscale"
   ```

3. Restart:

   ```bash
   make down && make up
   ```

4. Get the shareable URL:

   ```bash
   make tailscale
   ```

5. Invite users from the [Tailscale admin console](https://login.tailscale.com/admin/users). They install Tailscale, accept the invite, and can then open your URL from any device.

### Deployment Modes

`DEPLOY_MODE` in `.env` controls who can reach the UI:

| Mode | Bound to | Use case |
|---|---|---|
| `local` (default) | `127.0.0.1` | Mac only |
| `tailscale` | Tailscale IP | Private mesh, recommended for remote |
| `lan` | `0.0.0.0` | Your home/office network |
| `public` | `0.0.0.0` | Only behind TLS reverse proxy (Caddy/nginx) |

## Account Approval

The stack is configured for self-service signup with admin approval.

```text
┌─────────────────────┐
│ Stranger opens URL  │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ Signs up an account │  ← created with role = pending
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ Cannot use the LLM  │
│ until you approve   │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ Admin Panel > Users │  ← you flip role: pending → user
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│ User can now chat   │
└─────────────────────┘
```

Defaults applied (in `scripts/start_webui.sh`):

```text
WEBUI_AUTH=True
ENABLE_SIGNUP=True
DEFAULT_USER_ROLE=pending
```

To disable signups entirely (you create accounts manually):

```bash
export ENABLE_SIGNUP=False
```

## How It Works

**MLX server** — A FastAPI process that loads the chosen MLX model into memory once at startup and exposes a `/generate` endpoint. MLX uses Apple Metal directly, so inference runs natively on the Apple Silicon GPU. It listens only on loopback and refuses any non-loopback caller as defense in depth.

**Model selection** — On install, `src/model_selector.py` queries the Hugging Face API for current `mlx-community` chat/instruct models, filters them to 4-bit local-friendly variants, estimates what fits in the Mac's RAM, and picks one. You can override with `MODEL_ID` to pin a specific model.

| Mac RAM | Approx. model size selected |
|---:|---:|
| 8 GB | up to ~1.5B |
| 16 GB | up to ~3B |
| 24 GB | up to ~7B |
| 48 GB | up to ~14B |
| 64+ GB | up to ~32B |

**Router** — A second FastAPI process that exposes an OpenAI-compatible API (`/v1/models`, `/v1/chat/completions`) plus a simpler `/chat` endpoint. It does API-key auth (constant-time compare), enforces input length and token caps, applies CORS, and proxies requests to the MLX server. Open WebUI is wired to talk to this router, not directly to MLX, so all auth and limits go through one place.

**Open WebUI** — The browser frontend. It handles user accounts, sessions, chat history, and admin approval. It only talks to the router, on loopback. Its bind address is controlled by `DEPLOY_MODE`.

**Process manager** — `make up` starts MLX, the router, and Open WebUI as background processes via `scripts/stack_up.sh`. Each writes a PID file under `.pids/` and logs to `logs/`. `make down` reads those PID files and stops the processes cleanly. No Docker is used because Docker Desktop on macOS cannot pass through Apple Metal to Linux containers, which would defeat the point of MLX.

## Useful Commands

```bash
make up         # Start the whole stack in the background
make down       # Stop everything
make status     # Show which services are running
make logs       # Follow service logs
make tailscale  # Show the shareable Tailscale URL
make ip         # Show your local network IP
make mlx        # Run only MLX in the foreground
make router     # Run only the router in the foreground
make webui      # Run only Open WebUI in the foreground
make help       # List all targets
```

## Configuration

Everything is configured through `.env`, which `install.sh` writes for you:

```bash
export MODEL_ID="mlx-community/..."   # MLX model on Hugging Face
export API_KEY="..."                   # Router API key (random, 32 bytes)
export WEBUI_SECRET_KEY="..."          # Open WebUI JWT key (random, 48 bytes)
export DEPLOY_MODE="local"             # local | tailscale | lan | public
```

Optional overrides (env vars):

| Variable | Default | Effect |
|---|---|---|
| `MAX_PROMPT_CHARS` | `20000` | Reject prompts longer than this |
| `MAX_TOKENS_CAP` | `2048` | Clamp `max_tokens` to this ceiling |
| `WEBUI_PORT` | `8080` | Open WebUI port |
| `ENABLE_SIGNUP` | `True` | Allow self-service signup |
| `DEFAULT_USER_ROLE` | `pending` | Role assigned to new signups |

## Security

What the stack does for you:

- The router and MLX server only listen on `127.0.0.1`. They are unreachable from anywhere else.
- Open WebUI binds to `127.0.0.1` by default. Remote access requires explicit opt-in via `DEPLOY_MODE`.
- `install.sh` generates two random secrets per install (`API_KEY`, `WEBUI_SECRET_KEY`) and writes them to `.env` with permission `600`.
- API key checks use constant-time comparison (`hmac.compare_digest`).
- Router CORS is restricted to localhost origins.
- Inputs are length-capped (`MAX_PROMPT_CHARS`, `MAX_TOKENS_CAP`).
- New user accounts cannot chat until an admin approves them.

What you should do:

- Never commit `.env` or `logs/` (already in `.gitignore`).
- Prefer Tailscale over port-forwarding. If you must go public, run TLS via Caddy or nginx in front of Open WebUI.
- Treat `logs/*.log` as chat history. Rotate or delete as needed.
- Don't put secrets in `config/default.yaml`.

## Project Layout

```text
src/mlx_server/         MLX inference server
src/router/             FastAPI router + OpenAI-compatible API
src/model_selector.py   Dynamic Hugging Face MLX model picker
scripts/                Start/stop/status/logs/tailscale helpers
config/default.yaml     Example configuration (no secrets)
.env.example            Template for .env
Makefile                User-friendly commands
Procfile                Process list reference
```

## Troubleshooting

**A remote user cannot open the UI.**
Confirm `DEPLOY_MODE` is set to something other than `local` in `.env`. Run `make status` to verify services. For Tailscale, run `make tailscale` and confirm both you and the user are signed into the same tailnet. Allow incoming network access if macOS prompts.

**A new user signed up but cannot chat.**
They are in role `pending`. Open the UI as admin → Admin Panel → Users → set role to `user`.

**Install fails with "No matching distribution found for open-webui".**
Open WebUI currently requires Python 3.11 or 3.12. The installer detects a compatible Python automatically. If none is installed, run `brew install python@3.12` and re-run the installer.

**Model download fails during install.**
Re-run install. Hugging Face may rate-limit anonymous downloads; setting a `HF_TOKEN` improves reliability.

**MLX server fails to start.**
Run `make mlx` in the foreground to see the error. Most often: out of memory because the selected model is too large. Override with a smaller `MODEL_ID` in `.env`.
