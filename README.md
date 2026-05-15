# LLM Stack

A local LLM inference stack with heterogeneous backend routing.

## Architecture

```
┌─────────────────────────────────────┐
│          Open WebUI                 │
│   (auth, chat UI, remote access)    │
└────────────┬────────────────────────┘
             │ HTTP
┌────────────┴────────────────────────┐
│   Router (FastAPI orchestrator)     │
│   - routes /chat to mlx or llama   │
│   - auth middleware                 │
│   - streaming proxy                │
└────────────┬────────────────────────┘
             │ HTTP
     ┌───────┴────────┐
     │                │
┌────▼────┐    ┌──────▼──────┐
│  MLX    │    │  llama.cpp  │
│ (fast)  │    │ (structured)│
└─────────┘    └─────────────┘
```

## Quick Start

**One-liner install:**
```bash
bash <(curl -s https://raw.githubusercontent.com/Joshuajaeger/llm-stack/main/install.sh)
```

Or manually:
```bash
git clone https://github.com/Joshuajaeger/llm-stack.git
cd llm-stack
make install    # venv + pip + model download
```

**Start the stack:**
```bash
cd llm-stack && source .venv/bin/activate
make mlx       # Layer 1: fast inference (port 8001)
make router    # Layer 3: orchestrator (port 8000)
```

## Project Structure

```
├── src/
│   ├── mlx_server/         # MLX inference server
│   │   ├── __init__.py
│   │   └── server.py
│   ├── llama_cpp_server/   # llama.cpp config
│   │   ├── __init__.py
│   │   └── config.py
│   └── router/             # Python orchestrator
│       ├── __init__.py
│       ├── main.py
│       ├── auth.py
│       └── router.py
├── grammar/                # GBNF grammar files
│   └── json.gbnf
├── config/                 # Runtime config
│   └── default.yaml
├── scripts/                # Launch scripts
│   ├── start_mlx.sh
│   ├── start_llama.sh
│   ├── start_router.sh
│   └── start_webui.sh
├── requirements.txt
├── .gitignore
└── README.md
```

## Layers

| Layer | Backend | Port | Purpose |
|-------|---------|------|---------|
| 1 | MLX | 8001 | Fast chat inference (Apple Silicon) |
| 2 | llama.cpp | 8002 | Structured / grammar-constrained output |
| 3 | Router | 8000 | Request routing + auth |
| 4 | Open WebUI | 8080 | Frontend + user management |

## Models

Default models (override with env vars):

- `MODEL_ID` — MLX model (`mlx-community/Qwen2.5-1.5B-Instruct`)
