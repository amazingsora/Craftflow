"""隱私設定護欄：API 只對本機前端開放、回傳 PNG 不夾帶 prompt。"""
import io

from PIL import Image, PngImagePlugin

from app.core import config
from app.services import comfyui_client


def _png_with_prompt() -> bytes:
    info = PngImagePlugin.PngInfo()
    info.add_text("prompt", '{"6": {"inputs": {"text": "secret prompt"}}}')
    info.add_itxt("workflow", "{}")
    buf = io.BytesIO()
    Image.new("RGB", (4, 4), (1, 2, 3)).save(buf, "PNG", pnginfo=info)
    return buf.getvalue()


def test_cors_is_not_wildcard():
    assert "*" not in config.CORS_ORIGINS
    assert all(o.startswith(("http://localhost", "http://127.0.0.1")) for o in config.CORS_ORIGINS)


def test_strip_png_text_chunks_keeps_pixels():
    raw = _png_with_prompt()
    out = comfyui_client.strip_png_text_chunks(raw)
    assert b"secret prompt" in raw and b"secret prompt" not in out
    assert Image.open(io.BytesIO(out)).tobytes() == Image.open(io.BytesIO(raw)).tobytes()


def test_strip_png_passes_through_non_png_and_truncated():
    raw = _png_with_prompt()
    assert comfyui_client.strip_png_text_chunks(b"\xff\xd8jpeg") == b"\xff\xd8jpeg"
    assert comfyui_client.strip_png_text_chunks(raw[:40]) == raw[:40]


def test_download_image_honours_toggle(monkeypatch):
    raw = _png_with_prompt()

    class _Resp:
        content = raw

        def raise_for_status(self):
            pass

    monkeypatch.setattr(comfyui_client.SESSION, "get", lambda *a, **k: _Resp())
    monkeypatch.setattr(config, "PNG_STRIP_METADATA", True)
    assert b"secret prompt" not in comfyui_client.download_image("x.png")
    monkeypatch.setattr(config, "PNG_STRIP_METADATA", False)
    assert comfyui_client.download_image("x.png") == raw
