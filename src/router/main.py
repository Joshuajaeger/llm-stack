from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel
from typing import Optional
import httpx
import os

from .decision import RouteDecision, decide_backend
from .router import MLX_URL, LLAMA_URL
from .auth import verify_api_key

app = FastAPI(title="LLM Stack Router")


class ChatRequest(BaseModel):
    prompt: str
    max_tokens: Optional[int] = 300
    backend: Optional[str] = None


class OpenAIMessage(BaseModel):
    role: str
    content: str


class OpenAIChatRequest(BaseModel):
    model: Optional[str] = "llm-stack"
    messages: list[OpenAIMessage]
    max_tokens: Optional[int] = 300


@app.get("/")
def health():
    return {"status": "healthy", "backends": {"mlx": MLX_URL, "llama": LLAMA_URL}}


@app.post("/chat")
async def chat(req: ChatRequest, x_api_key: str = Header(None)):
    if not verify_api_key(x_api_key):
        raise HTTPException(status_code=401, detail="unauthorized")

    decision = decide_backend(req.prompt, req.backend)

    async with httpx.AsyncClient(timeout=60) as client:
        if decision.backend == "mlx":
            text = await call_mlx(client, req.prompt, req.max_tokens)
            return {
                "backend": "MLX",
                "decision": decision.__dict__,
                "text": text,
            }

        try:
            text = await call_llama(client, req.prompt, req.max_tokens)
            return {
                "backend": "llama.cpp",
                "decision": decision.__dict__,
                "text": text,
            }
        except httpx.HTTPError as exc:
            if decision.forced:
                raise HTTPException(status_code=503, detail=f"llama.cpp unavailable: {exc}")
            fallback = RouteDecision(
                backend="mlx",
                reason=f"{decision.reason}; llama.cpp unavailable, fell back to MLX",
                structured_score=decision.structured_score,
                fast_score=decision.fast_score,
            )
            text = await call_mlx(client, req.prompt, req.max_tokens)
            return {
                "backend": "MLX",
                "decision": fallback.__dict__,
                "text": text,
            }


async def call_mlx(client: httpx.AsyncClient, prompt: str, max_tokens: int | None) -> str:
    r = await client.post(
        MLX_URL,
        json={
            "prompt": prompt,
            "max_tokens": max_tokens,
        },
    )
    r.raise_for_status()
    body = r.json()
    return body.get("text", str(body))


async def call_llama(client: httpx.AsyncClient, prompt: str, max_tokens: int | None) -> str:
    r = await client.post(
        LLAMA_URL,
        json={
            "prompt": prompt,
            "n_predict": max_tokens,
        },
    )
    r.raise_for_status()
    body = r.json()
    return body.get("content", str(body))


@app.post("/route")
def route(req: ChatRequest, x_api_key: str = Header(None)):
    if not verify_api_key(x_api_key):
        raise HTTPException(status_code=401, detail="unauthorized")
    return decide_backend(req.prompt, req.backend).__dict__


def auth_or_401(x_api_key: str | None, authorization: str | None) -> str:
    key = x_api_key
    if not key and authorization and authorization.lower().startswith("bearer "):
        key = authorization.split(" ", 1)[1]
    if not verify_api_key(key):
        raise HTTPException(status_code=401, detail="unauthorized")
    return key


@app.get("/v1/models")
def openai_models():
    return {
        "object": "list",
        "data": [{"id": "llm-stack", "object": "model", "owned_by": "local"}],
    }


@app.post("/v1/chat/completions")
async def openai_chat_completions(
    req: OpenAIChatRequest,
    x_api_key: str = Header(None),
    authorization: str = Header(None),
):
    api_key = auth_or_401(x_api_key, authorization)
    prompt = "\n".join(f"{m.role}: {m.content}" for m in req.messages)
    result = await chat(ChatRequest(prompt=prompt, max_tokens=req.max_tokens, backend=req.model), x_api_key=api_key)
    return {
        "id": "chatcmpl-local",
        "object": "chat.completion",
        "model": req.model or "llm-stack",
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": result["text"]},
            "finish_reason": "stop",
        }],
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", "8000")))
