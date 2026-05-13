import json
from dataclasses import dataclass
from pathlib import Path

from diffusion.comfyui_provider import ComfyUIProvider

_WORKFLOW_PATH = Path(__file__).parent.parent / "diffusion" / "workflows" / "sketch_to_lineart.json"


@dataclass
class LineartResult:
    input_path: str
    output_path: str | None
    success: bool
    message: str


class LineartGenerator:
    def __init__(self, output_dir: str = "./analysis", comfyui_url: str = "http://localhost:8188"):
        self.comfyui = ComfyUIProvider(base_url=comfyui_url)
        self.output_dir = Path(output_dir)

    def generate(self, image_path: str) -> LineartResult:
        if not self.comfyui.is_available():
            return LineartResult(
                input_path=image_path,
                output_path=None,
                success=False,
                message=(
                    "ComfyUI is not running. "
                    "Please start it first (cd ComfyUI && python main.py --listen), "
                    "then re-run this command."
                ),
            )

        with open(_WORKFLOW_PATH, encoding="utf-8") as f:
            workflow = json.load(f)

        # Remove the _comment key (not a real node)
        workflow.pop("_comment", None)

        # Upload input image and inject filename into LoadImage node
        uploaded_name = self.comfyui.upload_image(image_path)
        for node in workflow.values():
            if isinstance(node, dict) and node.get("class_type") == "LoadImage":
                node["inputs"]["image"] = uploaded_name

        prompt_id = self.comfyui.submit_workflow(workflow)

        try:
            filenames = self.comfyui.wait_for_result(prompt_id)
        except TimeoutError as e:
            return LineartResult(input_path=image_path, output_path=None, success=False, message=str(e))

        if not filenames:
            return LineartResult(
                input_path=image_path,
                output_path=None,
                success=False,
                message="ComfyUI returned no output images. Check the workflow configuration.",
            )

        img_data = self.comfyui.download_image(filenames[0])
        self.output_dir.mkdir(parents=True, exist_ok=True)
        stem = Path(image_path).stem
        out_path = self.output_dir / f"{stem}_lineart.png"
        out_path.write_bytes(img_data)

        return LineartResult(
            input_path=image_path,
            output_path=str(out_path),
            success=True,
            message="Lineart generated successfully.",
        )
