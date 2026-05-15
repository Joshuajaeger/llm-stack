from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional
import mlx_lm
import os

from src.model_selector import select_model


app = FastAPI(title="MLX Inference Server")

MLX_BIND_HOST = os.environ.get("MLX_HOST", "127.0.0.1")
MLX_BIND_PORT = int(os.environ.get("MLX_PORT", "8001"))


@app.middleware("http")
async def restrict_to_loopback(request: Request, call_next):
    # MLX has no auth. Refuse anything that is not loopback when bound
    # to a non-loopback interface.
    client = request.client.host if request.client else ""
    if client not in {"127.0.0.1", "::1", "localhost"}:
        raise HTTPException(status_code=403, detail="forbidden")
    return await call_next(request)

MODEL_ID = os.environ.get("MODEL_ID") or select_model()

print(f"Loading model: {MODEL_ID}...")
model, tokenizer = mlx_lm.load(MODEL_ID)
print("Model loaded successfully")


MAX_PROMPT_CHARS = int(os.environ.get("MAX_PROMPT_CHARS", "20000"))
MAX_TOKENS_CAP = int(os.environ.get("MAX_TOKENS_CAP", "2048"))


class GenerateRequest(BaseModel):
    prompt: str = Field(..., max_length=MAX_PROMPT_CHARS)
    max_tokens: Optional[int] = Field(default=300, ge=1, le=MAX_TOKENS_CAP)
    temp: Optional[float] = Field(default=0.7, ge=0.0, le=2.0)
    repeat_penalty: Optional[float] = Field(default=1.1, ge=0.0, le=5.0)
    top_p: Optional[float] = Field(default=0.9, ge=0.0, le=1.0)


class GenerateResponse(BaseModel):
    text: str
    model: str
    tokens_generated: int


@app.get("/")
def health():
    return {"status": "healthy", "model": MODEL_ID}


@app.get("/v1/models")
def list_models():
    return {
        "object": "list",
        "data": [{"id": MODEL_ID, "object": "model", "created": 1234567890}]
    }


@app.post("/generate", response_model=GenerateResponse)
def generate(req: GenerateRequest):
    output = mlx_lm.generate(
        model,
        tokenizer,
        prompt=req.prompt,
        max_tokens=req.max_tokens,
        temp=req.temp,
        repeat_penalty=req.repeat_penalty,
        top_p=req.top_p,
    )
    return GenerateResponse(
        text=output,
        model=MODEL_ID,
        tokens_generated=len(tokenizer.encode(output)),
    )


@app.post("/stream")
def stream(req: GenerateRequest):
    def gen():
        for token in mlx_lm.generate(
            model,
            tokenizer,
            prompt=req.prompt,
            max_tokens=req.max_tokens,
            temp=req.temp,
            repeat_penalty=req.repeat_penalty,
            top_p=req.top_p,
            stream=True,
        ):
            yield f"data: {token}\n\n"
        yield "data: [DONE]\n\n"
    return StreamingResponse(gen(), media_type="text/event-stream")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=MLX_BIND_HOST, port=MLX_BIND_PORT)
