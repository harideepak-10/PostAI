"""
PostAI FastAPI Backend
Orchestrates: Groq (3 parallel calls) → Pollinations image → returns to frontend
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import httpx
import asyncio
import json
import random
import urllib.parse
import os
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

DESIGN_SYSTEM_PROMPT = """You are a senior art director at a world-class design agency.
You write image prompts that produce stunning, photorealistic 3D advertisement visuals.
Your prompts are concrete, specific, and describe exact visual scenes — not concepts.
Return only valid JSON."""

DESIGN_USER_PROMPT = """Design the visual configuration for a premium social media marketing poster about: "{topic}"

Return JSON with exactly these keys:
- "template": one of "saas" | "cyber-ai" | "corporate" | "minimal" | "glassmorphism"
- "primary_color": hex color that fits the topic (e.g. "#7c3aed")
- "secondary_color": complementary accent hex color
- "layout": one of "left-text" | "right-text" | "bottom-text" | "center-overlay"
- "image_prompt": Write a single detailed paragraph (not tags) describing a photorealistic 3D rendered scene for "{topic}".

  The scene must be VISUALLY SPECIFIC — describe exactly what is in the image:
  - The main subject (a specific object, person, device, or scene element directly related to {topic})
  - The environment and atmosphere (dark studio, futuristic room, abstract space, etc.)
  - Lighting details (neon blue rim light from left, purple volumetric fog, lens flare at top right)
  - Materials and textures (brushed metal, glowing glass, holographic surfaces)
  - Mood and style (cinematic, luxury advertisement, Apple product reveal style)
  - Camera angle (wide angle, eye-level, slight upward tilt)

  Keep it under 120 words. Write as a vivid scene description. Do NOT mention text, letters, watermarks, or logos."""


async def gen_design_config(client: httpx.AsyncClient, api_key: str, model: str, topic: str) -> dict:
    d = await groq_call(client, api_key, {
        "model": model,
        "temperature": 0.9,
        "max_tokens": 800,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": DESIGN_SYSTEM_PROMPT},
            {"role": "user",   "content": DESIGN_USER_PROMPT.format(topic=topic)},
        ]
    })
    try:
        return parse_json_response(d)
    except Exception:
        return {
            "template": "cyber-ai",
            "primary_color": "#7c3aed",
            "secondary_color": "#22d3ee",
            "layout": "bottom-text",
            "image_prompt": (
                f"A cinematic 3D rendered scene for {topic}. A glowing AI hologram floats in a dark futuristic room, "
                "surrounded by blue and purple neon light rays. Holographic data streams flow around a sleek laptop "
                "displaying a glowing dashboard interface. The background features deep space-like darkness with "
                "scattered light particles and volumetric fog. Cinematic lighting with rim lights, lens flares, "
                "and dramatic shadows. Ultra-realistic, 8K, octane render quality, Apple advertisement style."
            )
        }


# ── Image generation — tries gptimage (DALL-E 3), falls back to flux-pro ────────

async def gen_background_image(image_prompt: str, seed: Optional[int] = None) -> str:
    seed = seed or random.randint(0, 999999)

    # Clean, focused prompt — no contradictory "leave space" instructions
    full_prompt = (
        f"{image_prompt} "
        "Photorealistic, ultra high quality, 8K resolution, cinematic color grading, "
        "professional advertisement photography. No text, no letters, no watermarks, no logos."
    )

    negative = (
        "text, letters, words, watermark, logo, signature, blurry, low quality, "
        "ugly, deformed, pixelated, cartoon, clipart, flat, dull, overexposed, nsfw"
    )

    prompt_enc = urllib.parse.quote(full_prompt)
    neg_enc    = urllib.parse.quote(negative)

    # gptimage = DALL-E 3 quality via Pollinations — best prompt adherence
    # Returns both URLs; frontend tries gptimage first, falls back to flux-pro
    gptimage_url = (
        f"https://image.pollinations.ai/prompt/{prompt_enc}"
        f"?width=1024&height=1280&model=gptimage&nologo=true&nofeed=true"
    )
    return gptimage_url


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


# ── Serve frontend static files ─────────────────────────────────────────────────

FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "public")

@app.get("/")
async def serve_index():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))

# Mount any other static assets (css, images, etc.) if present
if os.path.isdir(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


# ── Run ─────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
