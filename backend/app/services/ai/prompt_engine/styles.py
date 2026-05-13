"""
Prompt style definitions — one config per model family.

Each style defines:
  quality_prefix  — prepended to final prompt (e.g. score tags for Pony)
  negative        — model-appropriate negative prompt
  banned_tags     — tags stripped from LLM output before quality_prefix is added
                    ALWAYS include the quality_prefix tags here to prevent duplication
  llm_template    — few-shot prompt sent to Ollama (English for better instruction-following)
"""
from __future__ import annotations

from enum import Enum


class PromptStyle(str, Enum):
    SDXL        = "sdxl"
    PONY        = "pony"
    FLUX        = "flux"
    NOOBAI      = "noobai"
    ILLUSTRIOUS = "illustrious"


# ── Quality tag sets (shared across banned_tags to prevent duplication) ───────

_QUALITY_TAGS_GENERIC = {
    "masterpiece", "best quality", "high quality", "good quality",
    "ultra detailed", "highly detailed", "extremely detailed",
    "ultra-detailed", "ultra high res", "8k", "4k", "hd", "uhd",
}

_QUALITY_TAGS_SCORE = {
    "score_9", "score_8_up", "score_7_up", "score_6", "score_5", "score_4",
}

_QUALITY_TAGS_NOOBAI = {
    "newest", "absurdres", "masterpiece", "best quality",
    "ultra detailed", "highly detailed",
}

_QUALITY_TAGS_ILLUSTRIOUS = {
    "newest", "highres", "masterpiece", "best quality",
    "ultra detailed", "highly detailed",
}

_SD_SYNTAX_TAGS = {
    "masterpiece", "best quality", "score_9", "ultra detailed",
    "1girl", "1boy", "source_anime", "source_furry",
}


# ── Per-style LLM templates (English for better instruction-following) ────────

_SDXL_TEMPLATE = """\
Convert the Chinese description into Danbooru-style image tags for Stable Diffusion SDXL.

Rules:
- Output ONLY lowercase English tags, comma-separated, no explanations or extra text
- Keep ALL subjects, actions, held objects, and directional words intact
  (右手 → right hand, 左手 → left hand, 右腳 → right leg, 左腳 → left leg)
- Add relevant scene, mood, and style details
- Do NOT add quality tags (masterpiece, best quality, ultra detailed, etc.)

Examples:
Input: 一個女孩右手拿傘
Output: 1girl, solo, holding umbrella, right hand, umbrella, standing, outdoors

Input: 少年坐在窗邊望向夜空
Output: 1boy, sitting, window, looking at sky, night sky, stars, indoors, melancholy

Input: {prompt}
Output:"""

_PONY_TEMPLATE = """\
Convert the Chinese description into Danbooru-style image tags for Pony Diffusion.

Rules:
- Output ONLY lowercase English tags, comma-separated, no explanations
- Keep ALL subjects, actions, and directional words intact
- Add source_anime for anime-style characters
- Do NOT add masterpiece, best quality, or score tags (handled automatically)

Examples:
Input: 一個女孩右手拿傘
Output: 1girl, solo, holding umbrella, right hand, umbrella, standing, source_anime

Input: 少年在雨中奔跑
Output: 1boy, solo, running, rain, wet, outdoors, source_anime

Input: 一隻貓趴在書桌上
Output: cat, lying, desk, indoors, looking at viewer, source_furry

Input: {prompt}
Output:"""

_FLUX_TEMPLATE = """\
Rewrite the Chinese description as a natural English image prompt for Flux.

Rules:
- Write 1-2 natural English sentences describing the scene
- Do NOT use comma-separated tag format
- Do NOT use SD-specific syntax (masterpiece, 1girl, score_9, etc.)
- Preserve directional words (right hand, left hand)
- Be descriptive and cinematic

Examples:
Input: 一個女孩右手拿傘
Output: A young girl standing outdoors, holding a colorful umbrella in her right hand, with a calm and serene expression.

Input: 少年坐在窗邊望向夜空
Output: A teenage boy sitting quietly by the window at night, gazing at the vast starry sky outside.

Input: {prompt}
Output:"""

_NOOBAI_TEMPLATE = """\
Convert the Chinese description into dense Danbooru-style image tags for NoobAI.

Rules:
- Output ONLY lowercase English tags, comma-separated, no explanations
- Be thorough: include clothing, expression, setting, lighting, and pose
- Keep ALL subjects, actions, and directional words intact
- Do NOT add quality tags (masterpiece, absurdres, newest, etc.)

Examples:
Input: 一個女孩右手拿傘
Output: 1girl, solo, holding umbrella, right hand, open umbrella, standing, looking at viewer, smile, rain, wet hair, outdoors, puddle, blush

Input: 少女坐在咖啡廳窗邊看書
Output: 1girl, solo, sitting, reading book, cafe, window, sunlight, warm lighting, cozy, book, table, long hair, casual clothes

Input: {prompt}
Output:"""

_ILLUSTRIOUS_TEMPLATE = """\
Convert the Chinese description into anime semantic tags for Illustrious XL.

Rules:
- Output ONLY lowercase English tags, comma-separated, no explanations
- Use anime-appropriate semantic vocabulary
- Keep ALL subjects, actions, and directional words intact (右手 → right hand)
- Do NOT add quality tags (masterpiece, highres, newest, etc.)

Examples:
Input: 一個女孩右手拿傘
Output: 1girl, solo, holding umbrella, right hand, umbrella, standing, detailed eyes, anime coloring

Input: 少年與少女在夕陽下並肩走路
Output: 1boy, 1girl, walking, side by side, sunset, warm colors, silhouette, romantic atmosphere

Input: {prompt}
Output:"""


# ── Style config ──────────────────────────────────────────────────────────────

STYLE_CONFIG: dict[PromptStyle, dict] = {
    PromptStyle.SDXL: {
        "quality_prefix": "masterpiece, best quality, high quality",
        "negative": (
            "low quality, blurry, watermark, text, signature, bad anatomy, "
            "extra limbs, deformed, ugly, duplicate, worst quality"
        ),
        # Strip quality tags the LLM might still output + score tags from other styles
        "banned_tags": _QUALITY_TAGS_GENERIC | _QUALITY_TAGS_SCORE,
        "llm_template": _SDXL_TEMPLATE,
    },
    PromptStyle.PONY: {
        "quality_prefix": "score_9, score_8_up, score_7_up",
        "negative": "score_6, score_5, score_4, bad anatomy, ugly, watermark, text",
        "banned_tags": _QUALITY_TAGS_GENERIC | _QUALITY_TAGS_SCORE,
        "llm_template": _PONY_TEMPLATE,
    },
    PromptStyle.FLUX: {
        "quality_prefix": "",
        "negative": "",
        "banned_tags": _QUALITY_TAGS_GENERIC | _QUALITY_TAGS_SCORE | _SD_SYNTAX_TAGS,
        "llm_template": _FLUX_TEMPLATE,
    },
    PromptStyle.NOOBAI: {
        "quality_prefix": "masterpiece, best quality, newest, absurdres",
        "negative": (
            "lowres, bad anatomy, bad hands, text, error, missing fingers, "
            "extra digit, fewer digits, cropped, worst quality, low quality"
        ),
        "banned_tags": _QUALITY_TAGS_GENERIC | _QUALITY_TAGS_NOOBAI | _QUALITY_TAGS_SCORE,
        "llm_template": _NOOBAI_TEMPLATE,
    },
    PromptStyle.ILLUSTRIOUS: {
        "quality_prefix": "masterpiece, best quality, newest, highres",
        "negative": "lowres, worst quality, low quality, ugly, watermark",
        "banned_tags": _QUALITY_TAGS_GENERIC | _QUALITY_TAGS_ILLUSTRIOUS | _QUALITY_TAGS_SCORE,
        "llm_template": _ILLUSTRIOUS_TEMPLATE,
    },
}
