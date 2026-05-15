from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
import mlx_lm
import os

app = FastAPI(title="MLX Inference Server")

MODEL_ID = os.environ.get("MODEL_ID", "mlx-community/Qwen2.5-1.5B-Instruct")

print(f"Loading model: {MODEL_ID}...")
model, tokenizer = mlx_lm.load(MODEL_ID)
print("Model loaded successfully")


class GenerateRequest(BaseModel):
    prompt: str
    max_tokens: Optional[int] = 300
    temp: Optional[float] = 0.7
    repeat_penalty: Optional[float] = 1.1
    top_p: Optional[float] = 0.9


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
    uvicorn.run(app, host="127.0.0.1", port=8001)
