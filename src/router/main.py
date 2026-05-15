from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel
from typing import Optional
import httpx

from .router import MLX_URL, LLAMA_URL, is_structured
from .auth import verify_api_key

app = FastAPI(title="LLM Stack Router")


class ChatRequest(BaseModel):
    prompt: str
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
