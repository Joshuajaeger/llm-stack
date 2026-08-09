"""Classify ambiguous documents with the local model in this repo.

Requests go to the FastAPI router on loopback (`src/router/`), authenticated
with the same `API_KEY` from `.env` that Open WebUI uses. Nothing is sent off
the Mac.

The model is never trusted to invent a folder: replies are parsed strictly and
every label is checked against the taxonomy. Anything unparseable, unknown, or
low-confidence comes back as "unresolved" and ends up in the review queue.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Sequence

import httpx

from .settings import LLMSettings

SYSTEM_RULES = (
    "You are a file classifier. For each numbered file you are given a name, "
    "its folder, and a short text excerpt. Assign each file exactly one category "
    "from the allowed list.\n"
    "Reply with ONLY a JSON array, no prose, no markdown fences. Each element: "
    '{"i": <file number>, "category": "<exact label from the list>", '
    '"confidence": <0.0-1.0>}\n'
    "Use the confidence honestly — a low number is better than a wrong folder. "
    "If a file does not clearly belong anywhere, use the review category."
)


@dataclass
class Verdict:
    category: str
    confidence: float


class LocalLLM:
    """Thin client for the repo's router."""

    def __init__(self, settings: LLMSettings):
        self.settings = settings

    # -- availability ----------------------------------------------------

    def available(self) -> tuple[bool, str]:
        """Is the stack up and is our key accepted?"""
        if not self.settings.enabled:
            return False, "disabled in config"
        if not self.settings.api_key:
            return False, "API_KEY not set — run `source .env` first"
        try:
            response = httpx.get(self.settings.health_url, timeout=5.0)
        except httpx.HTTPError as exc:
            return False, f"router unreachable ({exc.__class__.__name__}) — try `make up`"
        if response.status_code != 200:
            return False, f"router returned HTTP {response.status_code}"
        return True, "ok"

    # -- classification --------------------------------------------------

    def classify(
        self,
        items: Sequence[dict[str, Any]],
        categories: Sequence[str],
        review_category: str,
    ) -> dict[int, Verdict]:
        """Classify a batch. Keys are indices into `items`.

        Missing keys mean "the model did not give a usable answer for that
        file" — the caller decides what to do, and always sends those to review.
        """
        if not items:
            return {}

        prompt = self._build_prompt(items, categories, review_category)
        raw = self._ask(prompt)
        if raw is None:
            return {}

        allowed = set(categories)
        verdicts: dict[int, Verdict] = {}
        for entry in _parse_array(raw):
            index = _as_int(entry.get("i", entry.get("index")))
            category = entry.get("category")
            if index is None or not isinstance(category, str):
                continue
            if not (0 <= index < len(items)):
                continue
            category = category.strip().strip("/")
            if category not in allowed:
                continue
            verdicts[index] = Verdict(
                category=category,
                confidence=_as_float(entry.get("confidence"), 0.5),
            )
        return verdicts

    # -- internals -------------------------------------------------------

    def _build_prompt(
        self,
        items: Sequence[dict[str, Any]],
        categories: Sequence[str],
        review_category: str,
    ) -> str:
        header = (
            f"{SYSTEM_RULES}\n\n"
            f"Allowed categories:\n"
            + "\n".join(f"- {c}" for c in categories)
            + f"\n\nReview category (use when unsure): {review_category}\n\nFiles:\n"
        )

        # Share whatever prompt budget is left evenly across the batch, so a
        # single enormous excerpt can't crowd out the other files.
        budget = max(self.settings.max_prompt_chars - len(header) - 200, 0)
        per_item = max(budget // max(len(items), 1) - 120, 80)

        lines = []
        for index, item in enumerate(items):
            text = (item.get("text") or "")[:per_item]
            lines.append(
                f'{index}. name="{item.get("name", "")}" '
                f'folder="{item.get("folder", "")}"'
                + (f' excerpt="{text}"' if text else " excerpt=(none)")
            )
        return header + "\n".join(lines) + "\n\nJSON array:"

    def _ask(self, prompt: str) -> str | None:
        try:
            response = httpx.post(
                self.settings.url,
                headers={"X-Api-Key": self.settings.api_key},
                json={"prompt": prompt, "max_tokens": self.settings.max_tokens},
                timeout=self.settings.timeout,
            )
            response.raise_for_status()
        except httpx.HTTPError:
            return None
        body = response.json()
        text = body.get("text")
        return text if isinstance(text, str) else None


def _parse_array(text: str) -> list[dict]:
    """Recover a JSON array from a chatty reply.

    Small local models like to wrap output in prose or code fences, so take
    the outermost bracketed span rather than requiring a clean response.
    """
    text = re.sub(r"```(?:json)?", "", text).strip()
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end <= start:
        return []
    try:
        parsed = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return []
    return [item for item in parsed if isinstance(item, dict)] if isinstance(parsed, list) else []


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_float(value: Any, default: float) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return min(max(result, 0.0), 1.0)
