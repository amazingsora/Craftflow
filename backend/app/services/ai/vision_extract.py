"""Vision 抽取與角色 SD 標籤工具。

自 api/art_generate.py 下沉（2026-06-11 A1 階段 1）：
身體 coverage 偵測、視覺特徵抽取（含合併單次呼叫版）、vision 結果快取、
角色屬性（性別/年齡/身高）→ SD 標籤、服裝/髮型詞過濾。
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import Path

from starlette.concurrency import run_in_threadpool

from app.core import state
from app.services.ai import ollama_client as _oc
from app.services.ai.vram_manager import guardian

logger = logging.getLogger(__name__)

# ── Persistent cache file ─────────────────────────────────────────────────────
_VISION_CACHE_FILE = Path(__file__).resolve().parents[3] / "data" / "vision_cache.json"


def _detect_body_coverage(image_bytes: bytes) -> str:
    """
    Use the configured vision model to classify how much of the body is shown.
    Returns: "full" | "partial" | "bust"
    - full:    legs and feet visible
    - partial: torso visible but legs cut off (upper body / three-quarter)
    - bust:    face / shoulders only
    Falls back to "partial" on any error.
    """
    prompt = (
        "Look at this character illustration. How much of the body is shown?\n"
        "Reply with exactly one word:\n"
        "- 'full' if ankles AND feet are clearly visible (complete full body)\n"
        "- 'partial' if knees or ankles are cut off (thighs visible but no feet = partial)\n"
        "- 'bust' if only waist-up or less is shown\n"
        "One word only."
    )
    try:
        result = _oc.analyze_image_bytes(image_bytes, prompt, model=state.get_vision_model())
        result = result.strip().lower().split()[0] if result.strip() else ""
        if result in ("full", "partial", "bust"):
            return result
        # fuzzy match
        if any(k in result for k in ("full", "whole", "entire", "feet", "leg")):
            return "full"
        if any(k in result for k in ("bust", "face", "head", "shoulder")):
            return "bust"
        return "partial"
    except Exception as e:
        logger.warning("[body-coverage] detection failed: %s — defaulting to partial", e)
        return "partial"


def _detect_coverage_and_extract_visual(images_bytes: list[bytes]) -> tuple[str, str]:
    """
    Single Ollama call that combines body-coverage classification and visual feature extraction.
    Returns (coverage: "full"|"partial"|"bust", visual_description: str).
    Saves one full vision-model round-trip vs calling _detect_body_coverage + analyze_multi_images_bytes separately.
    """
    ignore_bg = (
        "【線稿警告】這可能是未上色的鉛筆稿／線稿，且常帶單色（如粉紅色）背景。"
        "規則一：完全忽略背景顏色——粉紅色或任何單色背景，絕不可當成髮色或服裝顏色。"
        "規則二：若畫面只有線條、沒有實際填色，請直接省略顏色、不要寫出任何顏色詞，也不要寫「線稿未上色」這類字樣，"
        "只描述髮型長度與形狀、服裝款式與材質、明顯特徵。嚴禁臆測顏色。只觀察「角色線條內」的特徵。"
    )
    n = len(images_bytes)
    # 2026-06-23：不再抽「體型輪廓」——體型由年齡/身高欄位確定性決定
    # （_age_body_tags/_height_body_tags），vision 版本只會衝突（如 petite vs tall slender）。
    if n == 1:
        feature_q = (
            "B. 視覺特徵（逗號分隔的中文短語，控制在70字以內）：\n"
            "① 髮色與髮型 ② 眼睛顏色 ③ 膚色 ④ 服裝主要顏色與風格 ⑤ 明顯特殊特徵"
        )
    else:
        feature_q = (
            f"B. {n}張圖共同視覺特徵（逗號分隔的中文短語，控制在90字以內）：\n"
            "① 髮色與髮型 ② 眼睛顏色 ③ 膚色 ④ 服裝主要顏色與風格 ⑤ 各圖均出現的特殊特徵"
        )
    prompt = (
        f"{ignore_bg}\n\n"
        "請回答以下兩個問題：\n\n"
        "A. 身體遮蔽程度（只回答一個英文詞，依下列步驟判斷）：\n"
        "  步驟1：畫面最底部有沒有畫出「腳掌、腳趾或鞋子」？\n"
        "    - 有看到腳掌／鞋子 → 'full'\n"
        "    - 沒看到腳掌／鞋子 → 進入步驟2（此時絕不可判 full）\n"
        "  步驟2：（沒有腳的前提下）最多能看到身體到哪裡？\n"
        "    - 看得到大腿、膝蓋或小腿（但沒有腳） → 'partial'\n"
        "    - 只看得到腰部以上（看不到大腿） → 'bust'\n"
        "  ⚠️ 關鍵規則：只要畫面底部沒有腳掌或鞋子，即使角色已畫到大腿、"
        "即使人物佔滿整個畫面高度，都一律判 'partial'，絕對不是 'full'。\n\n"
        f"{feature_q}\n\n"
        "回答格式（嚴格遵守）：\n"
        "COVERAGE: [一個英文詞]\n"
        "FEATURES: [逗號分隔的中文短語]"
    )
    try:
        result = _oc.analyze_multi_images_bytes(
            images_bytes, prompt,
            model=state.get_vision_model(),
            # num_predict 放寬：thinking 類模型需額外 token 才能在推理後吐出格式輸出。
            options={"num_predict": 512, "temperature": 0.1},
            # 2026-07-07 P0：呼叫完即退 VRAM，避免與後續 compile() 的文字模型同時駐留
            # 導致 vram_manager._can_coexist("ollama") 誤判安全（見開發規劃 P0 根因 3）。
            keep_alive=0,
        )
        # 診斷用：印出模型原始回應（含 think 段）→ 判斷回空主因（think 燒光/不照格式/真空回）
        logger.info("[combined-vision] RAW(len=%d): %r", len(result or ""), (result or "")[:300])
        # thinking 類模型（如 Qwen3-VL abliterated）即使送 think:false，response 仍可能
        # 內嵌 <think>…</think>。先去除再解析，避免推理段落污染或排擠格式輸出。
        cleaned = re.sub(r"<think>.*?</think>", "", result or "", flags=re.DOTALL | re.IGNORECASE).strip()

        coverage = ""
        visual = ""
        for line in cleaned.split('\n'):
            line = line.strip()
            if line.upper().startswith('COVERAGE:'):
                parts = line.split(':', 1)
                cov_word = parts[1].strip().lower().split()[0] if len(parts) > 1 and parts[1].strip() else ""
                if cov_word in ("full", "partial", "bust"):
                    coverage = cov_word
                elif any(k in cov_word for k in ("full", "whole", "entire", "feet", "leg")):
                    coverage = "full"
                elif any(k in cov_word for k in ("bust", "face", "head", "shoulder")):
                    coverage = "bust"
            elif line.upper().startswith('FEATURES:'):
                parts = line.split(':', 1)
                visual = parts[1].strip() if len(parts) > 1 else ""

        # Fallback 1：模型沒照 COVERAGE: 格式 → 在全文掃關鍵詞推斷
        if not coverage:
            low = cleaned.lower()
            if any(k in low for k in ("full body", "full-body", "feet", "ankle", "全身", "腳踝")):
                coverage = "full"
            elif any(k in low for k in ("bust", "headshot", "shoulder", "半身", "胸像", "肩")):
                coverage = "bust"
            elif any(k in low for k in ("partial", "thigh", "knee", "大腿", "膝")):
                coverage = "partial"

        # Fallback 2：沒抓到 FEATURES: 但有可用文字 → 取非 coverage 行當特徵
        if not visual and cleaned:
            desc = "\n".join(
                ln.strip() for ln in cleaned.split('\n')
                if ln.strip() and not ln.strip().upper().startswith('COVERAGE:')
            ).strip()
            visual = desc[:120]

        # 防呆：仍判不出 coverage（模型回空/格式不符）→ 預設 full 跳過外擴，
        # 避免視覺模型異常時 silent 觸發 40GB Flux 外擴拖垮速度（Resilient errors）。
        if not coverage:
            logger.warning("[combined-vision] 無法解析 coverage（模型回空或格式不符）→ 預設 full 跳過外擴")
            coverage = "full"

        logger.info("[combined-vision] coverage=%s visual_len=%d", coverage, len(visual))
        return coverage, visual
    except Exception as e:
        logger.warning("[combined-vision] failed: %s — 預設 full/empty（跳過外擴）", e)
        return "full", ""


def _age_gender_tag(gender: str | None, age: int | None) -> str:
    """
    Return the primary SD subject tag(s) based on gender + age.
    Placed at the very front of the positive prompt to anchor subject count.
    Returns empty string when gender is unset.
    """
    if gender == "female":
        base = "1girl" if (age is None or age < 25) else "1woman"
        suffix = ", mature female" if age is not None and age >= 40 else ""
        return base + suffix
    if gender == "male":
        base = "1boy" if (age is None or age < 25) else "1man"
        suffix = ", mature male" if age is not None and age >= 40 else ""
        return base + suffix
    if gender == "neutral":
        return "androgynous"
    return ""


def _age_body_tags(age: int | None) -> str:
    """Convert character age to SD body proportion tags.

    S3（2026-07-13）：≤12 歲檔原本 7 個 tag（child...flat chest, small hands）整串前排
    → 把比例壓成三頭身 chibi（第六輪 H3 實證）。縮為單一 `child`，拔 flat chest；
    15-17 歲檔改空（`teenage girl, youthful` 純稀釋，體型已由 _height_body_tags 承擔）。
    ≤6（toddler）與 13-14 檔維持原樣，未在本次 A/B 範圍。"""
    if age is None:
        return ""
    if age <= 6:
        return "toddler, very young, chubby cheeks, round face"
    if age <= 12:
        return "child"
    if age <= 14:
        return "young girl, youthful, flat chest"
    if age <= 17:
        return ""
    return ""


def _height_body_tags(height: int | None) -> str:
    """Convert character height (cm) to SD stature tags."""
    if height is None:
        return ""
    if height < 130:
        return "very short stature, tiny, small figure"
    if height < 150:
        return "short stature, petite"
    if height < 160:
        return "petite"
    if height < 170:
        return ""
    if height < 180:
        return "tall, long legs"
    return "very tall, long legs"


_CLOTHING_KW = {
    "外套", "大衣", "風衣", "夾克", "上衣", "衫", "褲", "短褲", "長褲",
    "裙", "短裙", "長裙", "服裝", "衣服", "制服", "連帽", "背心",
    "毛衣", "套裝", "腰帶", "圍巾", "手套", "鞋", "靴",
}
_HAIRSTYLE_KW = {
    "馬尾", "雙馬尾", "辮子", "捲髮", "直髮", "髮型", "長髮",
}
# S8（2026-07-13）：線稿膚色洩漏詞族。未上色線稿的膚色被 vision 誤譯成
# 「膚色未填色呈線條狀 / tan skin tone」進 prompt，壓深生成膚色（第五輪歸因）。
# 有膚色線條/未填色類描述一律剝除；真正膚色由年齡/預設確定性決定。
_SKINTONE_LEAK_KW = {
    "膚色", "膚", "未上色", "未填色", "無色", "線條", "線稿",
    "tan skin", "skin tone", "uncolored", "colorless", "unpainted",
}


def _filter_visual_for_llm(
    visual: str, *, strip_clothing: bool, strip_hairstyle: bool, strip_skin: bool = False
) -> str:
    """
    Remove clothing / hairstyle / skin-tone-leak phrases from a comma-separated vision
    description before sending it to the LLM, so it cannot hallucinate outfits, hairstyles,
    or lineart skin-tone artifacts that conflict with explicitly defined character settings.
    """
    if not (strip_clothing or strip_hairstyle or strip_skin):
        return visual
    phrases = [p.strip() for p in visual.replace(",", "，").split("，") if p.strip()]
    result = []
    for p in phrases:
        drop = False
        if strip_clothing and any(kw in p for kw in _CLOTHING_KW):
            drop = True
        if not drop and strip_hairstyle and any(kw in p for kw in _HAIRSTYLE_KW):
            drop = True
        if not drop and strip_skin and any(kw in p for kw in _SKINTONE_LEAK_KW):
            drop = True
        if not drop:
            result.append(p)
    return "，".join(result)


def _visual_extract_prompt(n: int) -> str:
    """Return a vision prompt tuned for single or multi-image analysis."""
    ignore_bg = (
        "【線稿警告】這可能是未上色的鉛筆稿／線稿，且常帶單色（如粉紅色）背景。"
        "規則一：完全忽略背景顏色——粉紅色或任何單色背景，絕不可當成髮色或服裝顏色。"
        "規則二：若畫面只有線條、沒有實際填色，請直接省略顏色、不要寫出任何顏色詞，也不要寫「線稿未上色」這類字樣，"
        "只描述髮型長度與形狀、服裝款式與材質、明顯特徵。嚴禁臆測顏色。只觀察「角色線條內」的特徵。"
    )
    if n == 1:
        return (
            f"{ignore_bg}\n"
            "請仔細觀察這張角色參考圖，描述以下視覺特徵：\n"
            "① 髮色與髮型（顏色、長度、形狀，請根據角色本身的髮色判斷）"
            "② 眼睛顏色"
            "③ 膚色"
            "④ 服裝主要顏色與風格（僅描述角色穿著的部分，無視背景）"
            "⑤ 明顯特殊特徵（獸耳、印記、武器等）\n"
            "格式：逗號分隔的中文短語，不加標號，不寫句子，控制在70字以內。"
        )
    return (
        f"{ignore_bg}\n"
        f"你收到了 {n} 張同一角色的不同參考圖。"
        "請綜合比較所有圖片，找出在多張圖中一致出現的視覺特徵：\n"
        "① 髮色與髮型"
        "② 眼睛顏色"
        "③ 膚色"
        "④ 服裝主要顏色與風格"
        "⑤ 各圖均出現的特殊特徵\n"
        "以共同特徵為主，忽略只在單張圖出現的細節。"
        "格式：逗號分隔的中文短語，不加標號，不寫句子，控制在90字以內。"
    )

# ── Vision extraction cache ──────────────────────────────────────────────────
# concept images 不變 → vision 抽取結果不變。以 image bytes hash + 模式 + 模型為
# key 快取，重複生成同角色時跳過最貴的 Ollama vision 呼叫（5~20s）。
# 錯誤結果（"[...]" 開頭）不快取。dict 依插入序淘汰最舊項目。
# 快取持久化至 data/vision_cache.json，重啟後仍命中（避免 LLM 非確定性導致行為飄移）。
_VISION_CACHE_MAX = 32

# H1（2026-07-13）：cache 版本號。coverage 與 visual 存在同一 cache value，過去 cache key
# 不含流程版本 → 改了 coverage 判定/prompt 後，舊的（可能誤判 full 的）coverage 仍被鎖死命中
# （第六輪半身圖斷腿根因之一）。凡動到 coverage 判定或 vision prompt，就 bump 此版本號，
# 讓全部舊快取自動失效、下次重判。
_VISION_FLOW_VERSION = "v4-2026-07-14"  # T1A：加入像素反向升級（fullness-check），改動 coverage 決策鏈 → 清舊快取重判


def _load_vision_cache() -> dict[str, tuple[str, str]]:
    """Load persisted vision cache from disk; return empty dict on any error."""
    try:
        if _VISION_CACHE_FILE.exists():
            raw = json.loads(_VISION_CACHE_FILE.read_text(encoding="utf-8"))
            # raw: {key: [coverage, visual]}
            cache = {k: (v[0], v[1]) for k, v in raw.items() if isinstance(v, list) and len(v) == 2}
            logger.info("[vision-cache] loaded %d entries from disk", len(cache))
            return cache
    except Exception as e:
        logger.warning("[vision-cache] could not load from disk: %s", e)
    return {}


def _save_vision_cache(cache: dict[str, tuple[str, str]]) -> None:
    """Persist vision cache to disk; silently skip on any error."""
    try:
        _VISION_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _VISION_CACHE_FILE.write_text(
            json.dumps({k: list(v) for k, v in cache.items()}, ensure_ascii=False, indent=None),
            encoding="utf-8",
        )
    except Exception as e:
        logger.warning("[vision-cache] could not save to disk: %s", e)


_VISION_CACHE: dict[str, tuple[str, str]] = _load_vision_cache()


def _vision_cache_key(images_bytes: list[bytes], mode: str) -> str:
    h = hashlib.sha256()
    for b in images_bytes:
        h.update(len(b).to_bytes(8, "little"))
        h.update(b)
    # H1：前綴流程版本號，改動 coverage/vision 邏輯後舊快取自動失效（見 _VISION_FLOW_VERSION）。
    return f"{_VISION_FLOW_VERSION}|{mode}|{state.get_vision_model()}|{h.hexdigest()}"


async def _vision_extract_cached(
    valid_images: list[bytes], need_coverage: bool,
) -> tuple[str, str]:
    """
    Shared vision-extraction step for character / variant design generation.
    Returns (coverage, visual); coverage is "full" placeholder when
    need_coverage=False.  Cache hit skips the Ollama call entirely
    (including request_focus, so ComfyUI stays warm).
    """
    mode = "coverage" if need_coverage else f"plain{len(valid_images)}"
    key = _vision_cache_key(valid_images, mode)
    cached = _VISION_CACHE.get(key)
    if cached is not None:
        logger.info("[vision-cache] hit (%s)", mode)
        return cached

    await guardian.request_focus("ollama")
    if need_coverage:
        coverage, visual = await run_in_threadpool(
            _detect_coverage_and_extract_visual, valid_images
        )
    else:
        coverage = "full"
        visual = await run_in_threadpool(
            _oc.analyze_multi_images_bytes,
            valid_images, _visual_extract_prompt(len(valid_images)),
            model=state.get_vision_model(),
            options={"num_predict": 160, "temperature": 0.1},
            # 2026-07-07 P0：同上，呼叫完即退 VRAM
            keep_alive=0,
        )

    if visual and not _oc.is_error(visual):
        _VISION_CACHE[key] = (coverage, visual)
        while len(_VISION_CACHE) > _VISION_CACHE_MAX:
            _VISION_CACHE.pop(next(iter(_VISION_CACHE)))
        _save_vision_cache(_VISION_CACHE)
    return coverage, visual
