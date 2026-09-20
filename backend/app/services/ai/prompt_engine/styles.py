# 註解索引：本檔 [CN-xxx] 標記的完整根因記錄見 doc/reference/CODE_NOTES.md
"""
Prompt style definitions — one config per model family.

Each style defines:
  quality_prefix  — prepended to final prompt (e.g. score tags for Pony)
  negative        — model-appropriate negative prompt
  banned_tags     — tags stripped from LLM output before quality_prefix is added
                    The StyleConfig validator automatically adds quality_prefix tags here.
  llm_template    — few-shot prompt sent to Ollama
"""
from __future__ import annotations

import re
from enum import Enum
from pydantic import BaseModel, model_validator


# [CN-023] quality_prefix 可能含 SD 權重語法，純逗號 split 會拆爛 → 先展開再 split
_WEIGHT_GROUP_RE = re.compile(r'\(([^()]+):[\d.]+\)')


class PromptStyle(str, Enum):
    SDXL        = "sdxl"
    PONY        = "pony"
    FLUX        = "flux"
    NOOBAI      = "noobai"
    ILLUSTRIOUS = "illustrious"
    ANYTHINGXL  = "anythingxl"
    # [CN-024] anima enum 必須與 workflow_builder._detect_style 的 UNETLoader fallback 同批上線
    ANIMA       = "anima"


class StyleConfig(BaseModel):
    quality_prefix: str
    negative: str
    banned_tags: set[str]
    llm_template: str

    @model_validator(mode="after")
    def _sync_banned_tags(self) -> StyleConfig:
        """Automatically add quality_prefix tags to banned_tags to prevent duplication.

        P2：先展開 SD 權重群組語法（見 _WEIGHT_GROUP_RE），再逐一 split，避免權重寫法
        把 tag 拆爛成不會命中 banned_set 的破碎字串。
        """
        if self.quality_prefix:
            expanded = _WEIGHT_GROUP_RE.sub(r'\1', self.quality_prefix)
            extra_banned = {t.strip() for t in expanded.split(",") if t.strip()}
            self.banned_tags.update(extra_banned)
        return self


# ── Tag Sets ──────────────────────────────────────────────────────────────────

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

# [CN-025] Anima 蒼白 tag 待用清單：刻意不進 banned_tags，僅文件化保留

_YEAR_TAGS = {"newest", "recent", "mid", "early", "old"}
_RATING_TAGS_ANYTHINGXL = set()

_QUALITY_TAGS_ANYTHINGXL = {
    "masterpiece", "best quality", "great quality", "good quality",
    "normal quality", "low quality", "worst quality",
}

# [CN-026] 線稿視覺屬性改 regex「含即丟」——枚舉式 set 被新變體不斷繞過
_LINEART_ARTIFACT_RE = re.compile(
    r'colou?rless|uncolou?red|unpainted|no colou?r|no iris'
    r'|no skin colou?r|line[ -]?art|achromatic'
    r'|pencil sketch|sketch style|sketch outline|monochrome sketch',
    re.IGNORECASE,
)

_SD_SYNTAX_TAGS = {
    "masterpiece", "best quality", "score_9", "ultra detailed",
    "1girl", "1boy", "source_anime", "source_furry",
}

_SUBJECT_COUNT_TAGS = {
    "1girl", "1boy", "1woman", "1man", "2girls", "2boys", "solo",
}


# ── Template Components (DRY) ─────────────────────────────────────────────────

_COLOR_RULES = (
    "- COLOR: Translate ALL colors EXACTLY. "
    "白=white, 金=golden, 銀=silver, 紅=red, 藍=blue, 紫=purple, 綠=green, 粉=pink, 棕=brown, 黑=black. "
    "NEVER substitute or invent colors not in the input."
)

_DANBOORU_COMMON_RULES = f"""- FORMAT: Output ONLY comma-separated tags. NO key-value pairs (e.g., no "name:", no "age:").
- GENDER: Always start with a gender tag (1boy, 1girl, 2boys, etc.) based on the input.
- NO-GO: No "Output:" prefix, No "Tags:" prefix, No explanations, No capital letters.
- CONFLICT: "外貌與個性" (Priority Traits) and "服裝設定" (Outfit Setting) ALWAYS override "視覺參考特徵" (Visual Traits). (a) If Visual says "pink jacket" but Outfit Setting says "grey combat suit", output ONLY the Outfit Setting outfit — discard the Visual outfit entirely. (b) If Visual says "purple eyes" but Priority Traits says "brown hair" / "異色瞳", use Priority Traits only.
- MODIFIERS: Pay extreme attention to hair length and style modifiers. "短雙馬尾" = "short hair, short twin tails" or "short hair, short ponytail".
- HETEROCHROMIA: If "異色瞳" is present, output "heterochromia" plus BOTH eye colors as PLURAL danbooru tags. Example: 左眼紅右眼綠 → heterochromia, red eyes, green eyes. NEVER write a side in parentheses (no "red eye (left)") — parentheses are weight syntax and corrupt the prompt.
- PASSTHROUGH: English tags already present in the input MUST be copied to the output verbatim, unchanged.
- STRICT: Do NOT add clothing, accessories, or background details that are NOT mentioned in the input.
- QUALITY: Do NOT add quality tags (e.g., masterpiece, best quality). They are handled elsewhere.
{_COLOR_RULES}"""


# ── Per-style LLM templates ───────────────────────────────────────────────────

_SDXL_TEMPLATE = f"""[TASK]
Convert Chinese descriptions into clean, lowercase Danbooru tags for Stable Diffusion SDXL.

[CRITICAL RULES]
{_DANBOORU_COMMON_RULES}
- PRESERVE: Keep subjects, actions, orientation (right/left hand), and ALL color descriptors exactly as given.

[EXAMPLES]
Input: 一個女孩右手拿傘
Output: 1girl, solo, holding umbrella, right hand, standing, outdoors

Input: 白色長捲髮，金色眼睛，天使氣質的少女
Output: 1girl, solo, white hair, long hair, curly hair, golden eyes, angel, angelic, ethereal, gentle expression

Input: 銀髮紫瞳的魔法師少年
Output: 1boy, solo, silver hair, purple eyes, mage, magic, robe, serious expression

Input: 左眼為紅色，右眼為綠色的異色瞳少女，短褐色頭髮
Output: 1girl, solo, heterochromia, red eyes, green eyes, brown hair, short hair

[INPUT]
{{prompt}}

[RESULT]"""

_PONY_TEMPLATE = f"""[TASK]
Convert Chinese descriptions into clean, lowercase Danbooru tags for Pony Diffusion.

[CRITICAL RULES]
{_DANBOORU_COMMON_RULES}
- STYLE: Always include 'source_anime' for anime-style descriptions.

[EXAMPLES]
Input: 一個女孩右手拿傘
Output: 1girl, solo, holding umbrella, right hand, standing, source_anime

Input: 銀髮少女拿著武士刀，背景是紅色的月亮
Output: 1girl, solo, silver hair, holding sword, katana, red moon, night, source_anime

Input: 黑髮黑眼的冷漠少年，頭髮及肩，瀏海蓋眼，綁短馬尾，身材精壯
Output: male focus, black hair, black eyes, shoulder-length hair, hair over eyes, bangs, short ponytail, cold expression, expressionless, muscular, athletic build, source_anime

[INPUT]
{{prompt}}

[RESULT]"""

_FLUX_TEMPLATE = """[TASK]
Rewrite the Chinese description as a natural, cinematic English image prompt for Flux.

[CRITICAL RULES]
- GROUNDING: First, list the MANDATORY FACTS extracted from the input in your mind.
- FORMAT: Write 1-2 natural English sentences that incorporate ALL mandatory facts.
- NO-GO: Do NOT use comma-separated tag format. Do NOT use SD-specific syntax (1girl, score_9).
- PRESERVE: Keep all directional details (right hand, left hand), colors, and hair/eye styles exactly as described.
- TONE: Be descriptive, cinematic, and clear.

[EXAMPLES]
Input: 一個女孩右手拿傘
Mandatory Facts: girl, right hand, holding umbrella
Output: A young girl standing outdoors, holding a colorful umbrella in her right hand, with a calm and serene expression.

Input: 賽博龐克風格的街道，雨天，霓虹燈招牌
Mandatory Facts: cyberpunk, street, rainy, neon signs
Output: A cinematic shot of a rainy cyberpunk street at night, illuminated by vibrant neon signs and glowing advertisements.

[INPUT]
{prompt}

[RESULT]"""

_NOOBAI_TEMPLATE = f"""[TASK]
Convert Chinese descriptions into dense, descriptive Danbooru tags for NoobAI.

[CRITICAL RULES]
- DEPTH: Be thorough; include clothing, expression, setting, lighting, and pose.
{_DANBOORU_COMMON_RULES}

[EXAMPLES]
Input: 一個女孩右手拿傘
Output: 1girl, solo, holding umbrella, right hand, standing, looking at viewer, smile, rain, wet hair, outdoors, puddle, blush

Input: 一個身穿盔甲的騎士在戰場上
Output: 1boy, solo, knight, full armor, holding sword, battlefield, fire, smoke, debris, intense expression, dynamic pose, cinematic lighting

[INPUT]
{{prompt}}

[RESULT]"""

_ANYTHINGXL_TEMPLATE = f"""[TASK]
Convert Chinese descriptions into structured Danbooru tags for Anything XL.

[CRITICAL RULES]
{_DANBOORU_COMMON_RULES}
- META: Always include 'source_anime' near the end as the meta tag.

[EXAMPLES]
Input: 一個女孩右手拿傘
Output: 1girl, solo, holding umbrella, right hand, standing, outdoors, source_anime

Input: 左眼為紅色，右眼為綠色的異色瞳女孩
Output: 1girl, solo, heterochromia, red eyes, green eyes, looking at viewer, source_anime

[INPUT]
{{prompt}}

[RESULT]"""

# [CN-027] SKIN/SCOPE 抽成兩 family 共用常數；措辭必須維持正向，不得回到列舉禁用詞
_SKIN_SCOPE_RULES = """- SKIN: Output a skin-tone tag ONLY when the input names one. If the input says nothing about
  skin, output no skin tag at all. When the input does name a light or fair complexion, write
  it as `porcelain skin`.
- SCOPE: Tag what the character IS, never how the picture looks overall. No image-mood and
  no colour-scheme descriptors.
"""

_ILLUSTRIOUS_TEMPLATE = f"""[TASK]
Convert Chinese descriptions into anime semantic tags for Illustrious XL.

[CRITICAL RULES]
- VOCABULARY: Use anime-appropriate semantic vocabulary.
- ANTI-LEAK: Translate ONLY what the input states. NEVER copy vocabulary, effects, props, or settings from the EXAMPLES below into your output (e.g. do not add magic, glowing, particles, forest, fantasy) unless the input itself mentions them.
{_SKIN_SCOPE_RULES}{_DANBOORU_COMMON_RULES}

[EXAMPLES]
Input: 白色長捲髮，金色眼睛，天使氣質的少女
Output: 1girl, solo, white hair, long hair, curly hair, golden eyes, angel, angelic, gentle expression

Input: 左眼為紅色，右眼為綠色的異色瞳少女，短褐色頭髮，灰色戰鬥服
Output: 1girl, solo, heterochromia, red eyes, green eyes, brown hair, short hair, grey combat suit, tactical vest

Input: 銀髮紫瞳的魔法師少年
Output: 1boy, solo, silver hair, purple eyes, mage, robe, serious expression

[INPUT]
{{prompt}}

[RESULT]"""


# [CN-028] NO-PALE 列舉式禁用詞本身就是 pale skin 的來源 → 改寫為正向指令，template 內零蒼白字面
_ANIMA_TEMPLATE = f"""[TASK]
Convert Chinese descriptions into anime danbooru tags for Anima (Cosmos-Predict2 based).

[CRITICAL RULES]
- VOCABULARY: Use standard danbooru anime tags. Anima is trained on danbooru-style captions.
- ANTI-LEAK: Translate ONLY what the input states. NEVER copy vocabulary, props, or settings
  from the EXAMPLES below into your output unless the input itself mentions them.
{_SKIN_SCOPE_RULES}- NO-SAFETY: Do NOT add rating tags (safe, sensitive, questionable, explicit). Handled elsewhere.
{_DANBOORU_COMMON_RULES}

[EXAMPLES]
Input: 藍色長髮雙馬尾，藍色眼睛的少女，微笑
Output: 1girl, solo, blue hair, long hair, twintails, blue eyes, smile, closed mouth, looking at viewer

Input: 左眼為紅色，右眼為綠色的異色瞳少女，短褐色頭髮，灰色戰鬥服
Output: 1girl, solo, heterochromia, red eyes, green eyes, brown hair, short hair, grey combat suit, tactical vest

Input: 銀髮紫瞳的魔法師少年
Output: 1boy, solo, silver hair, purple eyes, mage, robe, serious expression

[INPUT]
{{prompt}}

[RESULT]"""


# ── Style Config ──────────────────────────────────────────────────────────────

STYLE_CONFIG: dict[PromptStyle, StyleConfig] = {
    PromptStyle.SDXL: StyleConfig(
        # 2026-06-23：對齊實測有效組合（amazing quality, absurdres）；原 high quality 偏弱。
        quality_prefix="masterpiece, best quality, amazing quality, absurdres",
        # 補強手指/解剖/壓縮假影防護（原版缺 bad hands/fingers/jpeg → 爛手與死白膚色擋不住）。
        negative=(
            "worst quality, low quality, lowres, bad anatomy, bad hands, bad proportions, "
            "missing fingers, extra digits, fewer digits, fused fingers, jpeg artifacts, "
            "signature, watermark, username, text, blurry, cropped, extra limbs, deformed"
        ),
        banned_tags=_QUALITY_TAGS_GENERIC | _QUALITY_TAGS_SCORE | _SUBJECT_COUNT_TAGS,
        llm_template=_SDXL_TEMPLATE,
    ),
    PromptStyle.PONY: StyleConfig(
        quality_prefix="score_9, score_8_up, score_7_up",
        negative="score_6, score_5, score_4, bad anatomy, ugly, watermark, text",
        banned_tags=_QUALITY_TAGS_GENERIC | _QUALITY_TAGS_SCORE | _SUBJECT_COUNT_TAGS,
        llm_template=_PONY_TEMPLATE,
    ),
    PromptStyle.FLUX: StyleConfig(
        quality_prefix="",
        negative="",
        banned_tags=_QUALITY_TAGS_GENERIC | _QUALITY_TAGS_SCORE | _SD_SYNTAX_TAGS,
        llm_template=_FLUX_TEMPLATE,
    ),
    PromptStyle.NOOBAI: StyleConfig(
        quality_prefix="masterpiece, best quality, newest, absurdres",
        negative=(
            "lowres, bad anatomy, bad hands, text, error, missing fingers, "
            "extra digit, fewer digits, cropped, worst quality, low quality"
        ),
        banned_tags=_QUALITY_TAGS_GENERIC | _QUALITY_TAGS_NOOBAI | _QUALITY_TAGS_SCORE | _SUBJECT_COUNT_TAGS,
        llm_template=_NOOBAI_TEMPLATE,
    ),
    PromptStyle.ILLUSTRIOUS: StyleConfig(
        # [CN-029] Illustrious 主路配方：newest/highres 留在 banned_tags 阻止 LLM 自行吐出
        quality_prefix="masterpiece, best quality, amazing quality, absurdres",
        negative=(
            "worst quality, low quality, lowres, bad anatomy, bad hands, bad proportions, "
            "missing fingers, extra digits, fewer digits, fused fingers, jpeg artifacts, "
            "signature, watermark, username, text, blurry, cropped, extra limbs"
        ),
        banned_tags=_QUALITY_TAGS_GENERIC | _QUALITY_TAGS_ILLUSTRIOUS | _QUALITY_TAGS_SCORE | _SUBJECT_COUNT_TAGS,
        llm_template=_ILLUSTRIOUS_TEMPLATE,
    ),
    # [CN-030] Anima 配方來自附件二實測基準，非官方 prompt（官方那組追了會洗白）；三項決策見 CODE_NOTES
    PromptStyle.ANIMA: StyleConfig(
        quality_prefix="masterpiece, best quality, absurdres, ultra detailed, high contrast",
        # [CN-031] Anima 負向三段結構；刻意不加裸 shadow（會壓掉角色身上的 shading）
        negative=(
            "worst quality, low quality, lowres, score_1, score_2, score_3, blurry, "
            "jpeg artifacts, bad anatomy, watermark, artist name, "
            "drop shadow, cast shadow, floor, ground, reflection, "
            "overexposed, washed out, faded, low contrast, blown out highlights, pale"
        ),
        banned_tags=_QUALITY_TAGS_GENERIC | _QUALITY_TAGS_SCORE | _SUBJECT_COUNT_TAGS,
        llm_template=_ANIMA_TEMPLATE,
    ),
    PromptStyle.ANYTHINGXL: StyleConfig(
        quality_prefix="newest, masterpiece, best quality",
        negative=(
            "lowres, bad anatomy, bad hands, text, error, missing fingers, "
            "extra digit, fewer digits, cropped, worst quality, low quality, "
            "normal quality, jpeg artifacts, signature, watermark, username, "
            "blurry, artist name"
        ),
        banned_tags=(
            _QUALITY_TAGS_ANYTHINGXL | _YEAR_TAGS | _RATING_TAGS_ANYTHINGXL
            | _QUALITY_TAGS_SCORE | _SUBJECT_COUNT_TAGS
        ),
        llm_template=_ANYTHINGXL_TEMPLATE,
    ),
}


# [CN-032] booru upsampler system prompt 移植自 V37；措辭以 G1-1 手動 A/B 結果為準
UPSAMPLE_SYSTEM_PROMPT = """[TASK]
You are a Danbooru tag upsampler for anime Stable Diffusion. Expand the given SHORT tag list
into a denser, richer set of danbooru tags that describe the SAME subject and scene.

[RULES]
- SUBJECT LOCK: Never change, drop, or contradict any given tag. Keep the exact subject,
  character identity, gender, hair/eye colors, and outfit. Only ADD complementary tags.
- ADD: expression, pose, composition, lighting, background/setting, minor accessories, and
  view — but only what is consistent with the given tags. Do NOT invent a different character.
- SCALE: output roughly 10-50 comma-separated danbooru tags total (including the originals).
- FORMAT: lowercase, comma-separated tags ONLY. No key-value pairs, no sentences.
- NO-GO: NO quality/meta tags (masterpiece, best quality, score_9, absurdres, newest — handled
  elsewhere). NO "Output:"/"Tags:" prefix. NO explanations. NO capital letters.

[INPUT TAGS]
{tags}

[RESULT]"""
