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


@dataclass(frozen=True)
class GenProfile:
    family: str
    # 主 KSampler steps（後端覆寫工作流 KSampler.steps；人設全身用）。
    steps: int = 20
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


# family → profile。未列家族走 _DEFAULT（= 現況 SDXL 行為，零變更）。
_DEFAULT = GenProfile(family="sdxl")

GEN_PROFILE: dict[str, GenProfile] = {
    "sdxl":        _DEFAULT,
    "pony":        GenProfile(family="pony"),
    "noobai":      GenProfile(family="noobai"),
    # Illustrious（含 fabricatedXL_v70，即 V36 主路線）：
    # steps 略增 20→26（fabricatedXL 建議 18–30；補臉/細節），其餘沿用 SDXL 基線。
    # illustrious(fabricatedXL_v70=V36/V35 主底模):對齊真 V35 內建鏈→AnimeLineArt(預設)
    "illustrious": GenProfile(family="illustrious", steps=26),
    # 未來 Anima（非 SDXL，無 IPA，CN 僅 LLLite）：佔位，待 F4 落地。
    # "anima":     GenProfile(family="anima", ipa_enabled=False, cn_enabled=False),
}


def get_profile(family: str) -> GenProfile:
    return GEN_PROFILE.get(family, _DEFAULT)


def resolve_profile_for_workflow(workflow_name: str) -> tuple[GenProfile, str]:
    """讀 active workflow 內嵌 checkpoint → family → profile。

    custom workflow（如 V36）的 checkpoint 內嵌於 JSON（不被全域覆寫），是實際生成所用，
    故以工作流內嵌值為準；讀不到才退回 state.get_checkpoint()。
    回傳 (profile, family)。任何錯誤 → (_DEFAULT, 'sdxl')，不讓生成 crash。
    """
    ckpt = ""
    try:
        from app.services.ai.workflow_builder import _load_workflow
        wf = _load_workflow(workflow_name)
        ckpt = next(
            (n["inputs"].get("ckpt_name", "") for n in wf.values()
             if isinstance(n, dict) and n.get("class_type") == "CheckpointLoaderSimple"),
            "",
        ) or ""
    except Exception as e:
        logger.warning("[gen_profile] 讀工作流 checkpoint 失敗（%s），改用全域 checkpoint", e)
    if not ckpt:
        try:
            from app.core import state
            ckpt = state.get_checkpoint() or ""
        except Exception:
            ckpt = ""
    try:
        from app.services.ai.capability import resolve_family
        family = resolve_family(ckpt)
    except Exception:
        family = "sdxl"
    return get_profile(family), family
