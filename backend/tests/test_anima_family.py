"""Anima family 落地 + 能力閘控回歸測試（AC-4，2026-07-25）。

涵蓋 2026-07-25 一批改動：
  AC-1   PromptStyle.ANIMA / STYLE_CONFIG.anima（07-23 §4.3 定案配方）
  AC-2   workflow_builder._detect_style 的 UNETLoader fallback
  AC-2'  capability 三處共用 checkpoint 解析（UI 與生成端 family 一致）
  D'-2   cn_fallback="img2img" 與 _inject_img2img 注入鏈
  B-3'   _set_node_input 上游參數覆寫（採樣/解析度雙真相）

⚠️ 本檔同時是 **Standard_V37 定版零回歸鎖**：V37 相關斷言若失敗，代表 Anima 適配
   污染了已定版的 V37 路徑，必須回頭修，不可改斷言就當過關。

執行：cd backend && pytest tests/test_anima_family.py -v
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from app.services.ai import capability as cap
from app.services.ai import gen_profile as gp
from app.services.ai import wf_node_ops as ops
from app.services.ai.prompt_engine.styles import PromptStyle, STYLE_CONFIG

_WF_DIR = Path(__file__).resolve().parents[2] / "data" / "custom_workflows"


def _load(name: str) -> dict:
    p = _WF_DIR / name
    if not p.exists():
        pytest.skip(f"workflow {name} 不在 {_WF_DIR}")
    return json.loads(p.read_text(encoding="utf-8"))


# ── AC-1：PromptStyle.ANIMA / STYLE_CONFIG ────────────────────────────────────

def test_anima_enum_exists_and_roundtrips():
    """AC-1 與 AC-2 必須同批：enum 缺席時 PromptStyle('anima') 會 ValueError。"""
    assert PromptStyle("anima") is PromptStyle.ANIMA
    assert PromptStyle.ANIMA in STYLE_CONFIG


def test_anima_style_config_golden():
    """配方 golden — 來源：doc/2026-07-23 開發清單 §4.3。改配方請連同本測試一起改。"""
    c = STYLE_CONFIG[PromptStyle.ANIMA]
    assert c.quality_prefix == (
        "masterpiece, best quality, absurdres, ultra detailed, high contrast"
    )
    # 決策①：family 不做 safety 分級
    for tag in ("safe", "sensitive", "explicit"):
        assert tag not in c.quality_prefix
    # 決策②：光影組不寫死在 family
    for tag in ("bokeh", "depth of field", "backlighting", "light particles"):
        assert tag not in c.quality_prefix
    # Anima 專屬負向對比項（07-22 實測：缺這段必偏白）
    for tag in ("overexposed", "washed out", "faded", "low contrast",
                "blown out highlights", "pale"):
        assert tag in c.negative
    # P1-2（2026-08-12）：環境/投影抑制（R3 地面投影陰影）
    for tag in ("drop shadow", "cast shadow", "floor", "ground", "reflection"):
        assert tag in c.negative
    # ⚠️ 裸 "shadow" 會壓掉角色 shading，與上面的高對比訴求打架 —— 不得混入。
    # 用 tag 級比對（非子字串），否則 "drop shadow" 會誤判成命中。
    assert "shadow" not in {t.strip() for t in c.negative.split(",")}


@pytest.mark.parametrize("style", list(STYLE_CONFIG))
def test_llm_template_formats_with_only_prompt_field(style):
    """所有家族的 llm_template 必須只含 {prompt} 一個佔位符，且 .format 得起來。

    2026-07-25 實戰 bug：_ANIMA_TEMPLATE 是 f-string，裡面寫 "{{color}} theme" 想表達
    「任何顏色主題 tag」，f-string 求值後變成 {color}，compiler 的
    `config.llm_template.format(prompt=text)` 便當成佔位符 → KeyError: 'color'（500）。
    原測試只驗 STYLE_CONFIG 欄位內容、沒真的跑一次 format，所以沒攔下來。
    """
    import re
    fields = set(re.findall(r"(?<!\{)\{([a-zA-Z_][a-zA-Z0-9_]*)\}(?!\})",
                            STYLE_CONFIG[style].llm_template))
    assert fields == {"prompt"}, f"{style.value} 模板含非預期佔位符：{sorted(fields - {'prompt'})}"
    out = STYLE_CONFIG[style].llm_template.format(prompt="測試輸入")
    assert "測試輸入" in out


def test_anima_template_has_no_pale_literals():
    """2026-08-12 改版：規則不得再**列舉**蒼白 tag 字面。

    原 NO-PALE 規則逐一列出 pale skin / pastel colors / limited palette / {colour} theme
    來禁止它們，反而成為整份 template 裡唯一出現這些字串的地方 —— negation prompt 的
    典型反效果。對照組 _ILLUSTRIOUS_TEMPLATE / _PONY_TEMPLATE 沒有這條規則，輸出從不含
    pale skin；_ANIMA_TEMPLATE 有規則卻實跑吐出 pale skin（08-12 實測）。
    連 "palette" 都要擋：它含子字串 "pale"。
    """
    tpl = STYLE_CONFIG[PromptStyle.ANIMA].llm_template.lower()
    for kw in ("pale", "pastel", "palette", "theme", "desatur"):
        assert kw not in tpl, f"template 仍含蒼白字面 {kw!r} —— 會誘發模型吐出該 tag"


def test_anima_template_keeps_positive_skin_and_scope_rules():
    """規則被移除≠問題解決：改寫後的正向規則必須還在，否則等於整條防線消失。"""
    tpl = STYLE_CONFIG[PromptStyle.ANIMA].llm_template
    assert "- SKIN:" in tpl and "- SCOPE:" in tpl
    assert "skin tag" in tpl                       # SKIN 規則的核心語義
    assert "colour-scheme" in tpl                  # SCOPE 規則的核心語義


# 2026-09-21：原 test_warn_pale_tags_logs_without_mutating 已移除 ——
# compiler._warn_pale_tags() 本體是死碼（未與 watchlist 取交集、無 logger 呼叫），
# 連同 styles._PALE_TAGS_ANIMA_WATCHLIST 常數（早已不存在）一併清掉。
# 白皙膚色的可觀測性改由 compiler._canonicalize_fair_skin() 的 log 承接，見下方測試。


# 決策③的去飽和 tag 清單：原為 styles._PALE_TAGS_ANIMA_WATCHLIST，常數消失後就地內聯，
# 以免這條鎖因為 AttributeError 而形同虛設（＝SYNC-001「測試鎖錯對象」同型問題）。
_DESATURATING_TAGS = ("pale skin", "pastel colors", "limited palette", "muted colors")


def test_anima_pale_tags_not_banned():
    """決策③：去飽和 tag 不進 banned_tags（封鎖會誤殺吸血鬼／雪女等合法需求）。"""
    c = STYLE_CONFIG[PromptStyle.ANIMA]
    for tag in _DESATURATING_TAGS:
        assert tag not in c.banned_tags


def test_fair_skin_canonicalized_to_porcelain():
    """白皙系膚色統一詞：pale/fair/light skin → porcelain skin，且去重。"""
    from app.services.ai.prompt_engine.compiler import _canonicalize_fair_skin
    out = _canonicalize_fair_skin(
        ["1girl", "solo", "pale skin", "brown hair", "fair skin"], PromptStyle.ANIMA
    )
    assert out == ["1girl", "solo", "porcelain skin", "brown hair"]


def test_fair_skin_canon_keeps_intentional_pallor_and_other_tones():
    """負向對照：very/deathly/sickly pale 與其他膚色不得被改寫（合法角色設定）。"""
    from app.services.ai.prompt_engine.compiler import _canonicalize_fair_skin
    src = ["very pale skin", "deathly pale", "sickly pale skin", "tan", "dark skin", "olive skin"]
    assert _canonicalize_fair_skin(list(src), PromptStyle.ANIMA) == src


def test_fair_skin_canon_noop_when_no_skin_tag():
    """SKIN 規則：輸入沒提膚色就不該長出膚色 tag。"""
    from app.services.ai.prompt_engine.compiler import _canonicalize_fair_skin
    src = ["1girl", "solo", "brown hair", "blue eyes"]
    assert _canonicalize_fair_skin(list(src), PromptStyle.ANIMA) == src


# ── AC-2'：checkpoint 解析（三處共用同一來源）──────────────────────────────────

def test_extract_checkpoint_prefers_checkpoint_loader():
    wf = {"1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "a.safetensors"}},
          "2": {"class_type": "UNETLoader", "inputs": {"unet_name": "b.safetensors"}}}
    assert cap.extract_checkpoint_from_wf(wf) == "a.safetensors"


@pytest.mark.parametrize("ct", ["UNETLoader", "UnetLoaderGGUF", "UNETLoaderGGUF"])
def test_extract_checkpoint_unet_fallback(ct):
    """AC-2 的核心：無 CheckpointLoaderSimple 時要讀得到 unet_name（含 GGUF 變體）。"""
    wf = {"1": {"class_type": ct, "inputs": {"unet_name": "anima_baseV10.safetensors"}}}
    assert cap.extract_checkpoint_from_wf(wf) == "anima_baseV10.safetensors"
    assert cap.resolve_family(cap.extract_checkpoint_from_wf(wf)) == "anima"


def test_extract_checkpoint_empty_inputs():
    assert cap.extract_checkpoint_from_wf({}) == ""
    assert cap.extract_checkpoint_from_wf({"1": None, "2": "x"}) == ""


def test_nova_anime_xl_registered():
    """漏登錄 bug（2026-07-25）：novaAnimeXL 是 Illustrious 衍生，原本 fallback 成 sdxl。
    注意也要確認它不會誤命中 anima（"anime" != "anima"）。"""
    assert cap.resolve_family("novaAnimeXL_ilV190.safetensors") == "illustrious"


def test_animagine_is_sdxl_not_anima(monkeypatch):
    """SYNC-003 A1（2026-09-16）：animagineXL 含子字串 "anima"，漏登錄時被判成 Anima 家族，
    LLLite 被接到 SDXL 上 `created 0 modules` 空轉、IPA/CN 被閘掉、prompt 套 Anima 配方。
    07-25 AC-1 加入 catch-all "anima" 鍵起的回歸。兩條名稱判定路徑（family／style）都要鎖。"""
    from app.services.ai import workflow_builder as wb
    assert cap.resolve_family("animagineXL40_v4Opt.safetensors") == "sdxl"
    wf = {"1": {"class_type": "CheckpointLoaderSimple",
                "inputs": {"ckpt_name": "animagineXL40_v4Opt.safetensors"}}}
    monkeypatch.setattr(wb, "_load_workflow", lambda name: wf)
    assert wb._detect_style("text_to_image.json") == PromptStyle.SDXL
    # 對照：真正的 Anima 仍命中 catch-all
    assert cap.resolve_family("anima_turboV11.safetensors") == "anima"


# SYNC-003 C1：放在 checkpoints/ 但檔名帶 anima 的已知檔案（歸屬待使用者決定，決定後移除）。
# miaomiaoHarem_anima12：4,182,215,584 bytes，與 anima_baseV10 只差 2,744 bytes，
# 疑似只含 DiT 的 Anima 衍生模型放錯目錄（系統工作流的 CheckpointLoaderSimple 載不動）。
_KNOWN_ANIMA_IN_CHECKPOINTS = frozenset({"miaomiaoHarem_anima12.safetensors"})


def test_no_checkpoint_file_resolves_to_unet_only_family():
    """SYNC-003 A3-④ 磁碟反向驗證：models/checkpoints/ 是 CheckpointLoaderSimple 讀的目錄，
    裡面的檔案不該被判成只能用 UNet 載入器的家族。新放一支檔名撞到短鍵的 SDXL 模型時，
    這裡會紅，提醒去 checkpoint_styles.yml 兩區補登錄。

    ComfyUI 位置由 .env 的 COMFYUI_LORAS_DIR 推得（其上一層＝models/）；未設定就 skip。
    """
    from app.core.config import COMFYUI_LORAS_DIR
    ckpt_dir = COMFYUI_LORAS_DIR.parent / "checkpoints"
    if not ckpt_dir.is_dir():
        pytest.skip(f"ComfyUI checkpoints 目錄不存在：{ckpt_dir}（請在 .env 設定 COMFYUI_LORAS_DIR）")
    files = sorted(p.name for p in ckpt_dir.glob("*.safetensors"))
    if not files:
        pytest.skip(f"{ckpt_dir} 內沒有 .safetensors")
    wrong = [f for f in files
             if f not in _KNOWN_ANIMA_IN_CHECKPOINTS
             and cap.resolve_family(f) in cap._UNET_ONLY_FAMILIES]
    assert not wrong, (
        f"這些 checkpoints/ 內的檔案被判成 UNet 專屬家族，多半是檔名誤命中短鍵："
        f"{wrong} → 請在 checkpoint_styles.yml 的 checkpoints 與 families 兩區補登錄"
    )


def test_anima_workflow_capability_all_false():
    """使用者回報「CN 沒有效果」的根因鎖：UI 端能力必須與生成端閘控一致。"""
    wf = _load("AnimaStandardV7.json")
    c = cap.resolve_capability(wf, cap.extract_checkpoint_from_wf(wf))
    assert c["family"] == "anima"
    assert c["ipa_supported"] is False
    assert c["cn_supported"] is False
    assert c["cn_fallback"] == "img2img"   # 有替代 → 前端仍要顯示控制項
    assert c["models"] is None


# ── Standard_V37 定版零回歸鎖 ────────────────────────────────────────────────

def test_v37_capability_unchanged():
    wf = _load("Standard_V37.json")
    c = cap.resolve_capability(wf, cap.extract_checkpoint_from_wf(wf))
    assert c["family"] == "illustrious"
    assert c["ipa_supported"] is True
    assert c["cn_supported"] is True
    assert c["cn_fallback"] is None
    assert c["models"] is not None


def test_v37_illustrious_style_config_unchanged():
    """V37 的 prompt 由 prompt_profiles.yml 決定，但 family 仍是 fallback 底線。"""
    c = STYLE_CONFIG[PromptStyle.ILLUSTRIOUS]
    assert c.quality_prefix == "masterpiece, best quality, amazing quality, absurdres"
    assert c.negative.startswith("worst quality, low quality, lowres, bad anatomy")


def test_v37_profile_registered_and_anima_not():
    """AC-3：AnimaStandardV7 刻意不登錄 workflow profile（避免與 family 兩份真相）。"""
    from app.services.ai.workflow_builder import _load_prompt_profiles
    profiles = _load_prompt_profiles()
    assert "Standard_V37.json" in profiles
    assert "AnimaStandardV7.json" not in profiles


# ── AnimaStandardV8（Aesthetic v1.1）prompt 鎖 ───────────────────────────────
# 2026-08-17：V8 底模改用 anima_aestheticV11。官方 model card 對 Aesthetic 版明文
# 「正負向都不要用 score_* tags」，而 family(ANIMA) 的 negative 是為 base 版而設、
# 含 score_1/2/3 → 必須在 workflow profile 這層拿掉。
# 本組斷言鎖的是「唯一差異就是 score_*」——防的是日後改 family negative 時忘了同步
# 這份副本（prompt_profiles.yml 只有整段取代語義，沒有「移除單項」，副本無可避免）。

def test_v8_profile_registered_and_matches_checkpoint():
    from app.services.ai.workflow_builder import _load_prompt_profiles
    profiles = _load_prompt_profiles()
    assert "AnimaStandardV8.json" in profiles
    wf = _load("AnimaStandardV8.json")
    ckpt = cap.extract_checkpoint_from_wf(wf)
    assert "aesthetic" in ckpt.lower(), f"V8 底模已非 aesthetic（{ckpt}），本組斷言的前提失效"
    assert cap.resolve_family(ckpt) == "anima"


def test_v8_negative_drops_score_tags_only():
    """官方明令：Aesthetic 版正負向皆不得含 score_*。且與 family 的差異僅止於此。"""
    from app.services.ai.workflow_builder import _load_prompt_profiles
    v8 = _load_prompt_profiles()["AnimaStandardV8.json"]["negative"]
    fam = STYLE_CONFIG[PromptStyle.ANIMA].negative

    def toks(x):
        return [t.strip() for t in x.split(",") if t.strip()]

    assert not [t for t in toks(v8) if t.startswith("score_")]
    assert [t for t in toks(fam) if t not in toks(v8)] == ["score_1", "score_2", "score_3"]
    assert [t for t in toks(v8) if t not in toks(fam)] == []


def test_v8_quality_prefix_falls_back_to_family():
    """quality_prefix 刻意不登錄（family 現值已不含 score_*，符合官方）。
    若哪天有人在 V8 profile 補了 quality_prefix，這條會提醒他順便檢查 score_*。"""
    from app.services.ai.workflow_builder import _load_prompt_profiles
    prefix = _load_prompt_profiles()["AnimaStandardV8.json"].get("quality_prefix")
    assert prefix is None or "score_" not in prefix
    assert "score_" not in STYLE_CONFIG[PromptStyle.ANIMA].quality_prefix


def test_illustrious_profile_has_no_cn_fallback():
    """SDXL 系家族不得被 D'-2 影響：cn_fallback 必須是 None，否則會走錯路徑。"""
    for fam in ("sdxl", "pony", "noobai", "illustrious"):
        p = gp.get_profile(fam)
        assert p.cn_fallback is None, fam
        assert p.cn_enabled is True, fam
        assert p.ipa_enabled is True, fam


# ── D'-2：img2img 替代 ────────────────────────────────────────────────────────

def test_anima_profile_fallback_and_denoise_mapping():
    p = gp.get_profile("anima")
    assert p.cn_enabled is False and p.ipa_enabled is False
    # 2026-08-12 行為變更：cn_fallback 由單值改為候選鏈的首項，anima 首選已是 lllite。
    # img2img 沒有被移除，只是降為 lllite 不可用時的退路 —— 故這裡改驗「它還在鏈上」，
    # 下方 denoise 映射的斷言（img2img 專屬）也因此必須繼續有效。
    assert p.cn_fallback_chain == ("lllite", "img2img")
    assert "img2img" in p.cn_fallback_chain
    # cn_weight 越高＝越貼合參考圖；denoise 語義相反，必須單調遞減
    assert p.img2img_denoise(1.0) < p.img2img_denoise(0.5)
    # 夾在設定範圍內
    assert p.img2img_denoise_min <= p.img2img_denoise(1.0) <= p.img2img_denoise_max
    assert p.img2img_denoise_min <= p.img2img_denoise(0.0) <= p.img2img_denoise_max


@pytest.mark.parametrize("endpoint_name", ["generate_character_design", "generate_variant_design"])
def test_api_gate_keeps_use_controlnet_when_cn_fallback_exists(monkeypatch, endpoint_name):
    """2026-08-05 根因鎖：API 層 B5 能力守門不得把有替代路徑的家族打成 use_controlnet=False。

    背景：07-25 D'-2 只修了前端（cnUsable = cnSupported or cn_fallback），後端
    `if not _cap["cn_supported"]: use_controlnet = False` 漏改 → service 的
    cn_fallback 分支永遠進不去，img2img 替代方案自加入起就是死代碼（log 零命中）。
    這個測試鎖住兩層判斷一致，避免再次只修一邊。
    """
    import asyncio
    from app.api import art_generate as ag

    captured = {}

    async def _fake_gen(**kwargs):
        captured.update(kwargs)
        return None

    monkeypatch.setattr(ag, "_current_capability",
                        lambda *a, **k: {"ipa_supported": False, "cn_supported": False,
                                         "cn_fallback": "img2img", "family": "anima"})
    monkeypatch.setattr(ag.character_design_service, endpoint_name, _fake_gen)

    endpoint = getattr(ag, endpoint_name)
    call = {"character_id": 1, "use_ipa": True, "use_controlnet": True, "db": None}
    if endpoint_name == "generate_variant_design":
        call["slot"] = 1
    asyncio.run(endpoint(**call))

    assert captured["use_controlnet"] is True, "有 cn_fallback 時 use_controlnet 被誤關 → img2img 死代碼"
    assert captured["use_ipa"] is False, "ipa_supported=False 仍須關閉（無替代路徑）"


def test_api_gate_still_disables_cn_without_fallback(monkeypatch):
    """反向鎖：家族既不支援 CN 也沒有替代路徑時，守門仍必須關閉（如 flux）。"""
    import asyncio
    from app.api import art_generate as ag

    captured = {}

    async def _fake_gen(**kwargs):
        captured.update(kwargs)
        return None

    monkeypatch.setattr(ag, "_current_capability",
                        lambda *a, **k: {"ipa_supported": False, "cn_supported": False,
                                         "cn_fallback": None, "family": "flux"})
    monkeypatch.setattr(ag.character_design_service, "generate_character_design", _fake_gen)
    asyncio.run(ag.generate_character_design(character_id=1, use_ipa=True,
                                             use_controlnet=True, db=None))
    assert captured["use_controlnet"] is False


# ── A3 P0-1 / P0-3（2026-08-22）：seed / reuse_prompt 端點貫通 ────────────────

@pytest.mark.parametrize("endpoint_name", ["generate_character_design", "generate_variant_design"])
def test_api_forwards_seed_and_reuse_prompt(monkeypatch, endpoint_name):
    """seed/reuse_prompt 是可重現實驗台的入口——只在其中一層加參數、另一層沒接住，
    整條「同 seed 連按兩次應輸出一致」就是死代碼（同款教訓見 D4 兩層閘控）。"""
    import asyncio
    from app.api import art_generate as ag

    captured = {}

    async def _fake_gen(**kwargs):
        captured.update(kwargs)
        return None

    monkeypatch.setattr(ag, "_current_capability",
                        lambda *a, **k: {"ipa_supported": True, "cn_supported": True,
                                         "cn_fallback": None, "family": "illustrious"})
    monkeypatch.setattr(ag.character_design_service, endpoint_name, _fake_gen)

    endpoint = getattr(ag, endpoint_name)
    call = {"character_id": 1, "seed": 12345, "reuse_prompt": True, "db": None}
    if endpoint_name == "generate_variant_design":
        call["slot"] = 1
    asyncio.run(endpoint(**call))

    assert captured["seed"] == 12345
    assert captured["reuse_prompt"] is True


@pytest.mark.parametrize("endpoint_name", ["generate_character_design", "generate_variant_design"])
def test_api_seed_and_reuse_prompt_default_to_zero_regression_values(monkeypatch, endpoint_name):
    """未傳 seed/reuse_prompt 時必須是 -1/False（維持現行隨機＋每次重編譯），零回歸。"""
    import asyncio
    from app.api import art_generate as ag

    captured = {}

    async def _fake_gen(**kwargs):
        captured.update(kwargs)
        return None

    monkeypatch.setattr(ag, "_current_capability",
                        lambda *a, **k: {"ipa_supported": True, "cn_supported": True,
                                         "cn_fallback": None, "family": "illustrious"})
    monkeypatch.setattr(ag.character_design_service, endpoint_name, _fake_gen)

    endpoint = getattr(ag, endpoint_name)
    call = {"character_id": 1, "db": None}
    if endpoint_name == "generate_variant_design":
        call["slot"] = 1
    asyncio.run(endpoint(**call))

    assert captured["seed"] == -1
    assert captured["reuse_prompt"] is False


# ── 2026-08-05：img2img 參考圖色彩正規化 ──────────────────────────────────────

def _pink_sketch_bytes(w=64, h=128):
    """仿真實草圖：粉紅底 + 深粉線條（去色後背景為中灰，非白）。"""
    import io as _io
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (w, h), (240, 190, 195))
    d = ImageDraw.Draw(im)
    d.line([(w // 2, 4), (w // 2, h - 4)], fill=(120, 60, 70), width=2)
    buf = _io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


def _channels_of(image_bytes):
    import io as _io
    from PIL import Image
    im = Image.open(_io.BytesIO(image_bytes)).convert("RGB")
    px = list(im.getdata())
    return px


def test_i2i_ref_none_is_byte_identical():
    """回滾模式必須完全不動圖，否則「關掉」就不是真的關掉。"""
    from app.services.ai.image_ops import _normalize_i2i_ref
    raw = _pink_sketch_bytes()
    assert _normalize_i2i_ref(raw, "none") is raw


def test_i2i_ref_grayscale_removes_hue():
    """核心需求：去掉草圖色相，避免粉底染整張輸出；但保留明暗層次。"""
    from app.services.ai.image_ops import _normalize_i2i_ref
    raw = _pink_sketch_bytes()
    assert any(r != g or g != b for r, g, b in _channels_of(raw)), "測試素材本身應有色相"
    px = _channels_of(_normalize_i2i_ref(raw, "grayscale"))
    assert all(r == g == b for r, g, b in px), "grayscale 後仍殘留色相"
    assert len({p[0] for p in px}) > 1, "層次被壓平（應保留明暗，不是純色塊）"


def test_i2i_ref_lineart_needs_autocontrast_not_all_black():
    """回歸鎖：草圖去色後背景是中灰，直接套固定門檻會整張變黑（2026-08-05 實作時踩到）。

    正確行為是先 autocontrast 把背景拉到接近白，再二值化 → 必須同時存在黑與白。
    """
    from app.services.ai.image_ops import _normalize_i2i_ref
    px = _channels_of(_normalize_i2i_ref(_pink_sketch_bytes(), "lineart"))
    vals = {p[0] for p in px}
    assert vals <= {0, 255}, f"lineart 應為純二值，實際={sorted(vals)[:8]}"
    assert 0 in vals and 255 in vals, "整張同色＝門檻失效（全黑或全白）"
    dark_ratio = sum(1 for p in px if p[0] == 0) / len(px)
    assert 0.0 < dark_ratio < 0.5, f"線條占比異常={dark_ratio:.1%}"


@pytest.mark.parametrize("bad", ["bogus", "GRAYSCALE ", ""])
def test_i2i_ref_mode_is_validated(bad, monkeypatch):
    """未知/髒 mode 不得靜默走到別的分支：大小寫與空白正規化，無法辨識則退預設。"""
    from app.services.ai.image_ops import _normalize_i2i_ref
    raw = _pink_sketch_bytes()
    px = _channels_of(_normalize_i2i_ref(raw, bad) if bad else _normalize_i2i_ref(raw))
    assert all(r == g == b for r, g, b in px), "應退回預設 grayscale"


def test_i2i_ref_bad_bytes_falls_back_to_input():
    """Resilient errors：參考圖壞掉不可讓生成 crash，回傳原 bytes 繼續跑。"""
    from app.services.ai.image_ops import _normalize_i2i_ref
    junk = b"not-an-image"
    assert _normalize_i2i_ref(junk, "grayscale") == junk


def test_i2i_ref_env_override(monkeypatch):
    """IMG2IMG_REF_MODE 供本機 A/B；打錯字要退預設而不是靜默改行為。"""
    from app.services.ai import image_ops as io_mod
    monkeypatch.setenv("IMG2IMG_REF_MODE", "lineart")
    assert io_mod._resolve_i2i_ref_mode() == "lineart"
    monkeypatch.setenv("IMG2IMG_REF_MODE", "linart")   # typo
    assert io_mod._resolve_i2i_ref_mode() == io_mod._I2I_REF_MODE_DEFAULT


# ── P0（2026-08-12）：lineart 背景合成 ────────────────────────────────────────
# 解的是「純白線稿底在低 denoise 蓋掉 prompt 背景色」。**解不了動作詭異**
# （那是 img2img 的 denoise 死結，見 08-12 開發記錄第四節）——別把這組測試的
# 綠燈讀成姿勢問題已處理。

def _bg_px(image_bytes):
    """取四角像素當背景色樣本（線條在中央直線，不會落在角上）。"""
    import io as _io
    from PIL import Image
    im = Image.open(_io.BytesIO(image_bytes)).convert("RGB")
    w, h = im.size
    px = im.load()
    return [px[0, 0], px[w - 1, 0], px[0, h - 1], px[w - 1, h - 1]]


def _lineart(prompt=None):
    from app.services.ai.image_ops import _normalize_i2i_ref
    return _normalize_i2i_ref(_pink_sketch_bytes(), "lineart", prompt)


def test_bg_composite_uses_prompt_background_color(monkeypatch):
    """P0 核心：prompt 說 blue background，線稿底就要是藍，不是白。"""
    from app.services.ai.image_ops import _I2I_BG_COLORS
    monkeypatch.delenv("IMG2IMG_REF_BG", raising=False)
    out = _lineart("1girl, solo, blue background, standing")
    assert set(_bg_px(out)) == {_I2I_BG_COLORS["blue"]}


def test_bg_composite_keeps_lineart_pure_binary(monkeypatch):
    """線條必須維持純黑、且底色只有一種 —— 出現中間灰＝合成順序錯了
    （縮放插值先發生），會讓後續 _fit_to_canvas 糊掉線稿邊緣。"""
    monkeypatch.delenv("IMG2IMG_REF_BG", raising=False)
    px = _channels_of(_lineart("green background"))
    from app.services.ai.image_ops import _I2I_BG_COLORS
    assert set(px) == {(0, 0, 0), _I2I_BG_COLORS["green"]}, "出現非預期的中間色"
    dark = sum(1 for p in px if p == (0, 0, 0)) / len(px)
    assert 0.0 < dark < 0.5, f"線條占比異常={dark:.1%}（結構被合成破壞）"


def test_bg_auto_without_color_tag_stays_white(monkeypatch):
    """偏離 08-05 規劃 P0-3 的刻意設計：auto 解析不到顏色時退**白底**，
    不退草圖底色 —— 退草圖底色等於把 08-05 才擋掉的粉色場又放回 latent。"""
    monkeypatch.delenv("IMG2IMG_REF_BG", raising=False)
    assert set(_bg_px(_lineart("1girl, simple background"))) == {(255, 255, 255)}
    assert set(_bg_px(_lineart(None))) == {(255, 255, 255)}


def test_bg_sketch_mode_falls_back_to_border_color(monkeypatch):
    """sketch 模式＝規劃書原意：解析不到顏色時用原草圖底色。"""
    monkeypatch.setenv("IMG2IMG_REF_BG", "sketch")
    out = _bg_px(_lineart("1girl, simple background"))
    assert set(out) != {(255, 255, 255)}, "sketch 模式沒退回草圖底色"
    r, g, b = out[0]
    assert r > b > 100 and r > g, f"應接近草圖粉底 (240,190,195)，實際={out[0]}"


def test_bg_explicit_hex(monkeypatch):
    monkeypatch.setenv("IMG2IMG_REF_BG", "#123456")
    assert set(_bg_px(_lineart("blue background"))) == {(0x12, 0x34, 0x56)}, \
        "明確指定的色碼必須壓過 prompt 解析"


def test_bg_none_disables_composite(monkeypatch):
    """回滾開關：none 要回到 2026-08-12 前的純白底行為。"""
    monkeypatch.setenv("IMG2IMG_REF_BG", "none")
    assert set(_bg_px(_lineart("blue background"))) == {(255, 255, 255)}


@pytest.mark.parametrize("bad", ["bogus", "#12345", "#GGGGGG"])
def test_bg_bad_value_falls_back_to_auto(monkeypatch, bad):
    """打錯字不得靜默改行為：退回 auto（仍會解析 prompt）。"""
    from app.services.ai.image_ops import _I2I_BG_COLORS
    monkeypatch.setenv("IMG2IMG_REF_BG", bad)
    assert set(_bg_px(_lineart("blue background"))) == {_I2I_BG_COLORS["blue"]}


@pytest.mark.parametrize("prompt,expect", [
    ("simple background, white background", "white"),      # 非顏色詞在前不得使解析放棄
    ("detailed background, pink background", "pink"),
    ("light blue background", "blue"),                     # 取最靠近 background 的色詞
    ("1girl, solo", None),
    ("blue eyes, simple background", None),                # 顏色不緊鄰 background 不算
])
def test_bg_tag_parsing(prompt, expect):
    from app.services.ai.image_ops import _parse_bg_color_from_prompt, _I2I_BG_COLORS
    got = _parse_bg_color_from_prompt(prompt)
    assert got == (_I2I_BG_COLORS[expect] if expect else None), f"{prompt!r} → {got}"


def test_bg_color_table_covers_lexicon_color_map():
    """lexicon.COLOR_MAP 是中文→英文色名的產出端；它吐得出的色名，這裡都要查得到 RGB，
    否則 prompt 寫得出來的背景色會有一部分靜默失效。"""
    from app.services.ai.prompt_engine.lexicon import COLOR_MAP
    from app.services.ai.image_ops import _I2I_BG_COLORS
    missing = set(COLOR_MAP.values()) - set(_I2I_BG_COLORS)
    assert not missing, f"色名缺 RGB 對照：{sorted(missing)}"


def test_inject_img2img_rewires_latent_and_denoise():
    wf = _load("AnimaStandardV7.json")
    ks = ops._find_main_ksampler_id(wf)
    before_latent = copy.deepcopy(wf[ks]["inputs"]["latent_image"])

    assert ops._inject_img2img(wf, "ref.png", 0.55) is True

    new_latent = wf[ks]["inputs"]["latent_image"]
    assert new_latent != before_latent
    enc = wf[new_latent[0]]
    assert enc["class_type"] == "VAEEncode"
    img = wf[enc["inputs"]["pixels"][0]]
    assert img["class_type"] == "LoadImage" and img["inputs"]["image"] == "ref.png"
    # VAE 必須接到工作流既有的 VAE 來源，不可憑空造一個 loader
    assert enc["inputs"]["vae"] == ops._find_vae_ref(_load("AnimaStandardV7.json"))


def test_inject_img2img_denoise_written_to_shared_param_node():
    """雙真相鎖：AnimaStandardV7 的 denoise 由 node 24 分送 KSampler 與 metadata。
    denoise 必須寫到 node 24，否則 PNG metadata 會記錯值。"""
    wf = _load("AnimaStandardV7.json")
    ks = ops._find_main_ksampler_id(wf)
    ref = wf[ks]["inputs"]["denoise"]
    assert isinstance(ref, list), "前提變了：denoise 不再是節點參照，請重新確認本測試"
    src_id = str(ref[0])

    ops._inject_img2img(wf, "ref.png", 0.55)

    assert wf[src_id]["inputs"]["denoise"] == 0.55
    # KSampler 仍透過參照取值 → 兩個消費端同源
    assert wf[ks]["inputs"]["denoise"] == ref


def test_inject_img2img_missing_ksampler_returns_false():
    assert ops._inject_img2img({}, "ref.png", 0.5) is False


def test_inject_img2img_missing_vae_returns_false():
    wf = {"1": {"class_type": "KSampler", "inputs": {"latent_image": ["2", 0], "denoise": 1.0}}}
    assert ops._inject_img2img(wf, "ref.png", 0.5) is False


# ── B-3'：_set_node_input 上游參數覆寫 ────────────────────────────────────────

def test_set_node_input_literal_in_place():
    wf = {"1": {"class_type": "EmptyLatentImage", "inputs": {"width": 512}}}
    assert ops._set_node_input(wf, "1", "width", 1024) is True
    assert wf["1"]["inputs"]["width"] == 1024


def test_set_node_input_follows_primitive_source():
    """easy int 這類參數節點 → 寫到來源的 value，讓 metadata 等消費端同步。"""
    wf = {
        "1": {"class_type": "easy int", "inputs": {"value": 832}},
        "2": {"class_type": "EmptyLatentImage", "inputs": {"width": ["1", 0]}},
        "3": {"class_type": "Image Saver", "inputs": {"width": ["1", 0]}},
    }
    assert ops._set_node_input(wf, "2", "width", 1024) is True
    assert wf["1"]["inputs"]["value"] == 1024
    assert wf["2"]["inputs"]["width"] == ["1", 0]   # 仍為參照 → 兩端同源
    assert wf["3"]["inputs"]["width"] == ["1", 0]


def test_set_node_input_follows_same_named_source_key():
    """作者型參數節點（Input Parameters (Image Saver)）用同名 key。"""
    wf = {
        "24": {"class_type": "Input Parameters (Image Saver)",
               "inputs": {"steps": 30, "cfg": 4, "denoise": 1}},
        "6": {"class_type": "KSampler", "inputs": {"steps": ["24", 1]}},
    }
    assert ops._set_node_input(wf, "6", "steps", 45) is True
    assert wf["24"]["inputs"]["steps"] == 45


def test_set_node_input_unresolvable_source_falls_back_and_reports_false():
    """來源不可解析時退為字面值，但要回 False 讓呼叫端知道 metadata 可能不同步。"""
    wf = {"6": {"class_type": "KSampler", "inputs": {"steps": ["99", 1]}}}
    assert ops._set_node_input(wf, "6", "steps", 45) is False
    assert wf["6"]["inputs"]["steps"] == 45


def test_set_node_input_missing_node():
    assert ops._set_node_input({}, "nope", "steps", 1) is False


def test_v37_resolution_override_reaches_metadata():
    """V37 的 width/height 同樣是 easy int 參照，且同時餵 EmptyLatentImage 與 Image Saver。
    改動後兩者同源 —— 出圖尺寸不變，metadata 由『恆記工作流內建值』修正為實際值。"""
    wf = _load("Standard_V37.json")
    el = next(k for k, v in wf.items()
              if isinstance(v, dict) and v.get("class_type") == "EmptyLatentImage")
    w_ref = wf[el]["inputs"]["width"]
    if not isinstance(w_ref, list):
        pytest.skip("V37 width 非節點參照，本情境不適用")

    ops._set_node_input(wf, el, "width", 768)

    assert wf[str(w_ref[0])]["inputs"]["value"] == 768
    savers = [v for v in wf.values()
              if isinstance(v, dict) and v.get("class_type", "").startswith("Image Saver")]
    for s in savers:
        if isinstance(s["inputs"].get("width"), list):
            assert str(s["inputs"]["width"][0]) == str(w_ref[0])


# ── E-1 / E-2：單張全身插畫模式（2026-07-26）──────────────────────────────────

def test_fullbody_suffix_is_single_illustration():
    """E-1：suffix 不得再出現 design/reference sheet，且必含 solo。

    直接執行組裝函式而非只驗常數 —— 這段字串會原封不動送進 SD。
    """
    from app.services.ai.character_design_service import _build_fullbody_suffix
    suffix = _build_fullbody_suffix(", light red background")
    low = suffix.lower()
    for banned in ("design sheet", "reference sheet", "multiple views"):
        assert banned not in low, banned
    assert "character illustration" in low
    assert "full body portrait" in low
    assert "solo" in low
    assert "front view" in low
    assert low.endswith(", light red background")


def test_fullbody_suffix_survives_sheet_strip():
    """E-1 × E-2 交互：suffix 本身不得被 _strip_sheet_tags 誤刪任何 tag。"""
    from app.services.ai.character_design_service import _build_fullbody_suffix
    from app.services.ai.image_ops import _strip_sheet_tags
    suffix = _build_fullbody_suffix(", white background")
    before = [t.strip() for t in suffix.split(",") if t.strip()]
    after = [t.strip() for t in _strip_sheet_tags(suffix).split(",") if t.strip()]
    assert before == after


def test_strip_sheet_tags_drops_llm_sheet_synonyms():
    """E-2：LLM 常吐的三種同義寫法都要被剝除，其餘 tag 原形保留。"""
    from app.services.ai.image_ops import _strip_sheet_tags
    out = _strip_sheet_tags(
        "1girl, solo, character design reference sheet, character sheet, "
        "(multiple views:1.1), multiple poses, turnaround sheet, full body, white hair"
    )
    assert out == "1girl, solo, full body, white hair"


def test_strip_sheet_tags_noop_on_clean_prompt():
    from app.services.ai.image_ops import _strip_sheet_tags
    p = "1girl, solo, full body, front view, standing, simple background"
    assert _strip_sheet_tags(p) == p


# ── A3 P1-3 / D3（2026-08-22）：「無 sheet 結尾」的設定稿語義漏網 ──────────────
# 案例一當前圖與案例二現在圖的 prompt 都含 "character design reference"（結尾無
# "sheet"），原正則要求 sheet 結尾 → 整條漏網，未被 E-2 的剝除機制擋下。
# 先列保留/移除清單再改正則（CLAUDE.md 編程檢查點 §4 + 規劃書風險項）。

def test_strip_sheet_tags_drops_no_sheet_suffix_variant():
    """D3 核心案例：character design reference（無 sheet）必須被剝除。"""
    from app.services.ai.image_ops import _strip_sheet_tags
    out = _strip_sheet_tags(
        "1girl, solo, character design reference, full body, white hair"
    )
    assert out == "1girl, solo, full body, white hair"


def test_strip_sheet_tags_preserves_legit_character_tags():
    """正則放寬不可誤傷合法 character/design 相關 tag（風險項：character illustration 必留）。"""
    from app.services.ai.image_ops import _strip_sheet_tags
    p = (
        "1girl, solo, character illustration, character design, "
        "reference photo, game design, full body"
    )
    assert _strip_sheet_tags(p) == p


# ── G-1 / G-2：V37 profile 品質段（2026-07-26）────────────────────────────────

def test_v37_profile_quality_prefix_and_suffix_golden():
    """G-5 golden：profile 層（非 family 層）的品質段定版鎖。
    2026-08-12 R4-C/D/E 改版 —— 回滾 G-1 美學加權段、停用 G-2 尾綴、negative 去 sketch。"""
    from app.services.ai.workflow_builder import _load_prompt_profiles
    p = _load_prompt_profiles()["Standard_V37.json"]
    # R4-C：樸素三段，不含美學/年份 tag
    assert p["quality_prefix"] == "masterpiece, best quality, absurdres"
    for tag in ("newest", "very aesthetic", "highres"):
        assert tag not in p["quality_prefix"]
    # R4-D：尾綴美學段停用 → 該欄位不得登錄（登錄空字串也算停用，見 _workflow_profile_overrides）
    assert not p.get("quality_suffix")
    # R4-E：sketch 與 clean lineart 訴求對衝 → 移除。tag 級比對避免子字串誤判
    neg_tags = {t.strip() for t in p["negative"].split(",")}
    assert "sketch" not in neg_tags
    # P1-1：環境/投影抑制（R3）；裸 shadow 刻意不加，避免壓掉角色 shading
    for tag in ("drop shadow", "cast shadow", "floor", "ground", "reflection"):
        assert tag in neg_tags
    assert "shadow" not in neg_tags
    # 人設圖 profile 仍禁用場景細節
    assert "detailed background" in p["negative"]


def test_v37_profile_overrides_reach_compiler_kwargs():
    """profile → compile_prompt kwargs 的欄位對映（只驗登錄欄位有轉成 *_override）。"""
    from app.services.ai.workflow_builder import _workflow_profile_overrides
    ov = _workflow_profile_overrides("Standard_V37.json")
    assert ov["quality_prefix_override"] == "masterpiece, best quality, absurdres"
    assert ov["negative_override"].startswith("worst quality, low quality, lowres")
    # R4-D：未登錄欄位不佔位，讓 compile() 的 family fallback 維持有效
    assert "quality_suffix_override" not in ov


def test_weight_group_expansion_still_works():
    """權重群組語法要能展開進 banned_tags，否則 LLM 重複吐 highres/absurdres/
    very aesthetic 時去重失效、正向被灌爆。

    2026-08-12：R4-C 回滾後 V37 profile 已不含權重語法，本測試改用 G-1 原文當固定
    樣本 —— 鎖的是**展開機制**，不是某個 profile 的當期內容。日後任何 profile 重新
    啟用權重語法時，這條仍是有效防線。"""
    from app.services.ai.prompt_engine.styles import _WEIGHT_GROUP_RE
    sample = ("masterpiece, best quality, (newest:0.6), "
              "(highres, absurdres, very aesthetic:0.8)")
    expanded = _WEIGHT_GROUP_RE.sub(r"\1", sample)
    tags = {t.strip().lower() for t in expanded.split(",") if t.strip()}
    for t in ("newest", "highres", "absurdres", "very aesthetic", "masterpiece", "best quality"):
        assert t in tags, t


# ── H-3：Image Saver metadata prompt 與實跑同源（2026-07-26）──────────────────

@pytest.mark.parametrize("wf_name", ["Standard_V37.json", "AnimaStandardV7.json"])
def test_saver_metadata_prompt_matches_injected(wf_name):
    """注入後 saver 的 positive/negative 必須是實際送出值，不再是內建 wildcard 鏈參照。"""
    wf = _load(wf_name)
    savers = [v for v in wf.values()
              if isinstance(v, dict) and str(v.get("class_type", "")).startswith("Image Saver")
              and "positive" in v.get("inputs", {})]
    if not savers:
        pytest.skip(f"{wf_name} 無帶 prompt 欄位的 Image Saver 節點")
    assert any(isinstance(s["inputs"]["positive"], list) for s in savers), \
        "前提失效：改動前 positive 應為節點參照"

    ops._inject_prompts(wf, "POS_ACTUAL", "NEG_ACTUAL")

    for s in savers:
        assert s["inputs"]["positive"] == "POS_ACTUAL"
        assert s["inputs"]["negative"] == "NEG_ACTUAL"


def test_saver_metadata_sync_is_noop_without_saver():
    assert ops._sync_saver_prompt_metadata({}, "p", "n") == 0


def test_inject_prompts_still_writes_clip_text_encode():
    """H-3 零回歸：saver 同步不得取代原本的 CLIPTextEncode 注入。"""
    wf = _load("Standard_V37.json")
    ops._inject_prompts(wf, "POS_ACTUAL", "NEG_ACTUAL")
    texts = {n["inputs"].get("text") for n in wf.values()
             if isinstance(n, dict) and n.get("class_type") == "CLIPTextEncode"}
    assert "POS_ACTUAL" in texts and "NEG_ACTUAL" in texts


# ── L1/L2（2026-08-12）：Anima ControlNet-LLLite 接入 ─────────────────────────
# 節點 schema 取自 kohya-ss/ComfyUI-Anima-LLLite 的 nodes.py（非猜測）：
#   AnimaLLLiteApply(model, lllite_name, image, strength, start_percent,
#                    end_percent, preserve_wrapper, [mask]) -> (MODEL,)

def test_lllite_injects_into_ksampler_model_chain():
    """核心：LLLite 走 **MODEL 層**。KSampler.model 要改指向新節點，
    且原 model 來源要接到 LLLite 的 model 輸入（不是被丟掉）。"""
    wf = _load("AnimaStandardV7.json")
    ks_id = ops._find_main_ksampler_id(wf)
    orig_model_src = wf[ks_id]["inputs"]["model"]
    orig_latent = wf[ks_id]["inputs"].get("latent_image")

    assert ops._inject_lllite(wf, "ref.png", "anima-lllite-any-test-like-v2.safetensors",
                              0.7, end_percent=0.85,
                              node_class="AnimaLLLiteApply_sdscripts") is True

    new_src = wf[ks_id]["inputs"]["model"]
    assert new_src != orig_model_src, "KSampler.model 沒有改接"
    node = wf[new_src[0]]
    # 2026-08-17：class_type 由呼叫端傳入（capability 探測到的實名），不再寫死；
    # kohya 2026-08-02 commit b7495bd 已把註冊名改成 *_sdscripts。
    assert node["class_type"] == "AnimaLLLiteApply_sdscripts"
    inp = node["inputs"]
    assert inp["model"] == orig_model_src, "原 model 來源必須串進 LLLite，不可丟棄"
    assert inp["lllite_name"] == "anima-lllite-any-test-like-v2.safetensors"
    assert inp["strength"] == 0.7
    assert inp["start_percent"] == 0.0 and inp["end_percent"] == 0.85
    assert inp["preserve_wrapper"] is True
    assert "mask" not in inp, "any-test-like 是 3ch 權重，接 mask 會被節點警告並忽略"
    # 餵圖的 LoadImage
    img_node = wf[inp["image"][0]]
    assert img_node["class_type"] == "LoadImage"
    assert img_node["inputs"]["image"] == "ref.png"
    # ⚠️ latent 不得被動到 —— LLLite 與 img2img 互斥，同時套用會讓條件與污染的 latent 打架
    assert wf[ks_id]["inputs"].get("latent_image") == orig_latent


def test_lllite_does_not_touch_original_workflow_file():
    """使用者要求不改 workflow 檔：注入只動記憶體 dict，重新載入應為原狀。"""
    wf = _load("AnimaStandardV7.json")
    ops._inject_lllite(wf, "ref.png", "w.safetensors", 1.0)
    assert not ops._wf_has_lllite(_load("AnimaStandardV7.json")), \
        "原始 JSON 被寫入了 LLLite 節點"


def test_lllite_not_injected_twice():
    wf = _load("AnimaStandardV7.json")
    assert ops._inject_lllite(wf, "a.png", "w.safetensors", 1.0) is True
    assert ops._inject_lllite(wf, "b.png", "w.safetensors", 1.0) is False


def test_lllite_returns_false_without_ksampler():
    """Resilient errors：注入失敗要回 False 讓呼叫端退 img2img，不可丟例外。"""
    assert ops._inject_lllite({}, "a.png", "w.safetensors", 1.0) is False
    assert ops._inject_lllite({"1": {"class_type": "KSampler", "inputs": {}}},
                              "a.png", "w.safetensors", 1.0) is False


def test_pick_lllite_weight_ignores_sdxl_controlnets():
    """controlnet 目錄同時放著 SDXL ControlNet，盲抓第一個會把 2.5GB 的 SDXL 權重
    餵給 LLLite 節點載入失敗。"""
    from app.services.comfyui_client import pick_lllite_weight
    sdxl_only = ["controlnet-scribble-sdxl-1.0.safetensors",
                 "diffusion_pytorch_model_promax.safetensors"]
    assert pick_lllite_weight(sdxl_only) is None
    mixed = sdxl_only + ["anima-lllite-any-test-like-v2.safetensors"]
    assert pick_lllite_weight(mixed) == "anima-lllite-any-test-like-v2.safetensors"
    # 首選不在時退而求其次，但仍須是 lllite 檔
    assert pick_lllite_weight(sdxl_only + ["anima-lllite-scribble-1.safetensors"]) == \
        "anima-lllite-scribble-1.safetensors"
    assert pick_lllite_weight([]) is None


def test_anima_profile_fallback_chain_and_compat_property():
    """候選鏈取代單值，但 cn_fallback 相容欄位要留著 —— capability 與前端都還在讀它，
    改名一路貫通到 UI 才不會讓後端替代路徑變成死代碼（2026-07-25 已付過學費）。"""
    from app.services.ai.gen_profile import get_profile
    a = get_profile("anima")
    assert a.cn_fallback_chain == ("lllite", "img2img"), "lllite 必須排在 img2img 前"
    assert a.cn_fallback == "lllite"
    for fam in ("sdxl", "illustrious"):
        p = get_profile(fam)
        assert p.cn_fallback_chain == () and p.cn_fallback is None, f"{fam} 零回歸"


def test_lllite_detection_degrades_gracefully(monkeypatch):
    """ComfyUI 連不上／節點沒裝／權重沒放，都要安靜退回 None 而不是炸掉。"""
    from app.services.ai import capability as cap
    from app.services import comfyui_client

    monkeypatch.setattr(comfyui_client, "detect_lllite",
                        lambda: {"available": False, "weights": [], "reason": "節點未安裝"})
    assert cap._resolve_lllite_weight() is None

    monkeypatch.setattr(comfyui_client, "detect_lllite",
                        lambda: {"available": True,
                                 "weights": ["controlnet-scribble-sdxl-1.0.safetensors"]})
    assert cap._resolve_lllite_weight() is None, "只有 SDXL 權重時不得誤判為可用"

    def _boom():
        raise RuntimeError("connection refused")
    monkeypatch.setattr(comfyui_client, "detect_lllite", _boom)
    assert cap._resolve_lllite_weight() is None, "例外必須被吞掉"


def test_capability_falls_back_to_img2img_when_lllite_unavailable(monkeypatch):
    """候選鏈的核心行為：lllite 不可用 → 自動退 img2img（＝改動前的既有行為）。"""
    from app.services.ai import capability as cap
    wf = _load("AnimaStandardV7.json")
    ckpt = ops.extract_checkpoint_from_wf(wf) if hasattr(ops, "extract_checkpoint_from_wf") \
        else cap.extract_checkpoint_from_wf(wf)

    monkeypatch.setattr(cap, "_resolve_lllite_weight", lambda: None)
    out = cap.resolve_capability(wf, ckpt)
    assert out["cn_supported"] is False
    assert out["cn_fallback"] == "img2img"
    assert out["lllite_weight"] is None

    monkeypatch.setattr(cap, "_resolve_lllite_weight",
                        lambda: "anima-lllite-any-test-like-v2.safetensors")
    out2 = cap.resolve_capability(wf, ckpt)
    assert out2["cn_fallback"] == "lllite"
    assert out2["lllite_weight"] == "anima-lllite-any-test-like-v2.safetensors"


def test_v37_capability_unaffected_by_lllite(monkeypatch):
    """零回歸鎖：SDXL/V37 路徑 cn_supported=True，根本不該走進候選鏈解析。"""
    from app.services.ai import capability as cap
    called = {"n": 0}

    def _spy():
        called["n"] += 1
        return "should-not-be-used.safetensors"
    monkeypatch.setattr(cap, "_resolve_lllite_weight", _spy)

    wf = _load("Standard_V37.json")
    out = cap.resolve_capability(wf, cap.extract_checkpoint_from_wf(wf))
    assert out["cn_supported"] is True
    assert out["cn_fallback"] is None and out["lllite_weight"] is None
    assert called["n"] == 0, "V37 不該觸發 LLLite 偵測（多打一次 ComfyUI API）"
