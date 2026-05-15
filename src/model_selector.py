#!/usr/bin/env python3
import json
import os
import platform
import re
import sys
import urllib.request


FALLBACKS = [
    (48, "mlx-community/Qwen2.5-14B-Instruct-4bit"),
    (24, "mlx-community/Qwen2.5-7B-Instruct-4bit"),
    (14, "mlx-community/Qwen2.5-3B-Instruct-4bit"),
    (0, "mlx-community/Qwen2.5-1.5B-Instruct-4bit"),
]


def ram_gb() -> int:
    if platform.system() == "Darwin":
        pages = os.sysconf("SC_PHYS_PAGES")
        page_size = os.sysconf("SC_PAGE_SIZE")
        return int((pages * page_size) / 1024**3)
    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    return int(int(line.split()[1]) / 1024**2)
    except FileNotFoundError:
        pass
    return 8


def max_params_for_ram(gb: int) -> float:
    if gb >= 64:
        return 32.0
    if gb >= 48:
        return 14.0
    if gb >= 24:
        return 7.0
    if gb >= 14:
        return 3.0
    return 1.5


def fallback_model(gb: int) -> str:
    for min_gb, model in FALLBACKS:
        if gb >= min_gb:
            return model
    return FALLBACKS[-1][1]


def extract_params(model_id: str) -> float | None:
    matches = re.findall(r"(?<![a-zA-Z0-9])(\d+(?:\.\d+)?)\s*[bB](?![a-zA-Z])", model_id)
    if not matches:
        return None
    return max(float(m) for m in matches)


def is_good_chat_model(model: dict, max_params: float) -> bool:
    model_id = model.get("modelId") or model.get("id", "")
    lower = model_id.lower()
    tags = {str(t).lower() for t in model.get("tags", [])}
    params = extract_params(model_id)

    if model.get("private"):
        return False
    if model.get("pipeline_tag") != "text-generation":
        return False
    if params is None or params > max_params:
        return False
    if not any(q in lower or q in tags for q in ["4bit", "4-bit", "q4", "mxfp4"]):
        return False
    if not (re.search(r"(^|[-_/])(instruct|chat|it)([-_/]|$)", lower) or "gpt-oss" in lower):
        return False
    if any(k in lower for k in ["vision", "vl", "audio", "speech", "embedding", "reranker"]):
        return False
    return True


def fetch_models() -> list[dict]:
    url = "https://huggingface.co/api/models?author=mlx-community&sort=downloads&direction=-1&limit=200"
    with urllib.request.urlopen(url, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def select_model() -> str:
    if os.environ.get("MODEL_ID"):
        return os.environ["MODEL_ID"]

    gb = ram_gb()
    max_params = max_params_for_ram(gb)

    try:
        candidates = [m for m in fetch_models() if is_good_chat_model(m, max_params)]
    except Exception as exc:
        print(f"Model discovery failed, using fallback: {exc}", file=sys.stderr)
        return fallback_model(gb)

    if not candidates:
        return fallback_model(gb)

    def score(model: dict) -> tuple[float, int, int]:
        model_id = model.get("modelId") or model.get("id", "")
        params = extract_params(model_id) or 0.0
        downloads = int(model.get("downloads") or 0)
        no_custom_code = int("custom_code" not in {str(t).lower() for t in model.get("tags", [])})
        return (params, no_custom_code, downloads)

    best = max(candidates, key=score)
    return best.get("modelId") or best["id"]


if __name__ == "__main__":
    print(select_model())
