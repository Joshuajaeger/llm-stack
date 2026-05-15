from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel
from typing import Optional
import httpx
import os

from .router import MLX_URL, LLAMA_URL, is_structured
from .auth import verify_api_key

app = FastAPI(title="LLM Stack Router")


class ChatRequest(BaseModel):
    prompt: str
    max_tokens: Optional[int] = 300


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

    backend = "llama.cpp" if is_structured(req.prompt) else "MLX"
    url = LLAMA_URL if is_structured(req.prompt) else MLX_URL

    async with httpx.AsyncClient(timeout=60) as client:
        if is_structured(req.prompt):
            r = await client.post(url, json={
                "prompt": req.prompt,
                "n_predict": req.max_tokens,
            })
            body = r.json()
            text = body.get("content", str(body))
        else:
            r = await client.post(url, json={
                "prompt": req.prompt,
                "max_tokens": req.max_tokens,
            })
            body = r.json()
            text = body.get("text", str(body))

    return {"backend": backend, "text": text}


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
    result = await chat(ChatRequest(prompt=prompt, max_tokens=req.max_tokens), x_api_key=api_key)
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
