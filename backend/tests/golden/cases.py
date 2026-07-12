"""
Golden regression set — P2（2026-07-02 規劃）。

「遇到才知道壞」的根源 = 沒有回歸手段。這裡收錄一組代表性角色輸入，
連同「模擬 LLM 原始回應」(mock_raw) 一起固定下來，讓 compiler.compile()
裡的確定性後處理管線（sanitizer / anchor / 重排…）任何改動都能被 diff 出來。

注意：mock_raw 是「假裝 Ollama 回傳的原始文字」，不是真的呼叫模型。
這組回歸集驗證的是 compile() 的後處理邏輯是否被意外改壞，
不驗證 LLM 本身輸出品質（那需要真實 Ollama + 實測生圖，見規劃 P1 風險備忘）。

新增案例：在 CASES 加一筆 GoldenCase，跑一次
    python -m tests.golden.run_diff --update
寫入新 snapshot 後 review 內容再 commit。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.services.ai.prompt_engine.styles import PromptStyle


@dataclass(frozen=True)
class GoldenCase:
    name: str
    style: PromptStyle
    text: str
    mock_raw: str
    anchor_text: str = ""
    quality_prefix_override: str | None = None
    negative_override: str | None = None
    note: str = ""


CASES: list[GoldenCase] = [
    GoldenCase(
        name="heterochromia_female",
        style=PromptStyle.SDXL,
        text="左眼為紅色，右眼為綠色的異色瞳少女，短褐色頭髮",
        mock_raw="1girl, solo, heterochromia, red eye (left), green eye (right), brown hair, short hair",
        note="異色瞳：確認方向標籤與 heterochromia 不被去重誤刪",
    ),
    GoldenCase(
        name="male_mage",
        style=PromptStyle.SDXL,
        text="銀髮紫瞳的魔法師少年",
        mock_raw="1boy, solo, silver hair, purple eyes, mage, magic, robe, serious expression",
        note="男性角色：確認 1boy 主體詞與服裝標籤不受女性向規則影響",
    ),
    GoldenCase(
        name="child_age_phrase_leak",
        style=PromptStyle.SDXL,
        text="十歲的小女孩，圓臉",
        mock_raw="1girl, solo, 10 years old, round face, child, youthful",
        note="兒童：LLM 洩漏數字年齡短語（由 _age_body_tags 確定性處理，此處應被 _AGE_PHRASE_RE 濾除）",
    ),
    GoldenCase(
        name="tall_casual_vest",
        style=PromptStyle.ILLUSTRIOUS,
        text="高個子，背心，休閒風格的少女",
        mock_raw="1girl, solo, tall, long legs, vest, casual, sleeveless, formal suit, tie",
        note="背心/休閒 vs 西裝幻覺：Group A 過濾器目前停用，此案例會如實保留 formal suit/tie——"
             "若日後重新啟用 _clean_clothing_hallucinations，此 snapshot 應變化（預期內差異）",
    ),
    GoldenCase(
        name="no_concept_plain",
        style=PromptStyle.SDXL,
        text="一個女孩右手拿傘",
        mock_raw="1girl, solo, holding umbrella, right hand, standing, outdoors",
        note="無概念圖 / 無 anchor_text：純文字輸入的基本路徑",
    ),
    GoldenCase(
        name="cjk_and_meta_leak",
        style=PromptStyle.SDXL,
        text="白色頭髮，金色眼睛的少女",
        mock_raw='1girl, solo, white hair, golden eyes, 角色名稱, "but let\'s stick to input", '
                 'Conflict Resolution:, (or maybe boots), reasoning - wait actually blue',
        note="CJK 洩漏／雙引號 meta 註解／冒號結尾標籤／括號替代說明／dash 推理殘留，"
             "驗證 _sanitize_to_list 各層過濾同時生效",
    ),
    GoldenCase(
        name="duplicate_tags",
        style=PromptStyle.SDXL,
        text="白髮少女，眼睛是金色的",
        mock_raw="1girl, solo, white hair, golden eyes, white hair, golden eyes, solo",
        note="重複標籤：驗證 _sanitize_to_list 去重（大小寫/前後空白皆需正規化）",
    ),
    GoldenCase(
        name="pony_style_katana",
        style=PromptStyle.PONY,
        text="銀髮少女拿著武士刀，背景是紅色的月亮",
        mock_raw="1girl, solo, silver hair, holding sword, katana, red moon, night, source_anime",
        note="Pony 風格：確認 score_ 系列 quality tag 仍在 banned_tags 被擋（LLM 誤加時）",
    ),
    GoldenCase(
        name="flux_style_sentence",
        style=PromptStyle.FLUX,
        text="一個女孩右手拿傘",
        mock_raw="A young girl standing outdoors, holding a colorful umbrella in her right hand, "
                 "with a calm and serene expression.",
        note="Flux：自然語言路徑，不跑 tag sanitizer（final_body = extracted 原樣輸出）",
    ),
    GoldenCase(
        name="noobai_style_knight",
        style=PromptStyle.NOOBAI,
        text="一個身穿盔甲的騎士在戰場上",
        mock_raw="1boy, solo, knight, full armor, holding sword, battlefield, fire, smoke, debris, "
                 "intense expression, dynamic pose, cinematic lighting",
        note="NoobAI 風格：密集描述型 template 基本路徑",
    ),
    GoldenCase(
        name="anythingxl_heterochromia",
        style=PromptStyle.ANYTHINGXL,
        text="左眼為紅色，右眼為綠色的異色瞳女孩",
        mock_raw="1girl, solo, heterochromia, red eye (left), green eye (right), looking at viewer, "
                 "source_anime",
        note="AnythingXL 風格 + 異色瞳：跨 style 驗證方向標籤處理一致",
    ),
    GoldenCase(
        name="overlong_leak_tag",
        style=PromptStyle.SDXL,
        text="黑髮黑眼的少女，穿著簡單洋裝",
        mock_raw="1girl, solo, black hair, black eyes, simple dress, "
                 "this is a very long inference sentence that leaks reasoning text far beyond "
                 "the eighty character limit that a real sd tag would ever have and must be dropped",
        note="超長 tag（LLM 推理洩漏）：驗證 _MAX_TAG_LEN 上限過濾",
    ),
]
