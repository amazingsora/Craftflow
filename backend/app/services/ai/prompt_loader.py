"""
Prompt file loader with hardcoded fallback defaults.

Usage:
    from app.services.ai.prompt_loader import load_prompt

    # No variables — returns raw text:
    prompt = load_prompt("art/sketch_critique")

    # With variables — uses str.format_map():
    prompt = load_prompt("character/generate_summary", name="Alice", raw_notes="...")

File convention:
    Prompt files live in backend/app/prompts/{key}.txt
    Variables use {var_name} syntax.
    Literal braces in JSON examples must be doubled: {{ and }}
"""
from __future__ import annotations

from pathlib import Path

_PROMPTS_DIR = Path(__file__).parent.parent.parent / "prompts"

# ---------------------------------------------------------------------------
# Hardcoded defaults — used when the corresponding .txt file is absent.
# ---------------------------------------------------------------------------
_DEFAULTS: dict[str, str] = {

    # ── Art ──────────────────────────────────────────────────────────────────

    "art/sketch_critique": """\
你是一位專業的插畫指導老師，請分析這張**草稿**的線條品質。
注意：這是草稿階段，請只聚焦在線條結構問題，不要評論上色或完成度。

請依以下結構回應（使用繁體中文）：

## 整體草稿狀態
一句話描述草稿的整體狀況（例如：結構清晰但線條猶豫、比例大致正確但細節需補強等）。

## 逐部位線條分析
僅列出有問題的部位，沒問題可略過：

- **眼睛 / 五官**：位置比例是否正確？線條是否乾淨有力？有無歪斜？
- **頭髮**：流向是否自然？外輪廓線是否流暢？分組是否清晰？
- **手部 / 手指**：結構是否正確？關節比例？
- **身體 / 姿勢**：重心是否穩定？肩頸腰髖比例？
- **衣物 / 皺褶**：皺褶走向是否符合動作？線條是否過多或過少？
- **輪廓線**：外輪廓是否清晰定義？哪些部位輪廓線交叉或斷裂？

## 具體修改建議
請給出 2-3 點具體的修改步驟，指導創作者如何清線或修正人體結構。
""",

    "art/finished_critique": """\
你是一位嚴苛但專業的插畫評審。請對這張**完稿作品**進行全方位的視覺品質審查。

請依以下結構回應（使用繁體中文）：

## 視覺衝擊力
構圖、剪影與主體是否突出？

## 光影與色彩
光源方向是否明確？色彩搭配（主色、輔色、點綴色）是否和諧？固有色與環境色處理？

## 骨架與人體結構
在完稿衣物下，人體骨架（特別是雙肩、骨盆、四肢關節）是否合理？

## 細節與精緻度
線條收尾、材質表現（金屬、布料、皮膚等）的完成度評估。

## 綜合改進方向
如果這張圖要達到商業級發佈標準，最急需修改的三個地方是什麼？
""",

    "art/line_color": """\
你是一位色彩設計師。這是一張**乾淨的線稿**，請為它規劃 3 套不同的配色方案。
請考慮角色的氣質與可能的場景氛圍。

請依以下結構回應（使用繁體中文）：

## 方案一：經典/預設風格
- **主色 (60%)**：
- **輔色 (30%)**：
- **點綴色 (10%)**：
- **氛圍描述**：

## 方案二：對比/強烈風格
- **主色 (60%)**：
- **輔色 (30%)**：
- **點綴色 (10%)**：
- **氛圍描述**：

## 方案三：特殊/情境風格（如夜間、魔法、黃昏）
- **主色 (60%)**：
- **輔色 (30%)**：
- **點綴色 (10%)**：
- **氛圍描述**：
""",

    "art/composition_analysis": """\
你是一位精準的草稿轉提示詞大師與構圖專家。請分析這張**草稿**並回答使用者的問題。

使用者問題：{user_question}

請嚴格依循以下結構回應（使用繁體中文）：

[ADVICE]
（請在此處詳細回答使用者的問題，給出關於視角、光源、佈局或人體結構的具體優化建議。）

[PROMPT]
（請根據草稿內容，將其轉譯為適合 Stable Diffusion 生成的英文標籤(tags)。請遵守以下硬性規則：
1. 只描述草稿中「肉眼可見」的特徵，例如髮型、姿勢與表情（例如有微笑請務必加 smile）。
2. 對於服裝，請依據草稿的剪裁客觀描述（例如：vest, hoodie, sleeveless），絕不可無中生有添加西裝(suit)、禮服、夾克等無關風格。
3. 預設背景為純白或簡單背景（white background, simple background），禁止腦補任何複雜場景。
4. 格式請完全使用逗號分隔的標籤，不要有任何自然語言解釋。）
""",

    "art/describe_illustration": """\
請用繁體中文簡短描述這張插畫的內容、場景與視覺重點（100字以內）。
""",

    "art/composition_advisor": """\
你是一位專業的插畫創作顧問。請用繁體中文回答以下問題：

{question}

請給出具體、實用的建議。
""",

    # ── Character ────────────────────────────────────────────────────────────

    "character/generate_summary": """\
你是一位專業的角色設定整理師，正在為小說角色「{name}」建立角色檔案。

以下是作者提供的原始筆記：
{raw_notes}

請將上述資料整理成一份結構清晰的角色設定檔，使用繁體中文，格式如下：

## 角色概述
（一段話總結這個角色的核心定位與魅力，50字以內）

## 外貌與氣質
（外貌特徵、穿著風格、整體氣質）

## 性格特質
（核心個性、優點、缺點或矛盾面）

## 行為模式
（面對事情的反應方式、習慣、癖好）

## 說話方式
（語氣、常用詞彙、說話特色）

## 創作備注
（對作者有用的額外提示、潛在故事線等）

請只輸出格式化內容，不要加入任何前言或說明。
""",

    "character/extract_from_text": """\
[TASK]
Analyze the provided chapter text and extract character profile information for "{character_name}".

[OUTPUT FORMAT]
Return ONLY a valid JSON object. No conversational filler, no markdown code blocks (```json).
Strictly follow this JSON schema:
{{
  "core_traits": "personality traits observed (Traditional Chinese string or null)",
  "behavior_rules": "how this character acts/reacts (Traditional Chinese string or null)",
  "voice_style": "dialogue style and patterns (Traditional Chinese string or null)",
  "notes": "other notable observations (Traditional Chinese string or null)",
  "aliases": ["list of alternative names, nicknames, or titles mentioned"]
}}

[CONSTRAINTS]
1. Content Language: Use Traditional Chinese (繁體中文) for all string values.
2. Objectivity: Only include facts supported by the text. If no info exists for a field, use null.
3. JSON Integrity: Ensure all quotes are escaped. Do not truncate the JSON.

[CHAPTER TEXT]
{chapter_text}

[RESULT]
""",

    "character/design_chat": """\
You are a creative writing assistant helping design a character for a novel.
Character name: {character_name}
{profile_ctx}Author's question: {question}

Provide a helpful, specific, and creative answer in Traditional Chinese (繁體中文).
Focus on the character design question. Keep it concise.
""",

    "character/describe_portrait": """\
[TASK]
Analyze the provided illustration for the character "{character_name}" and create a structured visual profile.

[OUTPUT FORMAT]
Provide a detailed description in Traditional Chinese (繁體中文) using the following sections:

1. **外貌特徵 (Physical Traits)**: 髮色、髮型、瞳色、膚色、五官特色。
2. **身形體態 (Body & Posture)**: 體型描述、身高感、當前姿勢、給人的動態感。
3. **服裝細節 (Outfit & Accessories)**: 衣著層次、材質感、配色方案、特殊配件或武器。
4. **視覺氣質 (Atmosphere)**: 整體氣氛、光影表現、性格映射到視覺上的感覺。

[CONSTRAINTS]
- Be precise: Instead of "long hair", use "silver waist-length straight hair" if applicable.
- Semantic Focus: Focus on details that define the character's identity.
- Language: Use professional Traditional Chinese creative writing vocabulary.

[RESULT]
""",

    # ── Consistency ──────────────────────────────────────────────────────────

    "consistency/check": """\
[TASK]
You are a professional fiction consistency checker. Compare the provided character profiles with the chapter paragraph to detect contradictions.

[CHARACTER SETTINGS]
{char_desc}

[PARAGRAPH TO CHECK]
{paragraph}

[OUTPUT FORMAT]
Return ONLY a valid JSON array of issues. If no contradictions are found, return exactly [].
Do not include markdown code blocks (```json) or conversational text.

Each issue object must follow this schema:
{{
  "type": "character_behavior" | "character_voice",
  "severity": "high" | "medium" | "low",
  "target": "Exact name of the character",
  "reasoning": "Briefly explain the internal logic of why this is a violation in Traditional Chinese",
  "description": "Short summary of the issue in Traditional Chinese",
  "evidence": "Direct quote from the paragraph showing the violation"
}}

[CONSTRAINTS]
1. Severity Scale: 'high' for direct rule violation, 'medium' for subtle OOC (Out of Character), 'low' for minor style drift.
2. Accuracy: Do not hallucinate issues. If behavior matches the profile, do not report it.
3. Language: reasoning and description must be in Traditional Chinese.

[RESULT]
""",

    # ── Rewrite ──────────────────────────────────────────────────────────────

    "rewrite/rewrite": """\
You are a rewriting assistant.

RULES:
- Output ONLY the rewritten paragraph.
- No introductions, no explanations, no quotation marks, no extra text.
- The rewritten paragraph MUST be in the same language as the original.

Instruction: {instruction}
Reason: {reason}

Paragraph:
{paragraph_text}

Rewritten paragraph:
""",

    "rewrite/instruction_gentle": (
        "Lightly revise the paragraph to improve rhythm and clarity. "
        "Preserve the author's voice and structure. Avoid major restructuring."
    ),

    "rewrite/instruction_aggressive": (
        "Rewrite the paragraph to significantly improve rhythm, flow, and impact. "
        "You may restructure sentences and enhance stylistic expression "
        "while preserving original meaning."
    ),
}


def load_prompt(key: str, **kwargs) -> str:
    """Return the prompt for *key*, reading from file first, then falling back to _DEFAULTS."""
    path = _PROMPTS_DIR / f"{key}.txt"
    if path.exists():
        template = path.read_text(encoding="utf-8")
    else:
        template = _DEFAULTS.get(key, "")
    if kwargs:
        return template.format_map(kwargs)
    return template
