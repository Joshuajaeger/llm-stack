import hmac
import os

API_KEY = os.environ.get("API_KEY", "")


def verify_api_key(key: str | None) -> bool:
    if not API_KEY:
        # No key configured = closed by default.
        return False
    if not key:
        return False
    return hmac.compare_digest(API_KEY, key)
