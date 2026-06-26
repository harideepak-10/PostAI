"""
PostAI Backend — Multi-provider image generation
User prompt → Groq (enhance prompt + captions) → Image AI (Gemini / DALL-E / Pollinations) → frontend
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import httpx
import asyncio
import json
import random
import base64
import urllib.parse
import os
from pydantic import BaseModel
from typing import List, Optional

app = FastAPI(title="PostAI Backend", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

GROQ_API_BASE = "https://api.groq.com/openai/v1"
DEFAULT_MODEL  = "llama-3.3-70b-versatile"


# ── Request model ───────────────────────────────────────────────────────────────

class GenerateRequest(BaseModel):
    topic:         str
    platforms:     List[str]
    groq_key:      str
    model:         str = DEFAULT_MODEL
    img_provider:  str = "pollinations"   # "pollinations" | "gemini" | "openai"
    gemini_key:    Optional[str] = None
    openai_img_key: Optional[str] = None


# ── Groq helper ────────────────────────────────────────────────────────────────

async def groq_call(client: httpx.AsyncClient, api_key: str, body: dict) -> dict:
    r = await client.post(
        f"{GROQ_API_BASE}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=body,
        timeout=40.0,
    )
    if r.status_code == 429:
        raise HTTPException(status_code=429, detail="Groq rate limit — try again in a moment")
    r.raise_for_status()
    return r.json()


def parse_json(d: dict) -> dict:
    raw = d["choices"][0]["message"]["content"].strip()
    raw = raw.lstrip("```json").lstrip("```").rstrip("```").strip()
    m = __import__("re").search(r"\{[\s\S]*\}", raw)
    return json.loads(m.group(0) if m else raw)


# ── Task 1: Enhance image prompt + pick design config ─────────────────────────

async def gen_design(client: httpx.AsyncClient, api_key: str, model: str, topic: str) -> dict:
    d = await groq_call(client, api_key, {
        "model": model,
        "temperature": 0.9,
        "max_tokens": 700,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a senior art director and AI image prompt engineer. "
                    "You write world-class image prompts that generate stunning, photorealistic visuals. "
                    "Return only valid JSON."
                )
            },
            {
                "role": "user",
                "content": f"""Create the design configuration for a premium social media marketing poster about: "{topic}"

Return JSON with exactly these keys:
- "template": one of "saas" | "cyber-ai" | "corporate" | "minimal" | "glassmorphism"
- "primary_color": hex color matching the topic (e.g. "#7c3aed")
- "secondary_color": complementary accent hex
- "layout": one of "left-text" | "right-text" | "bottom-text" | "center-overlay"
- "headline": ALL CAPS, max 5 words
- "subheadline": supporting line, max 8 words
- "description": 1-2 sentence description
- "points": array of exactly 4 bullet points, max 5 words each
- "stat": impressive metric like "500+" or "99%"
- "stat_label": label for the stat, max 4 words
- "cta": call-to-action, max 5 words
- "image_prompt": A vivid, detailed paragraph describing a PHOTOREALISTIC 3D RENDERED SCENE for this topic.
  Describe exactly: the main subject (specific object/person/device), the environment, lighting (neon rim lights, volumetric fog, lens flares), materials (glowing glass, brushed metal), camera angle, mood.
  Style: cinematic CGI, 8K, octane render, Apple advertisement quality.
  Under 120 words. No mentions of text, letters, or UI buttons."""
            }
        ]
    })
    try:
        return parse_json(d)
    except Exception:
        return {
            "template": "cyber-ai", "primary_color": "#7c3aed", "secondary_color": "#22d3ee",
            "layout": "bottom-text", "headline": topic.upper()[:30],
            "subheadline": "Professional. Powerful. Proven.",
            "description": f"Discover the future of {topic}.",
            "points": ["Top Quality", "Expert Team", "Fast Delivery", "Best Value"],
            "stat": "100%", "stat_label": "Client Satisfaction", "cta": "Get Started Today",
            "image_prompt": (
                f"Cinematic 3D render of {topic}. Glowing AI hologram floats in a dark futuristic studio, "
                "blue and purple neon rim lighting, volumetric light rays, glassmorphism panels, "
                "floating digital particles, deep space dark background, ultra-realistic, 8K, octane render."
            )
        }


# ── Task 2: Social media captions ──────────────────────────────────────────────

async def gen_captions(client: httpx.AsyncClient, api_key: str, model: str, topic: str, platforms: List[str]) -> dict:
    plat_str   = ", ".join(platforms)
    plat_rules = ""
    if "linkedin"  in platforms: plat_rules += '- "linkedin": professional, 5-8 hashtags, max 1300 chars\n'
    if "instagram" in platforms: plat_rules += '- "instagram": fun & visual, emojis, 15-20 hashtags, max 2000 chars\n'
    if "facebook"  in platforms: plat_rules += '- "facebook": conversational, 3-5 hashtags, end with question, max 500 chars\n'

    d = await groq_call(client, api_key, {
        "model": model, "temperature": 0.8, "max_tokens": 2000,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": "Expert social media copywriter. Return only valid JSON."},
            {"role": "user", "content": f'Write captions for: "{topic}"\nPlatforms: {plat_str}\n{plat_rules}\nReturn JSON with keys: {plat_str}'}
        ]
    })
    try:
        return parse_json(d)
    except Exception:
        return {p: f"Exciting update about {topic}! #marketing #{topic.replace(' ','')}" for p in platforms}


# ── Image generation — Gemini Imagen 3 ─────────────────────────────────────────

async def gen_image_gemini(prompt: str, api_key: str) -> str:
    """Google Gemini Imagen 3 — returns data:image/png;base64,..."""
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"imagen-3.0-generate-001:predict?key={api_key}"
    )
    payload = {
        "instances": [{"prompt": prompt}],
        "parameters": {
            "sampleCount": 1,
            "aspectRatio": "4:5",
            "safetyFilterLevel": "block_few",
            "personGeneration": "allow_adult"
        }
    }
    async with httpx.AsyncClient(timeout=90.0) as client:
        r = await client.post(url, json=payload)
        if r.status_code != 200:
            raise HTTPException(status_code=r.status_code, detail=f"Gemini error: {r.text[:200]}")
        data = r.json()
        b64  = data["predictions"][0]["bytesBase64Encoded"]
        return f"data:image/png;base64,{b64}"


# ── Image generation — OpenAI DALL-E 3 ─────────────────────────────────────────

async def gen_image_openai(prompt: str, api_key: str) -> str:
    """OpenAI DALL-E 3 HD — returns image URL"""
    async with httpx.AsyncClient(timeout=90.0) as client:
        r = await client.post(
            "https://api.openai.com/v1/images/generations",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": "dall-e-3",
                "prompt": prompt + ". No text, no letters, no watermarks.",
                "n": 1,
                "size": "1024x1792",
                "quality": "hd",
                "style": "vivid"
            }
        )
        if r.status_code != 200:
            raise HTTPException(status_code=r.status_code, detail=f"OpenAI error: {r.text[:200]}")
        return r.json()["data"][0]["url"]


# ── Image generation — Pollinations (free, no key) ─────────────────────────────

async def gen_image_pollinations(prompt: str) -> str:
    """Pollinations gptimage (DALL-E 3 quality) — returns URL"""
    full = (
        f"{prompt}. "
        "Photorealistic, ultra high quality, 8K, cinematic lighting. "
        "No text, no letters, no watermarks, no logos."
    )
    neg = "text, letters, watermark, logo, blurry, low quality, ugly, deformed, nsfw"
    enc = urllib.parse.quote(full)
    neg_enc = urllib.parse.quote(neg)
    seed = random.randint(0, 999999)
    return (
        f"https://image.pollinations.ai/prompt/{enc}"
        f"?width=1024&height=1280&model=gptimage&nologo=true&nofeed=true&seed={seed}"
    )


# ── Route image gen to the right provider ──────────────────────────────────────

async def generate_image(prompt: str, provider: str, gemini_key: str = None, openai_key: str = None) -> str:
    if provider == "gemini" and gemini_key:
        try:
            return await gen_image_gemini(prompt, gemini_key)
        except Exception as e:
            print(f"Gemini failed ({e}), falling back to Pollinations")

    if provider == "openai" and openai_key:
        try:
            return await gen_image_openai(prompt, openai_key)
        except Exception as e:
            print(f"OpenAI failed ({e}), falling back to Pollinations")

    return await gen_image_pollinations(prompt)


# ── Main endpoint ───────────────────────────────────────────────────────────────

@app.post("/api/generate")
async def generate(req: GenerateRequest):
    if not req.groq_key:
        raise HTTPException(status_code=400, detail="Groq API key is required")
    if not req.topic.strip():
        raise HTTPException(status_code=400, detail="Topic cannot be empty")

    async with httpx.AsyncClient() as client:
        # Groq: design config + captions in parallel
        design, captions = await asyncio.gather(
            gen_design(client, req.groq_key, req.model, req.topic),
            gen_captions(client, req.groq_key, req.model, req.topic, req.platforms),
        )

    # Image generation with selected provider
    image_url = await generate_image(
        prompt       = design.get("image_prompt", req.topic),
        provider     = req.img_provider,
        gemini_key   = req.gemini_key,
        openai_key   = req.openai_img_key,
    )

    return {
        "poster_content": {
            "headline":    design.get("headline", ""),
            "subheadline": design.get("subheadline", ""),
            "description": design.get("description", ""),
            "points":      design.get("points", []),
            "stat":        design.get("stat", ""),
            "stat_label":  design.get("stat_label", ""),
            "cta":         design.get("cta", "Get Started"),
        },
        "design_config": {
            "template":        design.get("template", "saas"),
            "primary_color":   design.get("primary_color", "#7c3aed"),
            "secondary_color": design.get("secondary_color", "#22d3ee"),
            "layout":          design.get("layout", "bottom-text"),
        },
        "captions":  captions,
        "image_url": image_url,
        "provider":  req.img_provider,
    }


@app.get("/health")
async def health():
    return {"status": "ok", "service": "PostAI Backend v2"}


# ── Serve frontend ──────────────────────────────────────────────────────────────

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "public")

@app.get("/")
async def serve_index():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))

if os.path.isdir(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


# ── Run ─────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
