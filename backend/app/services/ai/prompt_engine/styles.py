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

_SDXL_TEMPLATE = """[TASK]
Convert Chinese descriptions into clean, lowercase Danbooru tags for Stable Diffusion SDXL.

[CRITICAL RULES]
- FORMAT: Output ONLY comma-separated tags. NO key-value pairs (e.g., no "name:", no "age:").
- GENDER: Always start with a gender tag (1boy, 1girl, 2boys, etc.) based on the input.
- NO-GO: No "Output:" prefix, No "Tags:" prefix, No explanations, No capital letters.
- STRICT: Do NOT add clothing, accessories, or background details that are NOT mentioned in the input.
- QUALITY: Do NOT add quality tags (e.g., masterpiece, best quality). They are handled elsewhere.
- PRESERVE: Keep subjects, actions, and orientation (right/left hand).

[EXAMPLES]
Input: 一個女孩右手拿傘
Output: 1girl, solo, holding umbrella, right hand, standing, outdoors

Input: 賽博龐克風格的街道，雨天，霓虹燈招牌
Output: cyberpunk, street, raining, neon lights, sign, cinematic lighting, cityscape

Input: 左眼為紅色，右眼為綠色的異色瞳女孩
Output: 1girl, solo, heterochromia, red eye (left), green eye (right), looking at viewer

Input: 一名15歲的冷酷少年，黑色短髮，黑眼，穿著高中制服
Output: 1boy, solo, male focus, short hair, black hair, black eyes, school uniform, closed mouth, cold expression, 15 years old

[INPUT]
{prompt}

[RESULT]"""

_PONY_TEMPLATE = """[TASK]
Convert Chinese descriptions into clean, lowercase Danbooru tags for Pony Diffusion.

[CRITICAL RULES]
- FORMAT: Output ONLY comma-separated tags. NO key-value pairs (e.g., no "name:", no "age:").
- GENDER: Always start with a gender tag (1boy, 1girl, 2boys, etc.) based on the input.
- STYLE: Always include 'source_anime' for anime-style descriptions.
- NO-GO: No "Output:" prefix, No "Tags:" prefix, No explanations, No capital letters.
- STRICT: Do NOT add clothing, accessories, or background details that are NOT mentioned in the input.
- QUALITY: Do NOT add masterpiece, best quality, or score tags. They are handled elsewhere.

[EXAMPLES]
Input: 一個女孩右手拿傘
Output: 1girl, solo, holding umbrella, right hand, standing, source_anime

Input: 銀髮少女拿著武士刀，背景是紅色的月亮
Output: 1girl, solo, silver hair, holding sword, katana, red moon, night, source_anime

Input: 左眼為紅色，右眼為綠色的異色瞳女孩
Output: 1girl, solo, heterochromia, red eye (left), green eye (right), looking at viewer, source_anime

Input: 一名15歲的冷酷少年，黑色短髮，黑眼，穿著高中制服
Output: 1boy, solo, male focus, short hair, black hair, black eyes, school uniform, closed mouth, cold expression, 15 years old, source_anime

[INPUT]
{prompt}

[RESULT]"""

_FLUX_TEMPLATE = """[TASK]
Rewrite the Chinese description as a natural, cinematic English image prompt for Flux.

[CRITICAL RULES]
- FORMAT: Write 1-2 natural English sentences.
- NO-GO: Do NOT use comma-separated tag format. Do NOT use SD-specific syntax (1girl, score_9).
- PRESERVE: Keep all directional details (right hand, left hand).
- TONE: Be descriptive, cinematic, and clear.

[EXAMPLES]
Input: 一個女孩右手拿傘
Output: A young girl standing outdoors, holding a colorful umbrella in her right hand, with a calm and serene expression.

Input: 賽博龐克風格的街道，雨天，霓虹燈招牌
Output: A cinematic shot of a rainy cyberpunk street at night, illuminated by vibrant neon signs and glowing advertisements.

Input: 左眼為紅色，右眼為綠色的異色瞳女孩
Output: A close-up portrait of a girl with striking heterochromia; her left eye is a vivid red while her right eye is a bright green.

[INPUT]
{prompt}

[RESULT]"""

_NOOBAI_TEMPLATE = """[TASK]
Convert Chinese descriptions into dense, descriptive Danbooru tags for NoobAI.

[CRITICAL RULES]
- FORMAT: Output ONLY comma-separated tags.
- DEPTH: Be thorough; include clothing, expression, setting, lighting, and pose.
- NO-GO: No "Output:" prefix, No explanations, No capital letters.
- STRICT: Do NOT add clothing, accessories, or background details that are NOT mentioned in the input.
- QUALITY: Do NOT add quality tags (masterpiece, absurdres, newest, etc.).

[EXAMPLES]
Input: 一個女孩右手拿傘
Output: 1girl, solo, holding umbrella, right hand, standing, looking at viewer, smile, rain, wet hair, outdoors, puddle, blush

Input: 一個身穿盔甲的騎士在戰場上
Output: 1boy, solo, knight, full armor, holding sword, battlefield, fire, smoke, debris, intense expression, dynamic pose, cinematic lighting

[INPUT]
{prompt}

[RESULT]"""

_ILLUSTRIOUS_TEMPLATE = """[TASK]
Convert Chinese descriptions into anime semantic tags for Illustrious XL.

[CRITICAL RULES]
- FORMAT: Output ONLY comma-separated tags.
- VOCABULARY: Use anime-appropriate semantic vocabulary.
- NO-GO: No "Output:" prefix, No explanations, No capital letters.
- STRICT: Do NOT add clothing, accessories, or background details that are NOT mentioned in the input.
- QUALITY: Do NOT add quality tags (masterpiece, highres, newest, etc.).

[EXAMPLES]
Input: 一個女孩右手拿傘
Output: 1girl, solo, holding umbrella, right hand, standing, detailed eyes, anime coloring

Input: 森林中的精靈，手中散發著魔法光芒
Output: 1girl, solo, elf, long hair, pointed ears, forest, glowing hands, magic, particle effects, soft lighting, fantasy art style

[INPUT]
{prompt}

[RESULT]"""


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
