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


# P2：quality_prefix 可能含 SD 權重語法，如 "(highres, absurdres, very aesthetic:0.8)"
# 或單一 "(newest:0.6)"。_sync_banned_tags 純逗號 split 會把整組拆成 "(highres" 等破碎
# 字串，banned_tags 比對永遠失敗、LLM 仍可能吐出重複的 highres/absurdres 灌爆正向。
# 這裡先把 "(tag1, tag2:0.8)" 展開成 "tag1, tag2"（丟權重與外層括號），再交給逐一 split。
_WEIGHT_GROUP_RE = re.compile(r'\(([^()]+):[\d.]+\)')


class PromptStyle(str, Enum):
    SDXL        = "sdxl"
    PONY        = "pony"
    FLUX        = "flux"
    NOOBAI      = "noobai"
    ILLUSTRIOUS = "illustrious"
    ANYTHINGXL  = "anythingxl"
    # 2026-07-25 (AC-1)：Anima（Cosmos-Predict2-2B 衍生，非 SDXL 架構）。
    # 必須與 workflow_builder._detect_style 的 UNETLoader fallback 同批上線——
    # 先補 fallback 而未補此 enum 時，PromptStyle("anima") 會拋 ValueError。
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

# Anima 蒼白 tag 待用清單（2026-07-23 決策③：**不進 banned_tags**，僅記錄）。
# 這組去飽和 tag 是 Anima 出圖「洗白／蒼白空靈」的主因（非 FP8，見 07-23 開發清單 §一）。
# 使用者要蒼白風時仍可手動帶入，故不封鎖。觸發條件：日後洗白復發，才考慮併入 banned
# 或改為 UI 警示。此常數目前未被引用，屬刻意保留的文件化清單。
_PALE_TAGS_ANIMA_WATCHLIST = {
    "pale skin", "fair skin", "pale color", "pastel colors", "limited palette",
    "blue theme", "white theme", "yellow theme",
}

_YEAR_TAGS = {"newest", "recent", "mid", "early", "old"}
_RATING_TAGS_ANYTHINGXL = set()

_QUALITY_TAGS_ANYTHINGXL = {
    "masterpiece", "best quality", "great quality", "good quality",
    "normal quality", "low quality", "worst quality",
}

# 線稿／未上色參考圖的視覺屬性：這些描述的是輸入素材，不是期望生成的彩色人設圖。
# S7.1（2026-07-13）：原枚舉式 set 被新變體不斷繞過（colorless eyes / line art style skin /
# no iris detail / simple line art outline …打地鼠）。改 regex「含即丟」，由 compiler
# _sanitize_to_list 對每個 tag 做 search，涵蓋全部舊枚舉＋未來變體。
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

_ILLUSTRIOUS_TEMPLATE = f"""[TASK]
Convert Chinese descriptions into anime semantic tags for Illustrious XL.

[CRITICAL RULES]
- VOCABULARY: Use anime-appropriate semantic vocabulary.
- ANTI-LEAK: Translate ONLY what the input states. NEVER copy vocabulary, effects, props, or settings from the EXAMPLES below into your output (e.g. do not add magic, glowing, particles, forest, fantasy) unless the input itself mentions them.
{_DANBOORU_COMMON_RULES}

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


_ANIMA_TEMPLATE = f"""[TASK]
Convert Chinese descriptions into anime danbooru tags for Anima (Cosmos-Predict2 based).

[CRITICAL RULES]
- VOCABULARY: Use standard danbooru anime tags. Anima is trained on danbooru-style captions.
- ANTI-LEAK: Translate ONLY what the input states. NEVER copy vocabulary, props, or settings
  from the EXAMPLES below into your output unless the input itself mentions them.
- NO-PALE: Do NOT add desaturating tags (pale skin, fair skin, pastel colors, limited palette,
  or any colour-theme tag such as blue theme / white theme / yellow theme). They wash the image
  out. Only keep them if the input explicitly asks for that look.
- NO-SAFETY: Do NOT add rating tags (safe, sensitive, questionable, explicit). Handled elsewhere.
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
        # 2026-06-23：fabricatedXL/Illustrious 主路。原 newest, highres 偏弱、negative 過薄；
        # 換成實測有效組合並補強手指/解剖/壓縮假影。newest/highres 仍留在 banned_tags
        # （_QUALITY_TAGS_ILLUSTRIOUS）阻止 LLM 自行吐出。
        quality_prefix="masterpiece, best quality, amazing quality, absurdres",
        negative=(
            "worst quality, low quality, lowres, bad anatomy, bad hands, bad proportions, "
            "missing fingers, extra digits, fewer digits, fused fingers, jpeg artifacts, "
            "signature, watermark, username, text, blurry, cropped, extra limbs"
        ),
        banned_tags=_QUALITY_TAGS_GENERIC | _QUALITY_TAGS_ILLUSTRIOUS | _QUALITY_TAGS_SCORE | _SUBJECT_COUNT_TAGS,
        llm_template=_ILLUSTRIOUS_TEMPLATE,
    ),
    # Anima family（2026-07-25 AC-1）。配方來源：doc/2026-07-23 開發清單 §4.3「定案配方」，
    # 由附件二（＝A3）實測基準拆解而來，非 Anima 官方 prompt（官方那組是「蒼白空靈」美學，
    # 追它會洗白，見 07-23 §一）。三項已拍板決策：
    #   ① 不做 safety 分級 → quality_prefix 不含 safe/sensitive/explicit
    #   ② 光影組（bokeh/depth of field/backlighting/light particles）不寫死 → 交由角色/場景 prompt
    #   ③ 蒼白 tag 不擋 → 僅記錄於 _PALE_TAGS_ANIMA_WATCHLIST
    PromptStyle.ANIMA: StyleConfig(
        quality_prefix="masterpiece, best quality, absurdres, ultra detailed, high contrast",
        # 前段為通用品質負向；後段 overexposed…pale 為 **Anima 專屬對比項**——
        # 07-22 實測：缺這段時 Anima 出圖必偏白、低對比（官方負向與 07-20 規劃皆無此段）。
        negative=(
            "worst quality, low quality, lowres, score_1, score_2, score_3, blurry, "
            "jpeg artifacts, bad anatomy, watermark, artist name, "
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


# ── Prompt 擴寫 stage2 system prompt（G1-2）─────────────────────────────────────
# 移植自 F:\wk\workflow 的 V37 Advanced 三變體共用的 booru tag upsampler system prompt：
# 把稀疏 danbooru tags 擴寫成 10-50 個更密的 tags，補足畫面資訊密度（畫風一致由此承擔，
# 讓 CN 可降權只管結構）。規則對齊 V37：不可改主體、不可加 meta/quality、僅輸出 tag 字串。
# ⚠️ 本常數為依規劃文件重建版本，最終措辭以 G1-1 手動 A/B 驗證結果為準。
# {tags} 由 compiler 填入 stage1 清洗後的 tag 串；輸出經同一 _sanitize_to_list 守門。
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
