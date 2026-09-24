# 註解索引：本檔 [CN-xxx] 標記的完整根因記錄見 doc/reference/CODE_NOTES.md
"""Prompt Compiler — 中文描述 → 對應模型的最終 prompt [FD-076]"""
from __future__ import annotations

import inspect
import logging
import re
import threading
import time

from app.core.config import (
    PROMPT_UPSAMPLE_ENABLED,
    PROMPT_UPSAMPLE_MODEL,
    PROMPT_MAX_BODY_TAGS,
    PROMPT_CACHE_TTL_SEC,
)
from app.services.ai import ollama_client
from app.services.ai.prompt_engine.styles import (
    PromptStyle,
    STYLE_CONFIG,
    UPSAMPLE_SYSTEM_PROMPT,
    _WEIGHT_GROUP_RE,
    _LINEART_ARTIFACT_RE,
    _SUBJECT_COUNT_TAGS,
)
from app.services.ai.prompt_engine import lexicon
from app.services.ai.prompt_engine.content_guard import is_explicit_tag, nsfw_guard_enabled

logger = logging.getLogger(__name__)


def _extract_color_anchors(text: str, anchor_source: str = "") -> list[str]:
    """Deterministically extract hair/eye traits from Chinese text [FD-077]"""
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

# [CN-012] 眼色一律輸出 danbooru 複數 tag；`{color} eye (left)` 會被 CLIPTextEncode 當權重群組
_DIRECTIONAL_EYE_RE = re.compile(r'\beyes?\s*\((?:left|right)\)', re.IGNORECASE)
# 把 LLM 仍可能吐出的舊格式 `{color} eye(s) (left/right)` 就地轉成複數色 tag。
_DIRECTIONAL_EYE_CAPTURE_RE = re.compile(r'\b([a-z]+)\s+eyes?\s*\((?:left|right)\)', re.IGNORECASE)
_EYE_SHAPE_KEEP = {
    # 形狀
    "big", "large", "small", "thin", "narrow", "wide", "slender", "droopy",
    "hooded", "almond", "round", "tareme", "tsurime",
    # 開闔／狀態（表情，非顏色）
    "closed", "half-closed", "open", "wide-eyed", "crossed", "rolling",
    # 質感（品質詞，不是顏色）
    "detailed", "glowing", "sparkling", "shiny", "expressive",
}
_EYE_TAIL_RE = re.compile(r'^(?P<mods>.+?)\s+eyes?$', re.IGNORECASE)


def _is_eye_color_tag(tag: str) -> bool:
    """`tag` 是否為「眼睛顏色」類 tag（→ 應被權威雙色取代） [FD-078]"""
    core = tag.lower().strip("() ").strip()
    m = _EYE_TAIL_RE.match(core)
    if not m:
        return False
    mods = m.group("mods").replace("-", " ").split()
    keep = {w.replace("-", " ") for w in _EYE_SHAPE_KEEP}
    return not any(w in _EYE_SHAPE_KEEP or w in keep for w in mods)


def _normalize_directional_eye_tags(tags: list[str]) -> list[str]:
    """把 `{color} eye (left/right)` 就地換成 danbooru 複數 `{color} eyes`，並去重 [FD-079]"""
    out: list[str] = []
    seen = {t.lower().strip("() ") for t in tags if not _DIRECTIONAL_EYE_RE.search(t)}
    for t in tags:
        m = _DIRECTIONAL_EYE_CAPTURE_RE.search(t)
        if not m:
            out.append(t)
            continue
        plural = f"{m.group(1).lower()} eyes"
        if plural not in seen:
            seen.add(plural)
            out.append(plural)
    return out


def _inject_heterochromia(tags: list[str], text: str, anchor_source: str = "") -> list[str]:
    """Detect 異色瞳 in source text and guarantee correct heterochromia tags are present [FD-080]"""
    combined = f"{text} {anchor_source}"
    if not _HETERO_DETECT_RE.search(combined):
        return tags

    tag_lowers = {t.lower().strip("() ") for t in tags}
    to_prepend: list[str] = []

    if "heterochromia" not in tag_lowers:
        to_prepend.append("heterochromia")

    # 輸出 danbooru 標準 tag；括號格式會被 CLIPTextEncode 當權重群組解析
    wanted: list[str] = []
    for side_re in (_LEFT_EYE_RE, _RIGHT_EYE_RE):
        m = side_re.search(combined)
        if m:
            eng = lexicon.COLOR_MAP.get(m.group(1))
            if eng and f"{eng} eyes" not in wanted:
                wanted.append(f"{eng} eyes")

    if wanted:
        # 先清掉所有既有眼色 tag（含 LLM 只挑一色、或挑錯色的情況），再放上權威版本，
        # 避免「兩個來源各給一色」導致三色以上互相稀釋。
        tags = [
            t for t in tags
            if not _is_eye_color_tag(t)
            and not _DIRECTIONAL_EYE_RE.search(t)
        ]
        to_prepend.extend(wanted)

    return to_prepend + tags


def _recall_dropped_outfit_terms(tags: list[str], source_text: str) -> list[str]:
    """個人詞庫 tag 已替換進 LLM 輸入、輸出卻漏掉時補回末尾。
    只補不刪、不猜未登錄詞彙。"""
    src_lower = source_text.lower()
    tag_lowers = {t.lower().strip("() ") for t in tags}
    to_append: list[str] = []
    for term in lexicon.personal_term_map_tags():
        term_lower = term.lower().strip()
        if term_lower and term_lower in src_lower and not _term_in_tags(term_lower, tag_lowers):
            to_append.append(term)
            tag_lowers.add(term_lower)
    return tags + to_append if to_append else tags


def _term_in_tags(term_lower: str, tag_lowers: set[str]) -> bool:
    """[CN-117] 詞庫 tag 以「整詞」出現在任一輸出 tag 內即算已翻出：修飾語併入後 LLM 會吐
    `black pencil skirt`，只比完全相等會再補一個重複的 `pencil skirt`。"""
    pat = re.compile(rf"(?<![a-z]){re.escape(term_lower)}(?![a-z])")
    return any(pat.search(t) for t in tag_lowers)


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


# [CN-013] 白皙系收斂成 porcelain skin；刻意放行 very/deathly/sickly pale，不動其他膚色
_FAIR_SKIN_TAGS = frozenset({
    "pale", "pale skin", "pale complexion",
    "fair skin", "fair complexion", "fair-skinned", "fair skinned",
    "white skin", "light skin", "porcelain",
})
_FAIR_SKIN_CANON = "porcelain skin"


def _canonicalize_fair_skin(tags: list[str], style) -> list[str]:
    """把白皙系膚色 tag 統一成 porcelain skin 並去重；命中時留 log 供歸因。"""
    result: list[str] = []
    hits: list[str] = []
    emitted = False
    for t in tags:
        core = t.strip().lower().strip("()")
        if core in _FAIR_SKIN_TAGS or core == _FAIR_SKIN_CANON:
            hits.append(core)
            if not emitted:
                result.append(_FAIR_SKIN_CANON)
                emitted = True
            # 重複的白皙變體直接丟棄
        else:
            result.append(t)
    if hits and hits != [_FAIR_SKIN_CANON]:
        logger.info(
            "[skin-canon] %s: fair-skin canonicalized %s -> %s",
            getattr(style, "value", style), sorted(set(hits)), _FAIR_SKIN_CANON,
        )
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
    """Detect semantic traits in source text, guarantee correct positive tags [FD-081]"""
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


def _upsample_tags(
    base_tags: list[str], model: str, banned_set: set[str]
) -> list[str]:
    """擴寫 stage2：把稀疏 tags 擴寫成更密的 danbooru tags。
    base_tags 一律保留在前、只補新增；呼叫失敗回原 tags。"""
    if not base_tags:
        return base_tags

    prompt = UPSAMPLE_SYSTEM_PROMPT.format(tags=", ".join(base_tags))
    raw = ollama_client.generate(
        prompt,
        model=model,
        options={"num_predict": 200, "temperature": 0.4},
        keep_alive=0,  # 同主編譯：編完即退 VRAM，避免餓死 ComfyUI 主 pass。
    )
    if ollama_client.is_error(raw):
        return base_tags

    extra = _sanitize_to_list(_extract_output(raw), banned_set)
    seen = {t.lower().strip("() ") for t in base_tags}
    merged = list(base_tags)
    for t in extra:
        key = t.lower().strip("() ")
        if key not in seen:
            seen.add(key)
            merged.append(t)
    return merged


def _apply_body_budget(
    tags: list[str], max_tags: int, protected: int
) -> list[str]:
    """token 預算：超過 max_tags 時從尾端（擴寫新增部分）砍；前 protected 個一律保留。
    max_tags<=0 時不動。"""
    if max_tags <= 0 or len(tags) <= max_tags:
        return tags
    return tags[: max(max_tags, protected)]


def _compile_impl(
    text: str,
    style: PromptStyle = PromptStyle.SDXL,
    model: str = ollama_client.DEFAULT_TEXT_MODEL,
    anchor_text: str = "",
    quality_prefix_override: str | None = None,
    negative_override: str | None = None,
    quality_suffix_override: str | None = None,
    negative_extra_override: str | None = None,
    keep_subject: bool = False,
) -> tuple[str, str]:
    """中文創作文字 → SD prompt。
    keep_subject：保留主體 tag（1girl, solo…）並移到最前；人設圖由 gender_prefix 補主體故傳 False，
    文字→生圖沒有補主體步驟必須傳 True。"""
    # 0. 個人詞庫：LLM 翻譯前做確定性替換，降低專有詞誤譯
    _mapped = lexicon.apply_personal_term_map(text)
    if _mapped != text:
        # [CN-117] UI 的「中文描述」是替換前；這行才是實際送進 LLM 的文字（診斷詞庫切字問題用）
        logger.info("[prompt-log] term-map 後送 LLM: %s", _mapped)
    text = _mapped

    config = STYLE_CONFIG[style]

    # [CN-014] override 帶入的 quality tags 要動態補進 local banned，否則去重失效
    banned = config.banned_tags
    _ov = ", ".join(filter(None, [quality_prefix_override, quality_suffix_override]))
    if _ov:
        _expanded = _WEIGHT_GROUP_RE.sub(r"\1", _ov)
        banned = banned | {t.strip().lower() for t in _expanded.split(",") if t.strip()}
    if keep_subject:
        banned = banned - _SUBJECT_COUNT_TAGS

    # 1. 構建 Prompt 並呼叫 LLM
    prompt = config.llm_template.format(prompt=text)
    raw_response = ollama_client.generate(
        prompt,
        model=model,
        options={"num_predict": 250, "temperature": 0.3},
        keep_alive=0,  # 編完即退 VRAM，避免文字模型殘留拖慢 ComfyUI 主 pass
    )
    if raw_response.startswith("["):
        raise RuntimeError(raw_response)

    # 2. 擷取輸出與標籤清洗
    extracted = _extract_output(raw_response)
    cleaned_tags = _sanitize_to_list(extracted, banned)

    # [CN-015] 選配擴寫 stage2 + token 預算；預設關閉時整段 no-op，FLUX 不套
    if PROMPT_UPSAMPLE_ENABLED and style is not PromptStyle.FLUX:
        _protected = len(cleaned_tags)  # 原始翻譯 tags = identity 錨，預算優先保留
        _up_model = PROMPT_UPSAMPLE_MODEL or model
        cleaned_tags = _upsample_tags(cleaned_tags, _up_model, banned)
        cleaned_tags = _apply_body_budget(cleaned_tags, PROMPT_MAX_BODY_TAGS, _protected)

    # 3. 處理防幻覺與特徵修正 (非自然語言的 tag 類模型才執行)
    _extra_neg = ""
    if style is not PromptStyle.FLUX:
        combined_text = f"{text} {anchor_text} {extracted}"
        
        # [CN-016] 內容腦補類過濾已停用（還原方式見 CODE_NOTES）
        if not _HETERO_DETECT_RE.search(f"{text} {anchor_text}"):
            cleaned_tags = [
                t for t in cleaned_tags
                if t.lower().strip("() ") not in {"heterochromia", "odd eyes"}
                and not _DIRECTIONAL_EYE_RE.search(t)
            ]
        cleaned_tags = _inject_heterochromia(cleaned_tags, text, anchor_source=anchor_text)
        # 收斂殘留的括號格式眼色 tag（LLM 對非異色瞳角色也可能吐出）
        cleaned_tags = _normalize_directional_eye_tags(cleaned_tags)

        # [CN-017] 服裝關鍵詞召回：只補詞庫已塞進輸入卻漏掉的 tag，不做腦補；必須放管線最後
        cleaned_tags = _recall_dropped_outfit_terms(cleaned_tags, text)

        # 白皙系膚色統一詞；放在管線最末，召回補回的 tag 也會被收斂
        cleaned_tags = _canonicalize_fair_skin(cleaned_tags, style)

        # keep_subject：主體放 body 最前（Anima 官方順序 quality/safety → 主體 → 其餘；
        # 異色瞳注入會把眼色 prepend 到最前，不重排主體就會被擠到後面）。
        if keep_subject:
            _subj = [t for t in cleaned_tags if t.lower() in _SUBJECT_COUNT_TAGS]
            cleaned_tags = _subj + [t for t in cleaned_tags if t.lower() not in _SUBJECT_COUNT_TAGS]

        # [CN-018] [停用] Group B Anchor 系統（抽色→清衝突→重排加權）——還原碼見 CODE_NOTES

        # A+B 停用後：直接採用清洗後的 tag 原序（仍保留 Group C 結構清理：sanitize/dedup）。
        final_body = ", ".join(cleaned_tags)
    else:
        final_body = extracted

    # 4. 拼接 quality_prefix
    prefix = quality_prefix_override if quality_prefix_override else config.quality_prefix
    positive = f"{prefix}, {final_body}" if prefix and final_body else (prefix or final_body)

    # [CN-019] workflow 級 quality_suffix 接在 body 後、構圖 tags 前：ComfyUI 分塊編碼，放尾端會被稀釋
    if quality_suffix_override:
        positive = f"{positive}, {quality_suffix_override}" if positive else quality_suffix_override

    # 5. Negative preset + context-aware suppression
    negative = negative_override if negative_override else config.negative
    # [CN-020] negative_extra 是「補充」語義，workflow profile 的 negative 才是「取代」
    if negative_extra_override:
        negative = f"{negative}, {negative_extra_override}" if negative else negative_extra_override
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

# [CN-021] 括號替代說明過濾：排除含 `:` 的權重語法，<7 字元保留（(left)/(right) 方向標）
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

        # banned_set 已剝除權重語法，比對鍵也須剝除才會命中
        normalized = re.sub(r':[\d.]+$', '', t_clean.lower().strip("()")).strip()

        if _LINEART_ARTIFACT_RE.search(t_clean):
            continue

        # [CN-118] 露骨 tag（受 NSFW_GUARD_ENABLED 控制）；未成年情境在注入前另行強制
        if nsfw_guard_enabled() and is_explicit_tag(t_clean):
            continue

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


# [CN-022] 快取刻意包一層而非改 _compile_impl；key 用 inspect 綁定實參，新參數自動納入
_CACHE_MAX = 64
_compile_cache: dict[str, tuple[float, tuple[str, str]]] = {}
_compile_cache_lock = threading.Lock()
_COMPILE_SIG = inspect.signature(_compile_impl)


def _compile_cache_key(args, kwargs) -> str:
    bound = _COMPILE_SIG.bind(*args, **kwargs)
    bound.apply_defaults()
    return repr([(k, repr(v)) for k, v in sorted(bound.arguments.items())])


def prompt_cache_hit(*args, **kwargs) -> bool:
    """compile 是否會命中快取（命中就不必搶 Ollama VRAM focus）；快取停用時恆為 False。
    預留 margin 秒，避免探測後剛好過期而未搶 focus 就呼叫 Ollama。"""
    if PROMPT_CACHE_TTL_SEC <= 0:
        return False
    try:
        key = _compile_cache_key(args, kwargs)
    except TypeError:
        return False
    with _compile_cache_lock:
        hit = _compile_cache.get(key)
    if hit is None:
        return False
    return (time.monotonic() - hit[0]) < max(PROMPT_CACHE_TTL_SEC - 5.0, 0.0)


def compile(*args, **kwargs) -> tuple[str, str]:
    """Main entrypoint to compile Chinese creative text into fine-tuned SD prompts [FD-082]"""
    if PROMPT_CACHE_TTL_SEC <= 0:
        return _compile_impl(*args, **kwargs)

    key = _compile_cache_key(args, kwargs)
    now = time.monotonic()
    with _compile_cache_lock:
        hit = _compile_cache.get(key)
        if hit is not None and now - hit[0] < PROMPT_CACHE_TTL_SEC:
            logger.info("[prompt-cache] hit —— 略過 Ollama 編譯（ComfyUI 模型免卸載重載）")
            return hit[1]

    result = _compile_impl(*args, **kwargs)

    with _compile_cache_lock:
        _compile_cache[key] = (time.monotonic(), result)
        while len(_compile_cache) > _CACHE_MAX:
            _compile_cache.pop(next(iter(_compile_cache)))
    return result
