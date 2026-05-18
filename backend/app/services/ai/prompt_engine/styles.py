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
    ANYTHINGXL  = "anythingxl"


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

# Anything XL year tags + rating tags — strip from LLM output to prevent duplication
_YEAR_TAGS = {"newest", "recent", "mid", "early", "old"}
_RATING_TAGS_ANYTHINGXL = set()

_QUALITY_TAGS_ANYTHINGXL = {
    "masterpiece", "best quality", "great quality", "good quality",
    "normal quality", "low quality", "worst quality",
}

_SD_SYNTAX_TAGS = {
    "masterpiece", "best quality", "score_9", "ultra detailed",
    "1girl", "1boy", "source_anime", "source_furry",
}

# Subject-count tags — always injected by gender_prefix in art_generate.py,
# so strip them from LLM output to prevent duplication.
_SUBJECT_COUNT_TAGS = {
    "1girl", "1boy", "1woman", "1man", "2girls", "2boys", "solo",
}


# ── Per-style LLM templates (English for better instruction-following) ────────

_SDXL_TEMPLATE = """[TASK]
Convert Chinese descriptions into clean, lowercase Danbooru tags for Stable Diffusion SDXL.

[CRITICAL RULES]
- FORMAT: Output ONLY comma-separated tags. NO key-value pairs (e.g., no "name:", no "age:").
- GENDER: Always start with a gender tag (1boy, 1girl, 2boys, etc.) based on the input.
- COLOR: Translate ALL colors EXACTLY. 白=white, 金=golden, 銀=silver, 紅=red, 藍=blue, 紫=purple, 綠=green, 粉=pink, 棕=brown, 黑=black. NEVER substitute or invent colors not in the input.
- NO-GO: No "Output:" prefix, No "Tags:" prefix, No explanations, No capital letters.
- STRICT: Do NOT add clothing, accessories, or background details that are NOT mentioned in the input.
- QUALITY: Do NOT add quality tags (e.g., masterpiece, best quality). They are handled elsewhere.
- PRESERVE: Keep subjects, actions, orientation (right/left hand), and ALL color descriptors exactly as given.

[EXAMPLES]
Input: 一個女孩右手拿傘
Output: 1girl, solo, holding umbrella, right hand, standing, outdoors

Input: 白色長捲髮，金色眼睛，天使氣質的少女
Output: 1girl, solo, white hair, long hair, curly hair, golden eyes, angel, angelic, ethereal, gentle expression

Input: 銀髮紫瞳的魔法師少年
Output: 1boy, solo, silver hair, purple eyes, mage, magic, robe, serious expression

Input: 左眼為紅色，右眼為綠色的異色瞳女孩
Output: 1girl, solo, heterochromia, red eye (left), green eye (right), looking at viewer

Input: 黑髮黑眼的冷漠少年，頭髮及肩，瀏海蓋眼，綁短馬尾，身材精壯
Output: male focus, black hair, black eyes, shoulder-length hair, hair over eyes, bangs, short ponytail, cold expression, expressionless, muscular, athletic build

[INPUT]
{prompt}

[RESULT]"""

_PONY_TEMPLATE = """[TASK]
Convert Chinese descriptions into clean, lowercase Danbooru tags for Pony Diffusion.

[CRITICAL RULES]
- FORMAT: Output ONLY comma-separated tags. NO key-value pairs (e.g., no "name:", no "age:").
- GENDER: Always start with a gender tag (1boy, 1girl, 2boys, etc.) based on the input.
- STYLE: Always include 'source_anime' for anime-style descriptions.
- COLOR: Translate ALL colors EXACTLY. 白=white, 金=golden, 銀=silver, 紅=red, 藍=blue, 紫=purple, 綠=green, 粉=pink, 棕=brown, 黑=black. NEVER substitute or invent colors not in the input.
- NO-GO: No "Output:" prefix, No "Tags:" prefix, No explanations, No capital letters.
- STRICT: Do NOT add clothing, accessories, or background details that are NOT mentioned in the input.
- QUALITY: Do NOT add masterpiece, best quality, or score tags. They are handled elsewhere.

[EXAMPLES]
Input: 一個女孩右手拿傘
Output: 1girl, solo, holding umbrella, right hand, standing, source_anime

Input: 白色長捲髮，金色眼睛，天使氣質的少女
Output: 1girl, solo, white hair, long hair, curly hair, golden eyes, angel, angelic, ethereal, source_anime

Input: 銀髮少女拿著武士刀，背景是紅色的月亮
Output: 1girl, solo, silver hair, holding sword, katana, red moon, night, source_anime

Input: 左眼為紅色，右眼為綠色的異色瞳女孩
Output: 1girl, solo, heterochromia, red eye (left), green eye (right), looking at viewer, source_anime

Input: 黑髮黑眼的冷漠少年，頭髮及肩，瀏海蓋眼，綁短馬尾，身材精壯
Output: male focus, black hair, black eyes, shoulder-length hair, hair over eyes, bangs, short ponytail, cold expression, expressionless, muscular, athletic build, source_anime

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
- COLOR: Translate ALL colors EXACTLY. 白=white, 金=golden, 銀=silver, 紅=red, 藍=blue, 紫=purple, 綠=green, 粉=pink, 棕=brown, 黑=black. NEVER substitute or invent colors not in the input.
- NO-GO: No "Output:" prefix, No explanations, No capital letters.
- STRICT: Do NOT add clothing, accessories, or background details that are NOT mentioned in the input.
- QUALITY: Do NOT add quality tags (masterpiece, absurdres, newest, etc.).

[EXAMPLES]
Input: 一個女孩右手拿傘
Output: 1girl, solo, holding umbrella, right hand, standing, looking at viewer, smile, rain, wet hair, outdoors, puddle, blush

Input: 白色長捲髮，金色眼睛，天使氣質的少女
Output: 1girl, solo, white hair, long hair, curly hair, golden eyes, angel wings, angelic, halo, soft lighting, gentle smile, ethereal glow

Input: 一個身穿盔甲的騎士在戰場上
Output: 1boy, solo, knight, full armor, holding sword, battlefield, fire, smoke, debris, intense expression, dynamic pose, cinematic lighting

[INPUT]
{prompt}

[RESULT]"""

_ANYTHINGXL_TEMPLATE = """[TASK]
Convert Chinese descriptions into structured Danbooru tags for Anything XL.

[CRITICAL RULES]
- FORMAT: Output ONLY comma-separated tags.
- GENDER: Always start with a gender tag (1boy, 1girl, 2boys, etc.)
- META: Always include 'source_anime' near the end as the meta tag.
- COLOR: Translate ALL colors EXACTLY. 白=white, 金=golden, 銀=silver, 紅=red, 藍=blue, 紫=purple, 綠=green, 粉=pink, 棕=brown, 黑=black. NEVER substitute or invent colors not in the input.
- NO-GO: No "Output:" prefix, No explanations, No capital letters.
- STRICT: Do NOT add clothing, accessories, or background not mentioned in the input.
- QUALITY: Do NOT add quality tags (masterpiece, best quality, etc.), year tags (newest, recent, etc.). They are handled elsewhere.

[EXAMPLES]
Input: 一個女孩右手拿傘
Output: 1girl, solo, holding umbrella, right hand, standing, outdoors, source_anime

Input: 白色長捲髮，金色眼睛，天使氣質的少女
Output: 1girl, solo, white hair, long hair, curly hair, golden eyes, angel, halo, angelic, ethereal, gentle expression, source_anime

Input: 銀髮紫瞳的魔法師少年
Output: 1boy, solo, silver hair, purple eyes, mage, magic, robe, serious expression, source_anime

Input: 左眼為紅色，右眼為綠色的異色瞳女孩
Output: 1girl, solo, heterochromia, red eye (left), green eye (right), looking at viewer, source_anime

Input: 黑髮黑眼的冷漠少年，頭髮及肩，瀏海蓋眼，綁短馬尾，身材精壯
Output: male focus, black hair, black eyes, shoulder-length hair, hair over eyes, bangs, short ponytail, cold expression, expressionless, muscular, athletic build, source_anime

[INPUT]
{prompt}

[RESULT]"""

_ILLUSTRIOUS_TEMPLATE = """[TASK]
Convert Chinese descriptions into anime semantic tags for Illustrious XL.

[CRITICAL RULES]
- FORMAT: Output ONLY comma-separated tags.
- VOCABULARY: Use anime-appropriate semantic vocabulary.
- COLOR: Translate ALL colors EXACTLY. 白=white, 金=golden, 銀=silver, 紅=red, 藍=blue, 紫=purple, 綠=green, 粉=pink, 棕=brown, 黑=black. NEVER substitute or invent colors not in the input.
- NO-GO: No "Output:" prefix, No explanations, No capital letters.
- STRICT: Do NOT add clothing, accessories, or background details that are NOT mentioned in the input.
- QUALITY: Do NOT add quality tags (masterpiece, highres, newest, etc.).

[EXAMPLES]
Input: 一個女孩右手拿傘
Output: 1girl, solo, holding umbrella, right hand, standing, detailed eyes, anime coloring

Input: 白色長捲髮，金色眼睛，天使氣質的少女
Output: 1girl, solo, white hair, long hair, curly hair, golden eyes, angel, angelic aura, halo, soft light, gentle smile

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
        "banned_tags": _QUALITY_TAGS_GENERIC | _QUALITY_TAGS_SCORE | _SUBJECT_COUNT_TAGS,
        "llm_template": _SDXL_TEMPLATE,
    },
    PromptStyle.PONY: {
        "quality_prefix": "score_9, score_8_up, score_7_up",
        "negative": "score_6, score_5, score_4, bad anatomy, ugly, watermark, text",
        "banned_tags": _QUALITY_TAGS_GENERIC | _QUALITY_TAGS_SCORE | _SUBJECT_COUNT_TAGS,
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
        "banned_tags": _QUALITY_TAGS_GENERIC | _QUALITY_TAGS_NOOBAI | _QUALITY_TAGS_SCORE | _SUBJECT_COUNT_TAGS,
        "llm_template": _NOOBAI_TEMPLATE,
    },
    PromptStyle.ILLUSTRIOUS: {
        "quality_prefix": "masterpiece, best quality, newest, highres",
        "negative": "lowres, worst quality, low quality, ugly, watermark",
        "banned_tags": _QUALITY_TAGS_GENERIC | _QUALITY_TAGS_ILLUSTRIOUS | _QUALITY_TAGS_SCORE | _SUBJECT_COUNT_TAGS,
        "llm_template": _ILLUSTRIOUS_TEMPLATE,
    },
    # Anything XL: structured template with year tag + quality + rating
    # Negative: no high-weight terms (official warns against (ugly:2) and NegativeXL)
    PromptStyle.ANYTHINGXL: {
        "quality_prefix": "newest, masterpiece, best quality",
        "negative": (
            "lowres, bad anatomy, bad hands, text, error, missing fingers, "
            "extra digit, fewer digits, cropped, worst quality, low quality, "
            "normal quality, jpeg artifacts, signature, watermark, username, "
            "blurry, artist name"
        ),
        "banned_tags": (
            _QUALITY_TAGS_ANYTHINGXL | _YEAR_TAGS | _RATING_TAGS_ANYTHINGXL
            | _QUALITY_TAGS_SCORE | _SUBJECT_COUNT_TAGS
        ),
        "llm_template": _ANYTHINGXL_TEMPLATE,
    },
}
