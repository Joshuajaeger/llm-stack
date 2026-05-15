# LLM Stack

A local LLM stack for Apple Silicon Macs.

It runs a ChatGPT-style web app on your Mac, uses MLX for fast Apple Silicon inference, optionally uses llama.cpp for grammar-constrained structured output, and can be exposed to other people through a private Tailscale network with admin-approved accounts.

## Architecture

```text
            ┌────────────────────────────┐
            │        Open WebUI          │
            │  browser UI + user login   │
            └────────────┬───────────────┘
                         │ HTTP
            ┌────────────▼───────────────┐
            │     FastAPI Router         │
            │  OpenAI-compatible API     │
            │  backend routing + auth    │
            └────────────┬───────────────┘
                         │ HTTP
        ┌────────────────┴────────────────┐
        │                                 │
┌───────▼────────┐              ┌─────────▼────────┐
│   MLX Server   │              │   llama.cpp API  │
│ fast chat      │              │ JSON / grammar   │
│ Apple Metal    │              │ structured output│
└────────────────┘              └──────────────────┘
```

## What This Does

- Runs local LLM inference on your Mac with MLX.
- Automatically chooses a model that should fit your Mac.
- Provides an Open WebUI browser interface with accounts.
- Supports remote access through Tailscale with admin approval per user.
- Adds a FastAPI router so the frontend talks to one local API.
- Includes optional llama.cpp support for structured / JSON / grammar-constrained output.
- Avoids Docker for MLX so Apple Metal acceleration is preserved.

## Components

| Layer | Component | Port | Purpose |
|---|---:|---:|---|
| 1 | MLX Server | `8001` | Fast local inference on Apple Silicon |
| 2 | llama.cpp Server | `8002` | Optional structured output using GGUF + GBNF grammar |
| 3 | FastAPI Router | `8000` | Routes requests and exposes OpenAI-compatible endpoints |
| 4 | Open WebUI | `8080` | Chat UI, users, accounts, admin approval |

## Install

```bash
bash <(curl -s https://raw.githubusercontent.com/Joshuajaeger/llm-stack/main/install.sh)
```

The installer clones the repo, creates `.venv`, installs Python packages, picks an MLX model, downloads it, and generates per-install secrets (`API_KEY`, `WEBUI_SECRET_KEY`) into a chmod-600 `.env`.

Prefer to inspect before running:

```bash
git clone https://github.com/Joshuajaeger/llm-stack.git
cd llm-stack
make install
```

## Start The Stack

```bash
cd ~/llm-stack
source .venv/bin/activate
source .env
make up
```

This starts MLX, the router, and Open WebUI in the background.

Open the UI on the Mac:

```text
http://127.0.0.1:8080
```

The very first account you create becomes the admin.

## Remote Access

The stack supports four deployment modes, set via `DEPLOY_MODE` in `.env`:

| Mode | Bind | Use Case |
|---|---|---|
| `local` (default) | `127.0.0.1` | Mac only, no remote access |
| `tailscale` | Tailscale IP | Private mesh, recommended for remote |
| `lan` | `0.0.0.0` | Anyone on your Wi-Fi/Ethernet |
| `public` | `0.0.0.0` | Only behind TLS reverse proxy |

### Recommended: Tailscale

[Tailscale](https://tailscale.com) gives you a private encrypted network. Only people you invite can reach the Mac, from anywhere in the world, without port forwarding.

1. Install Tailscale on the Mac and run `tailscale up`.
2. Edit `.env` and set:

   ```bash
   export DEPLOY_MODE="tailscale"
   ```

3. Restart the stack:

   ```bash
   make down
   make up
   ```

4. Get the shareable URL:

   ```bash
   make tailscale
   ```

   This prints both the IPv4 and MagicDNS URLs.

5. Invite users to your tailnet from the [Tailscale admin console](https://login.tailscale.com/admin/users). Once they accept and install Tailscale, they can reach your Open WebUI URL from any network they're on.

### How New Users Get Access

The stack is configured for self-service signup with admin approval:

1. A new user opens your Open WebUI URL.
2. They click "Sign up" and create an account.
3. Their account is created in `pending` state — they cannot use the chat yet.
4. You log in as admin, go to **Admin Panel → Users**, and switch their role from `pending` to `user`.
5. They can now sign in and use the LLM.

This is enforced by these Open WebUI environment variables, set in `scripts/start_webui.sh`:

```text
WEBUI_AUTH=True
ENABLE_SIGNUP=True
DEFAULT_USER_ROLE=pending
```

To disable signups entirely (admin-creates-users-only mode):

```bash
export ENABLE_SIGNUP=False
```

## Useful Commands

```bash
make up        # Start MLX, router, and Open WebUI in the background
make down      # Stop the background stack
make status    # Show which services are running
make logs      # Follow all service logs
make mlx       # Run only the MLX server in the foreground
make router    # Run only the router in the foreground
make webui     # Run only Open WebUI in the foreground
make llama     # Run llama.cpp server in the foreground
make ip        # Show your local network IP
make tailscale # Show Tailscale URL for sharing
make help      # Show available commands
```

## Where Is llama.cpp?

llama.cpp is the optional structured-output layer.

This repo includes the integration pieces:

- `scripts/start_llama.sh` starts a `llama-server` process.
- `grammar/json.gbnf` provides a JSON grammar file.
- `src/router/router.py` defines `LLAMA_URL` as `http://127.0.0.1:8002/completion`.
- `src/router/main.py` routes structured prompts to llama.cpp when enabled.

This repo does not vendor llama.cpp itself and does not include GGUF model files. llama.cpp is an external binary and GGUF models are usually large.

Install llama.cpp with Homebrew:

```bash
brew install llama.cpp
```

Place a GGUF model here:

```text
~/llm-stack/models/model.gguf
```

Or point to another GGUF file:

```bash
export LLAMA_MODEL="/path/to/model.gguf"
```

Then run:

```bash
make llama
```

By default, `make up` starts MLX, router, and Open WebUI. Start llama.cpp separately when you want the structured-output backend active.

## Routing Decision Tree

The user does not need to choose MLX or llama.cpp manually. Open WebUI talks to one API, and the router decides internally.

```text
Incoming prompt
      │
      ▼
Did caller force a backend?
      │
      ├── yes: use requested backend
      │
      ▼
Does the prompt strongly request JSON, schema, grammar, or strict machine-readable output?
      │
      ├── yes: try llama.cpp
      │
      └── no: use MLX
              
If llama.cpp was selected but is not running:
      │
      ├── forced llama.cpp: return an error
      └── automatic choice: fall back to MLX
```

Default behavior:

- Normal chat, writing, summarizing, brainstorming, and explanation prompts go to MLX.
- JSON, schema, grammar, extraction, parsing, and strict-format prompts go to llama.cpp when available.
- If llama.cpp is unavailable and the request was not explicitly forced, the router falls back to MLX.

The decision logic lives in:

```text
src/router/decision.py
```

There is also a debug endpoint for checking routing decisions:

```text
POST /route
```

## Model Selection

The MLX model is selected dynamically.

The selector checks Hugging Face for current `mlx-community` chat/instruct text-generation models, filters for local-friendly 4-bit models, estimates what your Mac can handle from system RAM, and picks a suitable model.

Rough guide:

| Mac RAM | Typical Model Size |
|---:|---:|
| 8 GB | up to about 1.5B |
| 16 GB | up to about 3B |
| 24 GB | up to about 7B |
| 48 GB | up to about 14B |
| 64+ GB | up to about 32B |

Force a specific MLX model:

```bash
MODEL_ID="mlx-community/Your-Model-Here" bash <(curl -s https://raw.githubusercontent.com/Joshuajaeger/llm-stack/main/install.sh)
```

## Open WebUI Configuration

Open WebUI talks to the router using an OpenAI-compatible API:

```text
http://127.0.0.1:8000/v1
```

The API key is generated per-install and stored in `.env` (`API_KEY`). It is never `secret123` and never committed to the repo.

The router exposes:

- `GET /v1/models`
- `POST /v1/chat/completions`
- `POST /chat`
- `POST /route`  (debug: shows backend decision)

## Security

The defaults are local-only. Remote access is opt-in via `DEPLOY_MODE`.

What the stack does for you:

- The router only listens on `127.0.0.1`. It is not reachable from any other host.
- The MLX server listens on `127.0.0.1` and refuses non-loopback clients at the middleware level (defense in depth).
- Open WebUI binds to `127.0.0.1` by default. To expose it, you must explicitly set `DEPLOY_MODE` to `tailscale`, `lan`, or `public`.
- `install.sh` generates two strong random secrets per install: `API_KEY` (router) and `WEBUI_SECRET_KEY` (Open WebUI JWT signing). Both go into `.env` with `chmod 600`.
- Open WebUI is configured with `WEBUI_AUTH=True`, `ENABLE_SIGNUP=True`, `DEFAULT_USER_ROLE=pending` — new accounts cannot use the LLM until an admin promotes them.
- The router uses constant-time API key comparison (`hmac.compare_digest`).
- CORS on the router is restricted to `http://127.0.0.1:8080` and `http://localhost:8080`.
- Requests are length-capped: `MAX_PROMPT_CHARS=20000`, `MAX_TOKENS_CAP=2048` (configurable via env).

What you should still do:

- Never commit `.env` or `logs/`. They are in `.gitignore`.
- Prefer Tailscale over port-forwarding. A public-internet-exposed Open WebUI is a permanent target — at minimum, you must run TLS via Caddy or nginx in front of it.
- For invited users: send them a Tailscale invite link, not your raw IP. Tailscale handles network-level auth; Open WebUI handles application-level auth.
- Treat `logs/*.log` as containing chat history. Rotate or delete as needed.
- Do not put secrets in `config/default.yaml`. Use `.env`.

## Why Not Docker?

Docker is useful for many projects, but it is not ideal for MLX on macOS.

MLX is fast because it uses Apple Metal directly. Docker Desktop on macOS does not provide normal direct Apple Metal acceleration to Linux containers, so containerizing MLX would remove the main performance advantage.

This project uses a native compose-style runner instead:

```bash
make up
make down
make logs
make status
```

## Project Layout

```text
src/mlx_server/          MLX inference server
src/router/              FastAPI router and OpenAI-compatible API
src/llama_cpp_server/    llama.cpp configuration helpers
src/model_selector.py    Dynamic Hugging Face MLX model selector
scripts/start_mlx.sh     Start MLX server
scripts/start_router.sh  Start router
scripts/start_webui.sh   Start Open WebUI
scripts/start_llama.sh   Start llama.cpp server
scripts/stack_up.sh      Start default stack in background
scripts/stack_down.sh    Stop background stack
grammar/json.gbnf        Example JSON grammar for llama.cpp
config/default.yaml      Example configuration
Procfile                 Process list reference
Makefile                 User-friendly commands
```

## Troubleshooting

If a remote user cannot open the UI:

- Confirm `DEPLOY_MODE` in `.env` is set (`tailscale`, `lan`, or `public`), not `local`.
- Run `make status` and make sure all services are running.
- For Tailscale: run `make tailscale` and confirm the URL. The user must be invited to your tailnet and running Tailscale on their device.
- For LAN: run `make ip` and verify the user is on the same network.
- Allow incoming network access if macOS asks.

If a new user cannot chat after signing up:

- They are in `pending` role. Open the UI as admin → Admin Panel → Users → set their role to `user`.

If model download fails:

- Run the install command again.
- Hugging Face may rate-limit anonymous downloads.
- Set a Hugging Face token if you need more reliable downloads.

If llama.cpp does not start:

- Confirm `llama-server` is installed with `brew install llama.cpp`.
- Confirm your GGUF model exists at `models/model.gguf` or set `LLAMA_MODEL`.
- Check `logs/` for details.
