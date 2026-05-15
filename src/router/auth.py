import os

API_KEY = os.environ.get("API_KEY", "secret123")


def verify_api_key(key: str) -> bool:
    return key == API_KEY
