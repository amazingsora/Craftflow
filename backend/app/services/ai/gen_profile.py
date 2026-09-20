# 註解索引：本檔 [CN-xxx] 標記的完整根因記錄見 doc/reference/CODE_NOTES.md
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
    # [CN-079] steps=None＝不覆寫，沿用 workflow JSON 內建值（node 級參數寫在 JSON 的原則）
    steps: int | None = 20
    # coverage → CN 強度上限（partial/bust 概念圖為半身，下半需 SD 腦補；
    # CN 過強會把「下半留空」也當硬約束 → 缺腿。None=不夾、沿用滑桿值）。
    coverage_cn_weight: dict = field(default_factory=lambda: {"partial": 0.6, "bust": 0.5})
    # coverage → CN end_percent override（full 設 0.85：最後 15% 步釋放 CN 讓底模補細節）。
    coverage_cn_end_pct: dict = field(default_factory=lambda: {"full": 0.85})
    # [CN-080] full coverage 的 CN 上限；None=不夾、沿用滑桿（維持 CN≥0.75 畫風一致）
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
    # [CN-081] cn_fallback 是有序候選鏈：lllite（MODEL 層，需執行期偵測）優先，img2img 為退路
    cn_fallback_chain: tuple[str, ...] = ()
    # [CN-082] LLLite strength 是 LoRA-like 乘數（default 1.0、range -10~10），與 CN 的 0~1 權重尺度不同
    lllite_strength_scale: float = 1.0

    @property
    def cn_fallback(self) -> str | None:
        """相容欄位：回傳候選鏈第一項。

        `capability.resolve_capability` 與前端 CapabilityNotice 仍讀這個名字，
        保留它可避免改動一路貫通到 UI（能力旗標沒貫通到 UI 會讓後端替代路徑變成
        死代碼 —— 2026-07-25 已付過一次學費）。
        """
        return self.cn_fallback_chain[0] if self.cn_fallback_chain else None
    # [CN-083] denoise 以滑桿兩端為錨線性映射；舊公式值域與定義域無關，兩端撞 clamp 產生死區
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
    # [CN-084] Illustrious（fabricatedXL_v70＝V36/V37 主路線）profile 與 steps 歷史遺留說明
    "illustrious": GenProfile(family="illustrious", steps=None),
    # [CN-085] Anima profile 決策史：ipa/cn 閘控、img2img→lllite 候選鏈、denoise 下限 0.20 未定案
    "anima":       GenProfile(family="anima", steps=None, ipa_enabled=False,
                              cn_enabled=False,
                              cn_fallback_chain=("lllite", "img2img"),
                              img2img_denoise_min=0.20,
                              lllite_strength_scale=1.0),
}


def get_profile(family: str) -> GenProfile:
    return GEN_PROFILE.get(family, _DEFAULT)


def resolve_profile_for_workflow(workflow_name: str) -> tuple[GenProfile, str]:
    """讀 active workflow 內嵌 checkpoint → family → profile。

    custom workflow（如 V36）的 checkpoint 內嵌於 JSON（不被全域覆寫），是實際生成所用，
    故以工作流內嵌值為準；讀不到才退回 state.get_checkpoint()。
    回傳 (profile, family)。任何錯誤 → (_DEFAULT, 'sdxl')，不讓生成 crash。
    """
    # [CN-086] checkpoint 解析改用 capability.resolve_checkpoint_for_workflow，三處共用避免分歧
    try:
        from app.services.ai.capability import resolve_checkpoint_for_workflow, resolve_family
        ckpt = resolve_checkpoint_for_workflow(workflow_name)
        family = resolve_family(ckpt)
    except Exception as e:
        logger.warning("[gen_profile] family 解析失敗（%s），fallback sdxl", e)
        family = "sdxl"
    return get_profile(family), family
