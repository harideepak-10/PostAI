"""
PostAI v3 — fal.ai FLUX, no database
Workflow: prompt → fal.ai FLUX → image URL → return to frontend
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import httpx
import os
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

FAL_KEY      = os.getenv("FAL_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")   # optional — for captions

app = FastAPI(title="PostAI", version="3.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class GenerateRequest(BaseModel):
    prompt: str


# ── fal.ai FLUX ──────────────────────────────────────────────────────────────

async def call_fal(prompt: str) -> str:
    if not FAL_KEY:
        raise HTTPException(500, "FAL_KEY not set in backend .env — add it and restart")

    async with httpx.AsyncClient(timeout=120.0) as client:
        r = await client.post(
            "https://fal.run/fal-ai/flux/dev",
            headers={"Authorization": f"Key {FAL_KEY}", "Content-Type": "application/json"},
            json={
                "prompt": prompt,
                "image_size": {"width": 1024, "height": 1280},   # 4:5 portrait
                "num_inference_steps": 28,
                "guidance_scale": 3.5,
                "num_images": 1,
                "enable_safety_checker": True,
                "output_format": "jpeg",
            },
        )
        if not r.is_success:
            raise HTTPException(r.status_code, f"fal.ai error: {r.text[:400]}")
        return r.json()["images"][0]["url"]


# ── Groq captions (optional) ─────────────────────────────────────────────────

async def gen_captions(prompt: str) -> dict | None:
    if not GROQ_API_KEY:
        return None
    try:
        import json, re
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
                json={
                    "model": "llama-3.3-70b-versatile",
                    "temperature": 0.8,
                    "max_tokens": 1200,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": "Social media expert. Return only valid JSON."},
                        {"role": "user", "content": (
                            f'Write captions for this image post about: "{prompt}"\n'
                            'Return JSON with keys "linkedin", "instagram", "facebook".\n'
                            'linkedin: professional, 5-8 hashtags.\n'
                            'instagram: emojis, 15-20 hashtags.\n'
                            'facebook: conversational, end with a question.'
                        )},
                    ],
                },
            )
            if r.is_success:
                raw = r.json()["choices"][0]["message"]["content"].strip()
                raw = raw.lstrip("```json").lstrip("```").rstrip("```").strip()
                m = re.search(r"\{[\s\S]*\}", raw)
                return json.loads(m.group(0) if m else raw)
    except Exception as e:
        print(f"Captions skipped: {e}")
    return None


# ── Route ────────────────────────────────────────────────────────────────────

@app.post("/api/generate")
async def generate(req: GenerateRequest):
    if not req.prompt.strip():
        raise HTTPException(400, "Prompt is required")

    image_url = await call_fal(req.prompt.strip())
    captions  = await gen_captions(req.prompt.strip())

    return {
        "image_url": image_url,
        "prompt":    req.prompt.strip(),
        "captions":  captions,
    }


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "3.0.0"}


# ── Serve frontend ───────────────────────────────────────────────────────────

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "public")

@app.get("/")
async def serve_index():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))

if os.path.isdir(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", 8000)), reload=True)
