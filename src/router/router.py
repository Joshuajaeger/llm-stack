MLX_URL = "http://127.0.0.1:8001/generate"
LLAMA_URL = "http://127.0.0.1:8002/completion"
LLAMA_PORT = 8002


def is_structured(prompt: str) -> bool:
    keywords = [
        "json", "schema", "structured", "format",
        "list", "bullet", "parse", "extract",
    ]
    return any(k in prompt.lower() for k in keywords)
