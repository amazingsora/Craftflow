"""
影像編輯 workflow 改造（P5：inpainting / upscale）。

兩者皆以 text_to_image 型 workflow（CheckpointLoader + CLIPTextEncode×2 +
EmptyLatentImage + KSampler + VAEDecode）為基底做原地改造：
- inpaint：EmptyLatentImage → VAEEncodeForInpaint（原節點 id 保留，KSampler 連線不動）
- upscale：EmptyLatentImage → VAEEncode + LatentUpscaleBy（hires-fix，低 denoise 重採樣）

只用 ComfyUI 核心節點，不需安裝額外模型/custom nodes。
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_DEFAULT_GROW_MASK = 6  # 遮罩外擴像素，緩和接縫


class WorkflowShapeError(ValueError):
    """workflow 缺少必要節點（非 text_to_image 型）。"""


def _find_node(wf: dict, class_type: str) -> str:
    for nid, n in wf.items():
        if isinstance(n, dict) and n.get("class_type") == class_type:
            return nid
    raise WorkflowShapeError(f"workflow 缺少 {class_type} 節點，請改用標準 txt2img workflow")


def to_inpaint_workflow(
    wf: dict,
    canvas_name: str,
    mask_name: str,
    denoise: float,
    grow_mask: int = _DEFAULT_GROW_MASK,
) -> None:
    """把 txt2img workflow 原地改成 inpaint（白色遮罩區 = 重繪區）。"""
    ckpt_id = _find_node(wf, "CheckpointLoaderSimple")
    latent_id = _find_node(wf, "EmptyLatentImage")
    ksampler_id = _find_node(wf, "KSampler")

    wf["_inp_img"] = {"class_type": "LoadImage", "inputs": {"image": canvas_name}}
    wf["_inp_mask_img"] = {"class_type": "LoadImage", "inputs": {"image": mask_name}}
    # 用 red channel 轉遮罩：黑白遮罩圖不依賴 alpha
    wf["_inp_mask"] = {
        "class_type": "ImageToMask",
        "inputs": {"image": ["_inp_mask_img", 0], "channel": "red"},
    }
    # 原節點 id 換成 VAEEncodeForInpaint → KSampler.latent_image 連線無需改
    wf[latent_id] = {
        "class_type": "VAEEncodeForInpaint",
        "inputs": {
            "pixels": ["_inp_img", 0],
            "vae": [ckpt_id, 2],
            "mask": ["_inp_mask", 0],
            "grow_mask_by": int(grow_mask),
        },
    }
    wf[ksampler_id]["inputs"]["denoise"] = round(float(denoise), 2)
    logger.info("[image-edit] inpaint workflow ready (denoise=%.2f, grow=%d)", denoise, grow_mask)


def to_upscale_workflow(
    wf: dict,
    image_name: str,
    scale: float,
    denoise: float,
) -> None:
    """把 txt2img workflow 原地改成 hires-fix upscale（潛空間放大 + 低 denoise 重採樣）。"""
    ckpt_id = _find_node(wf, "CheckpointLoaderSimple")
    latent_id = _find_node(wf, "EmptyLatentImage")
    ksampler_id = _find_node(wf, "KSampler")

    wf["_up_img"] = {"class_type": "LoadImage", "inputs": {"image": image_name}}
    wf["_up_encode"] = {
        "class_type": "VAEEncode",
        "inputs": {"pixels": ["_up_img", 0], "vae": [ckpt_id, 2]},
    }
    # 原節點 id 換成 LatentUpscaleBy → KSampler 連線無需改
    wf[latent_id] = {
        "class_type": "LatentUpscaleBy",
        "inputs": {
            "samples": ["_up_encode", 0],
            "upscale_method": "nearest-exact",
            "scale_by": round(float(scale), 2),
        },
    }
    wf[ksampler_id]["inputs"]["denoise"] = round(float(denoise), 2)
    logger.info("[image-edit] upscale workflow ready (scale=%.2f, denoise=%.2f)", scale, denoise)
