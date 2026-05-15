# LLM Stack

A local LLM stack for Apple Silicon Macs.

It runs a local ChatGPT-style web app on your Mac, uses MLX for fast Apple Silicon inference, optionally uses llama.cpp for grammar-constrained structured output, and exposes the UI to other devices on your Wi-Fi such as an iPhone.

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
- Provides an Open WebUI browser interface.
- Lets you use the UI from your iPhone on the same Wi-Fi.
- Adds a FastAPI router so the frontend talks to one local API.
- Includes optional llama.cpp support for structured / JSON / grammar-constrained output.
- Avoids Docker for MLX so Apple Metal acceleration is preserved.

## Components

| Layer | Component | Port | Purpose |
|---|---:|---:|---|
| 1 | MLX Server | `8001` | Fast local inference on Apple Silicon |
| 2 | llama.cpp Server | `8002` | Optional structured output using GGUF + GBNF grammar |
| 3 | FastAPI Router | `8000` | Routes requests and exposes OpenAI-compatible endpoints |
| 4 | Open WebUI | `8080` | Chat UI, users, browser access, iPhone access |

## Install

```bash
bash <(curl -s https://raw.githubusercontent.com/Joshuajaeger/llm-stack/main/install.sh)
```

The installer clones the repo, creates `.venv`, installs Python packages, picks an MLX model, downloads it, and saves the selected model to `.env`.

## Start The Default Stack

```bash
cd ~/llm-stack
source .venv/bin/activate
source .env
make up
```

This starts the native macOS stack in the background:

- MLX server
- FastAPI router
- Open WebUI

Open the UI on the Mac:

```text
http://127.0.0.1:8080
```

## Use From iPhone

Make sure your Mac and iPhone are on the same Wi-Fi.

Get your Mac's Wi-Fi IP:

```bash
make ip
```

Open this on your iPhone, replacing the IP with your Mac's actual IP:

```text
http://192.168.1.42:8080
```

If macOS asks for network permission, allow it.

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
make ip        # Show your Mac Wi-Fi IP address
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

Open WebUI is configured to talk to the router using an OpenAI-compatible API:

```text
http://127.0.0.1:8000/v1
```

Default API key:

```text
secret123
```

The router exposes:

- `GET /v1/models`
- `POST /v1/chat/completions`
- `POST /chat`

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

If the iPhone cannot open the UI:

- Confirm Mac and iPhone are on the same Wi-Fi.
- Run `make status` and make sure services are running.
- Run `make ip` again and use that exact IP.
- Try `http://127.0.0.1:8080` on the Mac first.
- Allow incoming network access if macOS asks.

If model download fails:

- Run the install command again.
- Hugging Face may rate-limit anonymous downloads.
- Set a Hugging Face token if you need more reliable downloads.

If llama.cpp does not start:

- Confirm `llama-server` is installed with `brew install llama.cpp`.
- Confirm your GGUF model exists at `models/model.gguf` or set `LLAMA_MODEL`.
- Check logs with `make logs` if running as part of a custom process setup.
