from dataclasses import dataclass
import re


@dataclass(frozen=True)
class RouteDecision:
    backend: str
    reason: str
    forced: bool = False
    structured_score: int = 0
    fast_score: int = 0


def normalize_backend(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip().lower()
    if normalized in {"auto", "llm-stack", "default"}:
        return None
    if normalized in {"mlx", "mlxlm", "mlx-lm"}:
        return "mlx"
    if normalized in {"llama", "llama.cpp", "llamacpp", "cpp", "gguf"}:
        return "llama.cpp"
    return None


def decide_backend(prompt: str, requested_backend: str | None = None) -> RouteDecision:
    forced_backend = normalize_backend(requested_backend)
    if forced_backend:
        return RouteDecision(
            backend=forced_backend,
            reason=f"backend forced by request: {requested_backend}",
            forced=True,
        )

    text = prompt.lower()
    structured_score = 0
    fast_score = 0
    reasons: list[str] = []

    strong_structured_patterns = [
        r"\bjson\b",
        r"\bschema\b",
        r"\bgbnf\b",
        r"\bgrammar\b",
        r"valid json",
        r"return only json",
        r"strict json",
    ]
    if any(re.search(pattern, text) for pattern in strong_structured_patterns):
        structured_score += 4
        reasons.append("strong structured-output signal")

    medium_structured_patterns = [
        r"strict format",
        r"exact format",
        r"machine[- ]readable",
        r"extract .* fields",
        r"parse .* into",
        r"classify .* as",
    ]
    if any(re.search(pattern, text) for pattern in medium_structured_patterns):
        structured_score += 3
        reasons.append("format-control signal")

    weak_structured_terms = ["yaml", "xml", "csv", "table", "bullet", "list", "fields", "keys"]
    weak_hits = [term for term in weak_structured_terms if term in text]
    if weak_hits:
        structured_score += min(len(weak_hits), 2)
        reasons.append("weak structure signal")

    fast_terms = [
        "explain", "chat", "brainstorm", "write", "rewrite", "summarize",
        "translate", "story", "email", "help", "idea", "compare", "why",
    ]
    fast_hits = [term for term in fast_terms if term in text]
    if fast_hits:
        fast_score += min(len(fast_hits), 3)

    if len(prompt) > 1500:
        fast_score += 1

    if structured_score >= 3 and structured_score > fast_score:
        return RouteDecision(
            backend="llama.cpp",
            reason=", ".join(reasons) or "structured-output prompt",
            structured_score=structured_score,
            fast_score=fast_score,
        )

    return RouteDecision(
        backend="mlx",
        reason="default fast Apple Silicon inference",
        structured_score=structured_score,
        fast_score=fast_score,
    )
