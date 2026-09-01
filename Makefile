.PHONY: install up down status logs mlx router webui llama ip tailscale help \
        org org-check org-scan org-dedupe org-junk org-classify org-plan \
        org-apply org-verify org-status org-folders

# fileorg: which folders to sweep, and the label of the Mac you are selling.
ROOTS   ?= ~/Desktop ~/Documents ~/Downloads ~/Pictures ~/Movies ~/Music
OLD_MAC ?=
FILEORG := bash scripts/fileorg.sh

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

tailscale:
	@bash scripts/tailscale_info.sh

org:
	@$(FILEORG) $(ARGS)

org-check:
	@$(FILEORG) icloud-check

org-scan:
	@$(FILEORG) scan $(ROOTS)

org-dedupe:
	@$(FILEORG) dedupe --prefer "$$(hostname -s)"

org-junk:
	@$(FILEORG) junk

org-classify:
	@$(FILEORG) classify

org-plan:
	@$(FILEORG) plan

org-apply:
	@$(FILEORG) apply

org-status:
	@$(FILEORG) status

org-folders:
	@$(FILEORG) smartfolders

org-verify:
	@test -n "$(OLD_MAC)" || { echo "Set OLD_MAC to the machine label you are erasing, e.g. make org-verify OLD_MAC=old-mbp"; exit 2; }
	@$(FILEORG) verify --only-machine "$(OLD_MAC)"

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
	@echo "  make ip        — show your local network IP"
	@echo "  make tailscale — show Tailscale URL for sharing with invited users"
	@echo ""
	@echo "File organization (see docs/file-organization.md):"
	@echo "  make org-check    — report iCloud files still stranded in the cloud"
	@echo "  make org-scan     — catalog ROOTS (override: make org-scan ROOTS='~/Desktop')"
	@echo "  make org-dedupe   — find duplicate content across catalogued Macs"
	@echo "  make org-junk     — report reclaimable junk (deletes nothing)"
	@echo "  make org-classify — sort into categories using rules + the local LLM"
	@echo "  make org-plan     — write the move plan for review"
	@echo "  make org-apply    — dry run the moves (add --execute via ARGS to commit)"
	@echo "  make org-verify   — prove a Mac's files all landed (OLD_MAC=<label>)"
	@echo "  make org-folders  — generate Finder Smart Folders for the library"
	@echo "  make org-status   — summarize the catalog"
	@echo "  make org ARGS='search invoice' — any fileorg command"
