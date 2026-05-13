import json
from dataclasses import dataclass, field
from pathlib import Path

from diffusion.comfyui_provider import ComfyUIProvider

_WORKFLOW_PATH = Path(__file__).parent.parent / "diffusion" / "workflows" / "style_enhance.json"

# Node IDs defined in style_enhance.json
_NODE_SKETCH = "2"
_NODE_STYLE_REF = "3"
_NODE_IPADAPTER = "6"


@dataclass
class EnhanceResult:
    input_path: str
    style_refs: list[str]
    output_path: str | None
    mode: str  # "enhance" | "style_explore"
    success: bool
    message: str
    warnings: list[str] = field(default_factory=list)


class ArtEnhancer:
    """
    Combines IP-Adapter (style) + ControlNet (structure) to produce
    a style-consistent, quality-improved version of a sketch.

    enhance:       style_refs = user's own finished artwork → preserves personal style
    style_explore: style_refs = any target style artwork  → explores different styles
    """

    # IP-Adapter weight per mode:
    # enhance uses higher weight to stay close to the personal style reference.
    # style_explore uses lower weight so the base model blends the target style more loosely.
    _WEIGHTS = {
        "enhance": 0.85,
        "style_explore": 0.65,
    }

    def __init__(self, output_dir: str = "./analysis", comfyui_url: str = "http://localhost:8188"):
        self.comfyui = ComfyUIProvider(base_url=comfyui_url)
        self.output_dir = Path(output_dir)

    def enhance(self, image_path: str, style_refs: list[str]) -> EnhanceResult:
        """Primary mode: produce a commercial-quality version in the user's own style."""
        return self._run(image_path, style_refs, mode="enhance")

    def style_explore(self, image_path: str, style_refs: list[str]) -> EnhanceResult:
        """Secondary mode: see the sketch rendered in a different art style."""
        return self._run(image_path, style_refs, mode="style_explore")

    # ------------------------------------------------------------------

    def _run(self, image_path: str, style_refs: list[str], mode: str) -> EnhanceResult:
        if not style_refs:
            return EnhanceResult(
                input_path=image_path,
                style_refs=[],
                output_path=None,
                mode=mode,
                success=False,
                message="At least one style reference image is required (--style-ref).",
            )

        if not self.comfyui.is_available():
            return EnhanceResult(
                input_path=image_path,
                style_refs=style_refs,
                output_path=None,
                mode=mode,
                success=False,
                message=(
                    "ComfyUI is not running. "
                    "Please start it first (cd ComfyUI && python main.py --listen)."
                ),
            )

        with open(_WORKFLOW_PATH, encoding="utf-8") as f:
            workflow = json.load(f)
        workflow.pop("_comment", None)

        # Upload images and inject into workflow nodes
        sketch_name = self.comfyui.upload_image(image_path)
        style_name = self.comfyui.upload_image(style_refs[0])

        workflow[_NODE_SKETCH]["inputs"]["image"] = sketch_name
        workflow[_NODE_STYLE_REF]["inputs"]["image"] = style_name
        workflow[_NODE_IPADAPTER]["inputs"]["weight"] = self._WEIGHTS[mode]

        # Multiple style refs: average embedding by uploading all and blending
        # (single ref is the common case; extras are stored in warnings for now)
        warnings = []
        if len(style_refs) > 1:
            warnings.append(
                f"Only the first style reference image is used. "
                f"({len(style_refs) - 1} additional file(s) ignored — "
                f"multi-ref blending will be added in a future update.)"
            )

        prompt_id = self.comfyui.submit_workflow(workflow)

        try:
            filenames = self.comfyui.wait_for_result(prompt_id)
        except TimeoutError as e:
            return EnhanceResult(
                input_path=image_path, style_refs=style_refs,
                output_path=None, mode=mode, success=False, message=str(e),
            )

        if not filenames:
            return EnhanceResult(
                input_path=image_path, style_refs=style_refs,
                output_path=None, mode=mode, success=False,
                message="ComfyUI returned no output. Check the workflow configuration.",
            )

        img_data = self.comfyui.download_image(filenames[0])
        self.output_dir.mkdir(parents=True, exist_ok=True)
        stem = Path(image_path).stem
        out_path = self.output_dir / f"{stem}_{mode}.png"
        out_path.write_bytes(img_data)

        return EnhanceResult(
            input_path=image_path,
            style_refs=style_refs,
            output_path=str(out_path),
            mode=mode,
            success=True,
            message="Generated successfully.",
            warnings=warnings,
        )
