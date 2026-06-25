"""
Prompt Compiler — 中文描述 → 對應模型的最終 prompt

流程：
  1. 依 style 選擇 LLM template
  2. Ollama 翻譯生成 raw tags / 描述
  3. Sanitizer：移除 banned_tags
  3.6 服飾防幻覺與情緒召回過濾器（草稿強化核心）
  4. Anchor Extraction：從原始中文抽取髮色/眼色/長度
  5. Semantic Cleaning：移除與 Anchor 衝突的標籤
  6. Reordering & Weighting：按類別排序標籤，並對 Anchor 加權
  7. 拼接 quality_prefix
  8. 回傳 (positive_prompt, negative_prompt)
"""
from __future__ import annotations

import re
from typing import List, Set

from app.services.ai import ollama_client
from app.services.ai.prompt_engine.styles import PromptStyle, STYLE_CONFIG
from app.services.ai.prompt_engine import lexicon


def _extract_color_anchors(text: str, anchor_source: str = "") -> list[str]:
    """
    Deterministically extract hair/eye traits from Chinese text.
    Returns English SD tags like ["white hair", "short hair", "golden eyes"].
    """
    def _scan(src: str) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for m in lexicon.HAIR_RE.finditer(src):
            prefix_zh = m.group(1)
            color_zh = m.group(2)
            style_zh = m.group(3)
            
            eng_color = lexicon.COLOR_MAP.get(color_zh)
            eng_style = lexicon.HAIR_STYLE_MAP.get(style_zh) if style_zh else None
            
            if eng_color:
                tag = f"{eng_color} hair"
                if tag not in seen:
                    seen.add(tag)
                    result.append(tag)
            if eng_style:
                if eng_style not in seen:
                    seen.add(eng_style)
                    result.append(eng_style)

        for m in lexicon.EYE_RE.finditer(src):
            color_zh = m.group(1)
            eng_color = lexicon.COLOR_MAP.get(color_zh)
            if eng_color:
                tag = f"{eng_color} eyes"
                if tag not in seen:
                    seen.add(tag)
                    result.append(tag)
        return result

    res = _scan(text)
    if not res and anchor_source:
        res = _scan(anchor_source)
    return res


_COLOR_ALT_RE = re.compile(
    "|".join(re.escape(k) for k in sorted(lexicon.COLOR_MAP, key=len, reverse=True))
)
_HETERO_DETECT_RE = re.compile(r'異色瞳|異色眼')
_LEFT_EYE_RE  = re.compile(rf'左眼(?:為|是|呈)?({_COLOR_ALT_RE.pattern})')
_RIGHT_EYE_RE = re.compile(rf'右眼(?:為|是|呈)?({_COLOR_ALT_RE.pattern})')


def _inject_heterochromia(tags: list[str], text: str, anchor_source: str = "") -> list[str]:
    """
    Detect 異色瞳 in source text and guarantee correct heterochromia tags are present.
    Runs after LLM translation so it's model-agnostic.
    """
    combined = f"{text} {anchor_source}"
    if not _HETERO_DETECT_RE.search(combined):
        return tags

    tag_lowers = {t.lower().strip("() ") for t in tags}
    to_prepend: list[str] = []

    if "heterochromia" not in tag_lowers:
        to_prepend.append("heterochromia")

    for side, side_re in (("left", _LEFT_EYE_RE), ("right", _RIGHT_EYE_RE)):
        m = side_re.search(combined)
        if m:
            eng = lexicon.COLOR_MAP.get(m.group(1))
            if eng:
                tag = f"{eng} eye ({side})"
                # 比對需與 tag_lowers 同樣正規化（去括號/空白），否則帶括號的 tag 永遠
                # 判定為「不存在」→ 重複注入（眼睛標籤出現兩份的根因）。
                if tag.lower().strip("() ") not in tag_lowers:
                    to_prepend.append(tag)

    # Remove any single-color eye tag that would conflict (e.g. LLM picked one color)
    if to_prepend:
        eye_color_tags = {f"{c} eyes" for c in lexicon.COLOR_MAP.values()}
        tags = [t for t in tags if t.lower().strip("() ") not in eye_color_tags]

    return to_prepend + tags


def _clean_clothing_hallucinations(tags: list[str], text_to_check: str) -> list[str]:
    """
    防幻覺過濾器：偵測是否有休閒/背心類關鍵字，若是，自動拔除腦補的正式西裝標籤。
    """
    lower_src = text_to_check.lower()
    casual_signals = ["背心", "連帽", "休閒", "vest", "hoodie", "tank top", "casual", "sleeveless"]
    
    if any(sig in lower_src for sig in casual_signals):
        formal_banned = {
            "formal suit", "suit", "jacket", "tie", "necktie", "business suit", 
            "professional attire", "formal background", "formal attire", 
            "formal setting", "office", "tuxedo", "blazer", "suited"
        }
        return [t for t in tags if t.strip().lower().strip("()") not in formal_banned]
    return tags


_PALE_SKIN_RE = re.compile(r'^(?:very |deathly |sickly )?pale(?: skin| complexion)?$', re.IGNORECASE)


def _normalize_skin_tone(tags: list[str]) -> list[str]:
    """膚色正規化：人設圖工作流不適用「死白」膚色（多由視覺參考圖帶入）。
    把 pale / pale skin 等替換成自然的 light skin；tan、dark skin 等其他膚色不動。
    """
    result: list[str] = []
    has_light = any(t.strip().lower() == "light skin" for t in tags)
    for t in tags:
        core = t.strip().lower().strip("()")
        if _PALE_SKIN_RE.match(core):
            if not has_light:
                result.append("light skin")
                has_light = True
            # 重複的 pale 變體直接丟棄
        else:
            result.append(t)
    return result


_CONTEXT_BLOCKERS: list[tuple[set[str], set[str], str]] = [
    # (trigger_tags_in_positive, positive_tags_to_remove, extra_negative_to_inject)
    (
        {"noble female", "ojou-sama", "princess"},
        {"maid", "maid outfit", "maid headdress", "waitress", "nurse", "apron", "police"},
        "maid, maid outfit, maid headdress, apron, waitress",
    ),
]


def _inject_traits(tags: list[str], text: str, anchor_source: str = "") -> tuple[list[str], str]:
    """
    Detect semantic traits in source text, guarantee correct positive tags,
    and return extra negative tags for hallucination suppression.

    Returns: (updated_positive_tags, extra_negative_str)
    """
    combined = f"{text} {anchor_source}"
    tag_lowers = {t.lower().strip("() ") for t in tags}
    to_prepend: list[str] = []

    for m in lexicon.TRAIT_RE.finditer(combined):
        trait_zh = m.group(1)
        eng = lexicon.TRAIT_MAP.get(trait_zh)
        if eng:
            for t in eng.split(","):
                t_clean = t.strip()
                if t_clean not in tag_lowers:
                    to_prepend.append(t_clean)
                    tag_lowers.add(t_clean)

    extra_negative_parts: list[str] = []
    for trigger_set, remove_set, neg_injection in _CONTEXT_BLOCKERS:
        if any(k in tag_lowers for k in trigger_set):
            tags = [t for t in tags if t.lower().strip("() ") not in remove_set]
            extra_negative_parts.append(neg_injection)

    return to_prepend + tags, ", ".join(extra_negative_parts)


def compile(
    text: str,
    style: PromptStyle = PromptStyle.SDXL,
    model: str = ollama_client.DEFAULT_TEXT_MODEL,
    anchor_text: str = "",
    quality_prefix_override: str | None = None,
    negative_override: str | None = None,
) -> tuple[str, str]:
    """
    Main entrypoint to compile Chinese creative text into fine-tuned SD prompts.
    """
    config = STYLE_CONFIG[style]

    # 1. 構建 Prompt 並呼叫 LLM
    prompt = config.llm_template.format(prompt=text)
    raw_response = ollama_client.generate(
        prompt,
        model=model,
        options={"num_predict": 250, "temperature": 0.3},
        keep_alive=0,  # 2026-06-21：編完即退 VRAM，避免 9b 殘留餓死 ComfyUI 主 pass（16GB 上主 pass 80s→~35s 穩定）。代價：每次編譯冷載 ~3-5s。
    )
    if raw_response.startswith("["):
        raise RuntimeError(raw_response)

    # 2. 擷取輸出與標籤清洗
    extracted = _extract_output(raw_response)
    cleaned_tags = _sanitize_to_list(extracted, config.banned_tags)

    # 3. 處理防幻覺與特徵修正 (非自然語言的 tag 類模型才執行)
    _extra_neg = ""
    if style is not PromptStyle.FLUX:
        combined_text = f"{text} {anchor_text} {extracted}"
        
        # ── [停用] Group A 內容腦補類過濾（2026-06-24 改用較強視覺/翻譯模型，保留模型原始輸出）──
        # 還原：取消下方對應區塊註解即可。各 helper 函式本體保留未刪。
        #
        # A2 服飾防幻覺過濾（偵測背心/連帽→拔西裝）
        # cleaned_tags = _clean_clothing_hallucinations(cleaned_tags, combined_text)
        #
        # A1 膚色正規化：死白 pale skin → light skin（先前已停用）
        # cleaned_tags = _normalize_skin_tone(cleaned_tags)
        #
        # A3 語義特徵強制注入（下垂眼、大小姐等神韻詞）＋ 女僕幻覺阻斷（_CONTEXT_BLOCKERS）
        # cleaned_tags, _extra_neg = _inject_traits(cleaned_tags, text, anchor_source=anchor_text)
        #
        # A4 情緒/微笑強制召回機制
        # if any(kw in combined_text for kw in ["笑", "微笑", "高興", "smile", "happy"]):
        #     if "smile" not in [t.lower().strip() for t in cleaned_tags]:
        #         cleaned_tags.insert(0, "smile")
        #
        # A5 異色瞳：無來源清除 LLM 幻覺 heterochromia ＋ 有來源強制注入方向眼色
        # if not _HETERO_DETECT_RE.search(f"{text} {anchor_text}"):
        #     cleaned_tags = [t for t in cleaned_tags
        #                     if t.lower().strip("() ") not in {"heterochromia", "odd eyes"}]
        # cleaned_tags = _inject_heterochromia(cleaned_tags, text, anchor_source=anchor_text)

        # ── [停用] Group B Anchor 系統（抽髮/眼色→清衝突→重排並 :1.1 加權，強制覆蓋模型）──
        # 還原：取消下列三段註解，並改回 final_body = _reorder_tags(cleaned_tags, anchors)。
        #
        # B1 Extract authoritative anchors
        # anchors = _extract_color_anchors(text, anchor_source=anchor_text)
        # if _HETERO_DETECT_RE.search(f"{text} {anchor_text}"):
        #     anchors = [a for a in anchors if not a.endswith(" eyes")]
        # B2 Clean conflicts
        # cleaned_tags = _remove_conflicting_tags(cleaned_tags, anchors)
        # B3 Reorder and weight
        # final_body = _reorder_tags(cleaned_tags, anchors)

        # A+B 停用後：直接採用清洗後的 tag 原序（仍保留 Group C 結構清理：sanitize/dedup）。
        final_body = ", ".join(cleaned_tags)
    else:
        final_body = extracted

    # 4. 拼接 quality_prefix
    prefix = quality_prefix_override if quality_prefix_override else config.quality_prefix
    positive = f"{prefix}, {final_body}" if prefix and final_body else (prefix or final_body)

    # 5. Negative preset + context-aware suppression
    negative = negative_override if negative_override else config.negative
    if _extra_neg:
        negative = f"{negative}, {_extra_neg}" if negative else _extra_neg

    return positive.strip(", "), negative


def _extract_output(raw: str) -> str:
    # [RESULT] = template end-marker（LLM 在此之後輸出）；"Output:" = few-shot 示例格式
    for marker in ("[RESULT]", "Output:"):
        if marker in raw:
            return raw.split(marker)[-1].strip()
    return raw.strip()


# ── Sanitize helpers ──────────────────────────────────────────────────────────

# 單一 SD tag 合理上限：超過此長度 = LLM 推理文字洩漏（非合法 tag）
_MAX_TAG_LEN = 80

# 括號替代說明過濾：排除含 `:` 的（SD 權重 (tag:1.1) 不受影響）
# 7+ 字元的無冒號括號 = LLM 替代說明（e.g. "(or horse boots)"）→ 清除
# <7 字元保留：(left)=4, (right)=5 等方向標
_ALT_PAREN_RE = re.compile(r'\s*\([^):]{7,}\)')

# 行尾 dash 推理：" - wait...", " - note:" 等說明 → 清除到行尾
_INLINE_DASH_RE = re.compile(r'\s+-\s+.+$')

# Meta-label：以 `:` 結尾（e.g. "Conflict Resolution:", "Note:"）→ 丟棄整個 tag
_META_LABEL_RE = re.compile(r':\s*$')

# 數字年齡短語（"10 year old", "5 years old"）= 由 _age_body_tags 確定性處理；
# LLM 翻譯版本會與 body_prefix 衝突，且可能產生不適當的外觀描述
_AGE_PHRASE_RE = re.compile(r'\b\d+\s+years?\s+old\b', re.IGNORECASE)

# CJK（中日韓）偵測：含這些字元的 tag = LLM 未完成翻譯／角色名／few-shot 範例反芻洩漏。
# SD 模型對中文 token 無概念 → 丟棄整個 tag。通用安全網,model-agnostic。
_CJK_RE = re.compile(r'[぀-ヿ㐀-䶿一-鿿ｦ-ﾟ]')


def _sanitize_to_list(tag_string: str, banned_set: set[str]) -> list[str]:
    raw_tags = re.split(r'[,\n#]', tag_string)
    cleaned = []
    seen = set()
    for t in raw_tags:
        t_clean = t.strip().strip('."\'')
        if not t_clean:
            continue

        # 斜線替代選項：取第一項（"a/b" → "a"）
        if '/' in t_clean:
            t_clean = t_clean.split('/')[0].strip()
            if not t_clean:
                continue

        # 行尾 dash 推理（" - wait", " - note:"）
        t_clean = _INLINE_DASH_RE.sub('', t_clean).strip()

        # 括號替代說明（7+ 字元無冒號：(or horse boots) → 清除）
        # 保留：(left)/(right)=短方向標；(golden eyes:1.1)=含冒號不受影響
        t_clean = _ALT_PAREN_RE.sub('', t_clean).strip()
        if not t_clean:
            continue

        # 超過長度上限 → LLM 推理文字洩漏，丟棄
        if len(t_clean) > _MAX_TAG_LEN:
            continue

        # 含雙引號 → LLM meta-commentary（e.g. 'but let\'s stick to input: "金眼"'）
        if '"' in t_clean:
            continue

        # 含 CJK（中日韓）→ LLM 未完成翻譯／角色名／範例反芻洩漏，丟棄整個 tag
        if _CJK_RE.search(t_clean):
            continue

        # Meta-label 以 ":" 結尾（e.g. "Conflict Resolution:"）
        if _META_LABEL_RE.search(t_clean):
            continue

        # 數字年齡短語 → 由 _age_body_tags 確定性處理，LLM 版本一律丟棄
        if _AGE_PHRASE_RE.search(t_clean):
            continue

        normalized = t_clean.lower().strip("()")
        if normalized in banned_set or normalized in seen:
            continue
        seen.add(normalized)
        cleaned.append(t_clean)
    return cleaned


def _remove_conflicting_tags(tags: list[str], anchors: list[str]) -> list[str]:
    anchor_colors = set()
    for a in anchors:
        parts = a.split()
        if len(parts) == 2 and parts[1] in ("hair", "eyes"):
            anchor_colors.add((parts[0], parts[1]))

    if not anchor_colors:
        return tags

    filtered = []
    for tag in tags:
        tag_lower = tag.lower()
        conflict = False
        for c_eng, category in anchor_colors:
            # 同時匹配複數與單數（eyes/eye），避免 LLM 生成 "red eye (left)" 形式漏網
            category_variants = {category, category.rstrip('s')} if category.endswith('s') else {category}
            if any(cv in tag_lower for cv in category_variants) and c_eng not in tag_lower:
                conflict = True
                break
        if not conflict:
            filtered.append(tag)
    return filtered


def _reorder_tags(tags: list[str], anchors: list[str]) -> str:
    subjects = []
    clothing = []
    meta = []
    others = []

    anchor_set = {a.lower() for a in anchors}
    clothing_keywords = ["suit", "vest", "shirt", "pants", "dress", "skirt", "jacket", "hoodie", "clothes", "attire"]

    for tag in tags:
        tl = tag.lower()
        if tl in anchor_set:
            continue
        if any(kw in tl for kw in ["1girl", "1boy", "solo", "woman", "man", "character"]):
            subjects.append(tag)
        elif any(kw in tl for kw in clothing_keywords):
            clothing.append(tag)
        elif any(kw in tl for kw in ["background", "monochrome", "lineart", "clean lines", "shading"]):
            meta.append(tag)
        else:
            others.append(tag)

    weighted_anchors = [f"({a}:1.1)" for a in anchors]
    final_list = subjects + weighted_anchors + clothing + others + meta
    return ", ".join(final_list)
