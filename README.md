# LLM Stack

Run a local ChatGPT-style app on your Mac and use it from your iPhone on the same Wi-Fi.

This project is made for Apple Silicon Macs. It uses MLX so the model can run fast on your Mac instead of in the cloud.

## Explain Like I'm 5

Think of this like a little local AI machine with three parts:

- **MLX** is the engine. It does the actual AI thinking on your Mac.
- **Router** is the traffic helper. It receives chat requests and sends them to the right place.
- **Open WebUI** is the website. You open it in a browser and chat with the AI.

Your Mac runs the AI. Your iPhone is just the screen you use to talk to it.

## What You Need

- An Apple Silicon Mac: M1, M2, M3, M4, or newer.
- macOS.
- Python 3.
- Git.
- Same Wi-Fi if you want to use it from your iPhone.

## Install

Run this in Terminal:

```bash
bash <(curl -s https://raw.githubusercontent.com/Joshuajaeger/llm-stack/main/install.sh)
```

The installer will:

- Download this project.
- Create a Python environment.
- Install the needed packages.
- Pick a good AI model for your Mac automatically.
- Download that model.

## Start Everything

After install, run:

```bash
cd ~/llm-stack
source .venv/bin/activate
source .env
make up
```

That starts everything in the background.

Open the app on your Mac:

```text
http://127.0.0.1:8080
```

## Use From iPhone

First get your Mac's Wi-Fi address:

```bash
make ip
```

It will print something like:

```text
192.168.1.42
```

On your iPhone, open Safari and go to:

```text
http://192.168.1.42:8080
```

Use the number from your Mac, not the example above.

Your iPhone and Mac must be on the same Wi-Fi.

## Stop Everything

```bash
make down
```

## Useful Commands

```bash
make up        # Start the local AI stack
make down      # Stop everything
make status    # Show what is running
make logs      # Watch logs
make ip        # Show your Mac Wi-Fi IP address
make help      # Show commands
```

## Model Selection

The project automatically chooses a model based on your Mac.

Rough idea:

- 8 GB RAM gets a smaller model.
- 16 GB RAM gets a better small model.
- 24 GB RAM gets a stronger model.
- 48 GB or more can run larger models.

The selector checks Hugging Face for current MLX chat models, then picks one that should fit your Mac.

If you want to force a specific model:

```bash
MODEL_ID="mlx-community/Your-Model-Here" bash <(curl -s https://raw.githubusercontent.com/Joshuajaeger/llm-stack/main/install.sh)
```

## Why Not Docker?

Docker is useful for many apps, but it is not the best choice for MLX on macOS.

MLX needs Apple Metal acceleration to be fast. Docker Desktop on Mac does not give Linux containers normal direct access to Apple Metal.

So this project runs natively on macOS and uses `make up` like a simple Docker Compose-style command.

## Troubleshooting

If the website does not open on iPhone:

- Make sure Mac and iPhone are on the same Wi-Fi.
- Run `make status` to check that services are running.
- Run `make ip` again and use that exact IP.
- If macOS asks about network access, click Allow.
- Try opening `http://127.0.0.1:8080` on the Mac first.

If install fails while downloading the model:

- Run the install command again.
- Hugging Face may rate-limit anonymous downloads.
- Setting a Hugging Face token can improve download reliability.

## Advanced Pieces

Ports used by default:

- MLX server: `8001`
- Router: `8000`
- Open WebUI: `8080`

Open WebUI talks to the router here:

```text
http://127.0.0.1:8000/v1
```

Default API key:

```text
secret123
```

## Project Layout

```text
src/mlx_server/       AI engine server
src/router/           Router API
src/model_selector.py Automatic model picker
scripts/              Start and stop scripts
grammar/              llama.cpp grammar files
config/               Example config
Procfile              Process list
Makefile              Easy commands
```
