"""
PostAI FastAPI Backend
Orchestrates: Groq (3 parallel calls) → Pollinations image → returns to frontend
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import httpx
import asyncio
import json
import random
import urllib.parse
from pydantic import BaseModel
from typing import List, Optional

app = FastAPI(title="PostAI Backend", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

GROQ_API_BASE = "https://api.groq.com/openai/v1"
DEFAULT_MODEL  = "llama-3.3-70b-versatile"


# ── Models ─────────────────────────────────────────────────────────────────────

class GenerateRequest(BaseModel):
    topic:     str
    platforms: List[str]
    groq_key:  str
    model:     str = DEFAULT_MODEL


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


def parse_json_response(d: dict) -> dict:
    raw = d["choices"][0]["message"]["content"].strip()
    raw = raw.lstrip("```json").lstrip("```").rstrip("```").strip()
    match = __import__("re").search(r"\{[\s\S]*\}", raw)
    if match:
        raw = match.group(0)
    return json.loads(raw)


# ── Task 1: Poster content ─────────────────────────────────────────────────────

async def gen_poster_content(client: httpx.AsyncClient, api_key: str, model: str, topic: str) -> dict:
    d = await groq_call(client, api_key, {
        "model": model,
        "temperature": 0.8,
        "max_tokens": 500,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": "You are a professional marketing copywriter. Return only valid JSON with no extra text."
            },
            {
                "role": "user",
                "content": (
                    f'Create marketing poster content for: "{topic}"\n\n'
                    "Return JSON with exactly these keys:\n"
                    '- "headline": ALL CAPS, max 5 words\n'
                    '- "subheadline": supporting line, max 8 words\n'
                    '- "description": 1-2 sentence description\n'
                    '- "points": array of exactly 4 bullet points, max 5 words each\n'
                    '- "stat": impressive metric like "500+" or "99%" or "10X"\n'
                    '- "stat_label": label for the stat, max 4 words\n'
                    '- "cta": call-to-action button text, max 5 words'
                )
            }
        ]
    })
    try:
        return parse_json_response(d)
    except Exception:
        return {
            "headline": topic.upper()[:30],
            "subheadline": "Professional. Powerful. Proven.",
            "description": f"Discover the best in {topic}.",
            "points": ["Top Quality Results", "Expert Team", "Fast Delivery", "Best Value"],
            "stat": "100%",
            "stat_label": "Client Satisfaction",
            "cta": "Get Started Today"
        }


# ── Task 2: Social media captions ──────────────────────────────────────────────

async def gen_captions(client: httpx.AsyncClient, api_key: str, model: str, topic: str, platforms: List[str]) -> dict:
    plat_str = ", ".join(platforms)
    plat_rules = ""
    if "linkedin"  in platforms: plat_rules += '- "linkedin": professional tone, 5-8 hashtags, max 1300 chars\n'
    if "instagram" in platforms: plat_rules += '- "instagram": fun & visual, emojis throughout, 15-20 hashtags, max 2000 chars\n'
    if "facebook"  in platforms: plat_rules += '- "facebook": conversational, 3-5 hashtags, end with a question, max 500 chars\n'

    d = await groq_call(client, api_key, {
        "model": model,
        "temperature": 0.8,
        "max_tokens": 2000,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": "You are a social media copywriter. Return only valid JSON with platform captions."
            },
            {
                "role": "user",
                "content": (
                    f'Write social media captions for: "{topic}"\n\n'
                    f"Platforms: {plat_str}\n\n"
                    "Requirements:\n"
                    f"{plat_rules}"
                    f"\nReturn JSON with keys: {plat_str}"
                )
            }
        ]
    })
    try:
        return parse_json_response(d)
    except Exception:
        return {p: f"Check out our latest on {topic}! #marketing" for p in platforms}


# ── Task 3: Design configuration + image prompt ────────────────────────────────

async def gen_design_config(client: httpx.AsyncClient, api_key: str, model: str, topic: str) -> dict:
    d = await groq_call(client, api_key, {
        "model": model,
        "temperature": 0.85,
        "max_tokens": 700,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": "You are a professional graphic designer and AI image prompt engineer. Return only valid JSON."
            },
            {
                "role": "user",
                "content": (
                    f'Design the visual configuration for a social media marketing poster about: "{topic}"\n\n'
                    "Return JSON with exactly these keys:\n"
                    '- "template": one of "saas" | "cyber-ai" | "corporate" | "minimal" | "glassmorphism" — pick the most fitting\n'
                    '- "primary_color": hex color matching the topic theme (e.g. "#7c3aed")\n'
                    '- "secondary_color": complementary hex color\n'
                    '- "layout": one of "left-text" | "right-text" | "bottom-text" | "center-overlay"\n'
                    '- "image_style": one of "hologram" | "mockup" | "abstract-tech" | "business-illustration" | "product-scene"\n'
                    '- "image_prompt": You are a professional graphic designer. Create a detailed image prompt for a '
                    f'HIGH-QUALITY visual asset for a marketing poster about "{topic}". '
                    "This image is the hero visual — NOT a simple background. Include:\n"
                    f"  * Specific visual subject relevant to {topic} (AI hologram, laptop mockup, product, tech scene, etc.)\n"
                    "  * Professional 3D render or cinematic photography style\n"
                    "  * Dramatic cinematic lighting, volumetric light rays\n"
                    "  * Rich color grading matching the primary_color\n"
                    "  * Deliberate empty/dark space on the opposite side for text overlay\n"
                    "  * Ultra high quality, 8K, photorealistic or premium digital art\n"
                    "  * Premium branding aesthetic (luxury, tech, corporate, minimal)\n"
                    "  * Absolutely NO text, NO letters, NO watermarks, NO logos, NO UI elements\n"
                    "  Output as comma-separated tags, 80-120 words."
                )
            }
        ]
    })
    try:
        return parse_json_response(d)
    except Exception:
        return {
            "template": "saas",
            "primary_color": "#7c3aed",
            "secondary_color": "#22d3ee",
            "layout": "bottom-text",
            "image_style": "abstract-tech",
            "image_prompt": f"premium dark background, {topic}, cinematic lighting, deep blue tones, no text, no watermark"
        }


# ── Image generation (Pollinations FLUX) ───────────────────────────────────────

async def gen_background_image(image_prompt: str, seed: Optional[int] = None) -> str:
    seed = seed or random.randint(0, 999999)
    full_prompt = f"{image_prompt}, no text, no words, no letters, no watermark, no logo, ultra detailed, 8k quality"
    negative    = "text, words, letters, watermark, logo, signature, url, copyright, blurry, low quality, ugly, deformed, nsfw"

    prompt_enc  = urllib.parse.quote(full_prompt)
    neg_enc     = urllib.parse.quote(negative)

    url = (
        f"https://image.pollinations.ai/prompt/{prompt_enc}"
        f"?width=1024&height=1280&model=flux-pro&seed={seed}"
        f"&nologo=true&nofeed=true&negative={neg_enc}"
    )
    return url


# ── Main endpoint ───────────────────────────────────────────────────────────────

@app.post("/api/generate")
async def generate(req: GenerateRequest):
    if not req.groq_key:
        raise HTTPException(status_code=400, detail="Groq API key is required")
    if not req.topic.strip():
        raise HTTPException(status_code=400, detail="Topic cannot be empty")

    async with httpx.AsyncClient() as client:
        # 3 Groq calls in parallel
        content, captions, design = await asyncio.gather(
            gen_poster_content(client, req.groq_key, req.model, req.topic),
            gen_captions(client, req.groq_key, req.model, req.topic, req.platforms),
            gen_design_config(client, req.groq_key, req.model, req.topic),
        )

    # Image generation (after Groq, no rate limit concern)
    image_url = await gen_background_image(design.get("image_prompt", req.topic))

    return {
        "poster_content": content,
        "captions":       captions,
        "design_config":  design,
        "image_url":      image_url,
    }


@app.get("/health")
async def health():
    return {"status": "ok", "service": "PostAI Backend"}


# ── Run ─────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    port = int(__import__("os").getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
