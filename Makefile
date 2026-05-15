.PHONY: install mlx router webui llama all help

install:
	bash install.sh

mlx:
	source .venv/bin/activate && bash scripts/start_mlx.sh

llama:
	source .venv/bin/activate && bash scripts/start_llama.sh

router:
	source .venv/bin/activate && bash scripts/start_router.sh

webui:
	bash scripts/start_webui.sh

help:
	@echo "Targets:"
	@echo "  make install   — clone, venv, install deps, download model"
	@echo "  make mlx       — start MLX fast inference server (port 8001)"
	@echo "  make llama     — start llama.cpp server (port 8002)"
	@echo "  make router    — start orchestrator router (port 8000)"
	@echo "  make webui     — start Open WebUI (port 8080)"