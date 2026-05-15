.PHONY: install up down status logs mlx router webui llama ip help

install:
	bash install.sh

up:
	bash scripts/stack_up.sh

down:
	bash scripts/stack_down.sh

status:
	bash scripts/stack_status.sh

logs:
	bash scripts/stack_logs.sh

mlx:
	source .venv/bin/activate && bash scripts/start_mlx.sh

llama:
	source .venv/bin/activate && bash scripts/start_llama.sh

router:
	source .venv/bin/activate && bash scripts/start_router.sh

webui:
	source .venv/bin/activate && bash scripts/start_webui.sh

ip:
	@ipconfig getifaddr en0 || ipconfig getifaddr en1

help:
	@echo "Targets:"
	@echo "  make install   — clone, venv, install deps, download model"
	@echo "  make up        — start MLX, router, and Open WebUI in background"
	@echo "  make down      — stop background stack"
	@echo "  make status    — show service status"
	@echo "  make logs      — follow service logs"
	@echo "  make mlx       — start MLX fast inference server (port 8001)"
	@echo "  make llama     — start llama.cpp server (port 8002)"
	@echo "  make router    — start orchestrator router (port 8000)"
	@echo "  make webui     — start Open WebUI (port 8080)"
	@echo "  make ip        — show your Mac Wi-Fi IP address"
