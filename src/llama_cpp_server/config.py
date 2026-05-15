import os

LLAMA_PORT = 8002
LLAMA_HOST = "127.0.0.1"
MODEL_PATH = os.environ.get("LLAMA_MODEL", "models/model.gguf")
GRAMMAR_DIR = "grammar"
