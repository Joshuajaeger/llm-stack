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

Run each long-running command in a separate terminal tab/window.

**Use from iPhone on the same Wi-Fi:**

```bash
# Terminal 1
make mlx

# Terminal 2
make router

# Terminal 3
make webui

# Get the Mac IP address
make ip
```

Then open this from Safari on iPhone:

```text
http://<your-mac-ip>:8080
```

Open WebUI is configured to use the local router at `http://127.0.0.1:8000/v1` with API key `secret123` by default.

The installer automatically chooses an MLX model for the Mac it runs on. It queries Hugging Face for current `mlx-community` text-generation chat/instruct models, filters for 4-bit local models, matches the model size to system RAM, and saves the selected model to `.env`.

Override automatic selection anytime:

```bash
MODEL_ID="mlx-community/Your-Model-Here" bash <(curl -s https://raw.githubusercontent.com/Joshuajaeger/llm-stack/main/install.sh)
```

## Project Structure

```
├── src/
│   ├── mlx_server/         # MLX inference server
│   │   ├── __init__.py
│   │   └── server.py
│   ├── model_selector.py   # Dynamic Hugging Face model selector
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

Model selection is dynamic by default:

- 8 GB RAM: up to about 1.5B parameters
- 16 GB RAM: up to about 3B parameters
- 24 GB RAM: up to about 7B parameters
- 48 GB RAM: up to about 14B parameters
- 64+ GB RAM: up to about 32B parameters

Override with `MODEL_ID` if you want a specific MLX model.
