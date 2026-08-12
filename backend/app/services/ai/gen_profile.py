"""每家族生成策略 profile（GEN_PROFILE）。

2026-06-20 (R3)：把原散落於 character_design_service 的生成決策常數
（主 KSampler steps、coverage→CN 上限與 end_percent、full coverage 的 CN 行為）
集中為「依 checkpoint family 的單一真相來源」。換家族（如未來 Anima）只需補一組 profile，
不必散改生成流程。

family 來源：capability.resolve_family(checkpoint)（checkpoint_styles.yml `families` 區段）。
未知家族 → fallback 'sdxl'（零行為變更）。

注意：cfg / sampler / scheduler / FaceDetailer 參數寫在 workflow JSON（node 級，後端不覆寫），
不在此 profile；此處只放「後端會動態覆寫工作流」的參數。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# CN 強度滑桿定義域（與前端 CharacterDetailView 的 <input type="range"> min/max 一致）。
# img2img 換算以此為錨做線性映射；前端改動範圍時此處必須同步，否則端點語義失準。
CN_WEIGHT_SLIDER_MIN = 0.1
CN_WEIGHT_SLIDER_MAX = 1.5


@dataclass(frozen=True)
class GenProfile:
    family: str
    # 主 KSampler steps（人設全身用）。None = 不覆寫，沿用 workflow JSON 內建的
    # KSampler.steps（R3，2026-07-12：對齊本檔案自身原則「node 級參數寫在 workflow
    # JSON，後端不覆寫」——steps 過去無條件覆寫屬歷史遺留）。
    steps: int | None = 20
    # coverage → CN 強度上限（partial/bust 概念圖為半身，下半需 SD 腦補；
    # CN 過強會把「下半留空」也當硬約束 → 缺腿。None=不夾、沿用滑桿值）。
    coverage_cn_weight: dict = field(default_factory=lambda: {"partial": 0.6, "bust": 0.5})
    # coverage → CN end_percent override（full 設 0.85：最後 15% 步釋放 CN 讓底模補細節）。
    coverage_cn_end_pct: dict = field(default_factory=lambda: {"full": 0.85})
    # full coverage（本就全身概念圖）的 CN 上限。
    #   None = 不夾、沿用滑桿（維持 CN≥0.75 畫風一致；= 現況行為）。
    #   設一個值（如 0.6）= Q3「降/關強制 CN、還底模自由」開關：改善 V36 全身品質，
    #   但會降低與概念圖貼合，與「CN≥0.75 一致性」是取捨，需實機 A/B 後再定值。
    full_cn_weight: float | None = None
    # CN preprocessor：'canny'(V35 附件三 proven，較鬆、留底模上色空間) 或
    # 'anime_lineart'(乾淨線稿但易平塗)。pre-ref 外擴(彩色圖)由呼叫端強制改 anime_lineart。
    cn_preprocessor: str = "anime_lineart"
    cn_canny_low: int = 100
    cn_canny_high: int = 200
    cn_resolution: int = 1024
    # 能力閘控（多家族用；未來 Anima 無 IP-Adapter → ipa_enabled=False）。
    ipa_enabled: bool = True
    cn_enabled: bool = True
    # CN 停用時的替代結構控制路徑（2026-07-25 D'-2）。
    #   None      = 無替代（家族本就支援 CN，或不需要）。
    #   "img2img" = 參考圖走 VAEEncode 進 latent + 低 denoise 貼合構圖。
    # 用於 Anima：官方明言不支援 ControlNet，但仍需依草圖控制構圖。
    cn_fallback: str | None = None
    # img2img denoise 換算：把 CN 強度滑桿【全域線性】映射到 [min, max]。
    # cn_weight 語義是「越高越貼合參考圖」，denoise 相反（越低越貼合）→ 反向映射。
    # 2026-08-05：原公式 `1 - cn_weight * scale` 的值域與滑桿定義域無關，
    # 兩端都會撞 clamp → 產生死區（舊值 scale=0.6/min=0.35 時，1.08 以上完全無效）。
    # 改為以滑桿兩端為錨的線性映射：滑桿全段單調有效、永不出現死區，
    # 且端點語義明確（滑桿底＝底模自由發揮、滑桿頂＝最大程度照抄草圖）。
    img2img_denoise_min: float = 0.35
    img2img_denoise_max: float = 0.85

    def img2img_denoise(self, cn_weight: float) -> float:
        """CN 強度滑桿 → img2img denoise（線性反向映射，無死區）。

        cn_weight = CN_WEIGHT_SLIDER_MIN → img2img_denoise_max（最自由）
        cn_weight = CN_WEIGHT_SLIDER_MAX → img2img_denoise_min（最貼合）
        定義域外的值先夾到滑桿範圍內，確保回傳恆落在 [min, max]。
        """
        span = CN_WEIGHT_SLIDER_MAX - CN_WEIGHT_SLIDER_MIN
        ratio = (float(cn_weight) - CN_WEIGHT_SLIDER_MIN) / span
        ratio = min(1.0, max(0.0, ratio))
        d_span = self.img2img_denoise_max - self.img2img_denoise_min
        return round(self.img2img_denoise_max - ratio * d_span, 2)


# family → profile。未列家族走 _DEFAULT（= 現況 SDXL 行為，零變更）。
_DEFAULT = GenProfile(family="sdxl")

GEN_PROFILE: dict[str, GenProfile] = {
    "sdxl":        _DEFAULT,
    "pony":        GenProfile(family="pony"),
    "noobai":      GenProfile(family="noobai"),
    # Illustrious（含 fabricatedXL_v70，即 V36/V37 主路線）：
    # steps=None（R3，2026-07-12）：不覆寫，沿用各 workflow JSON 內建值（V36=28、
    # AnimaV7=30，皆在 fabricatedXL 建議區間 18–30 內）。原本硬覆寫 26 是歷史遺留，
    # 與 V37「採樣端已對齊官方配方、零調整」的前提矛盾，已改用 workflow 自身的值。
    # illustrious(fabricatedXL_v70=V36/V35 主底模):對齊真 V35 內建鏈→AnimeLineArt(預設)
    "illustrious": GenProfile(family="illustrious", steps=None),
    # Anima（非 SDXL：UNETLoader + Qwen 文字編碼器；無 IP-Adapter、CN 僅 LLLite）：
    # 2026-07-14 啟用 G0 能力閘控——ipa_enabled/cn_enabled=False 讓角色/變體生成流程
    # 不把 SDXL IPA/ControlNet 節點注入 Anima UNet（架構不符會維度錯誤/靜默失效）。
    # steps=None：AnimaV7 KSampler 由內部節點鏈驅動（steps 為節點參照），後端不覆寫。
    # 2026-07-25：cn_fallback="img2img" —— Anima 官方不支援 ControlNet（亦無 LLLite），
    # 但使用者仍需草圖構圖控制 → 以 img2img 低 denoise 替代（D'-2）。
    # ipa_enabled 維持 False：Anima 無對應 adapter，替代路徑是既有的 vision→prompt
    # （use_vision，不受此閘控影響）。
    # 2026-08-05：img2img 換算改為滑桿全域線性映射（見 GenProfile.img2img_denoise），
    # 並把下限放到 0.20 —— Anima 沒有 ControlNet，結構控制全靠 denoise 這一個旋鈕，
    # 要達到接近 SDXL ControlNet 的輪廓貼合度，滑桿頂端必須壓得夠低。
    # 對照表（滑桿 → denoise）：0.10→0.85、0.50→0.66、0.75→0.55、1.00→0.43、
    #                          1.25→0.31、1.50→0.20
    # ⚠️ 0.20 是下限候選值，尚未實測定案——denoise 過低會把草圖的粉底/鉛筆線一併留下，
    # 貼合度與畫質是取捨，需實機 A/B 後回填定案值。
    "anima":       GenProfile(family="anima", steps=None, ipa_enabled=False,
                              cn_enabled=False, cn_fallback="img2img",
                              img2img_denoise_min=0.20),
}


def get_profile(family: str) -> GenProfile:
    return GEN_PROFILE.get(family, _DEFAULT)


def resolve_profile_for_workflow(workflow_name: str) -> tuple[GenProfile, str]:
    """讀 active workflow 內嵌 checkpoint → family → profile。

    custom workflow（如 V36）的 checkpoint 內嵌於 JSON（不被全域覆寫），是實際生成所用，
    故以工作流內嵌值為準；讀不到才退回 state.get_checkpoint()。
    回傳 (profile, family)。任何錯誤 → (_DEFAULT, 'sdxl')，不讓生成 crash。
    """
    # 2026-07-25 AC-2'：checkpoint 解析改用 capability.resolve_checkpoint_for_workflow
    # （原本此處自帶一份 UNETLoader fallback，與 _detect_style / capability caller 各自為政
    #  → 同一工作流被解析成不同 family）。改為三處共用同一函式，避免再分歧。
    try:
        from app.services.ai.capability import resolve_checkpoint_for_workflow, resolve_family
        ckpt = resolve_checkpoint_for_workflow(workflow_name)
        family = resolve_family(ckpt)
    except Exception as e:
        logger.warning("[gen_profile] family 解析失敗（%s），fallback sdxl", e)
        family = "sdxl"
    return get_profile(family), family
