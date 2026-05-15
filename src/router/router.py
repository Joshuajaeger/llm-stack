import os


MLX_URL = os.environ.get("MLX_URL", "http://127.0.0.1:8001/generate")
LLAMA_URL = os.environ.get("LLAMA_URL", "http://127.0.0.1:8002/completion")
LLAMA_PORT = 8002
