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

```bash
# Create venv
python3 -m venv .venv
source .venv/bin/activate

# Install
pip install -r requirements.txt

# 1. Start MLX server (fast inference)
bash scripts/start_mlx.sh

# 2. Start llama.cpp server (structured output)
bash scripts/start_llama.sh

# 3. Start router
bash scripts/start_router.sh

# 4. Start Open WebUI
bash scripts/start_webui.sh
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
