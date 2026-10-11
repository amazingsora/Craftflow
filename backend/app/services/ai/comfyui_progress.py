"""ComfyUI WebSocket 進度監聽（best-effort）：失敗皆靜默降級；
完成與輸出以 comfyui_client.wait_for_result 的 HTTP 輪詢為準。"""
from __future__ import annotations

import asyncio
import json
import logging
import time

from app.core.config import COMFYUI_BASE

logger = logging.getLogger(__name__)


def _ws_url(client_id: str) -> str:
    base = COMFYUI_BASE.replace("https://", "wss://").replace("http://", "ws://")
    return f"{base.rstrip('/')}/ws?clientId={client_id}"


async def stream_progress(client_id, prompt_id, on_event, *, timeout: float = 600.0) -> None:
    """連 ComfyUI ws，把進度事件回報給 on_event(dict) [FD-049]"""
    try:
        import websockets  # 延後 import：未安裝即整段降級
    except Exception:
        logger.info("[comfyui-ws] websockets 未安裝，進度串流停用（不影響生成）")
        return

    url = _ws_url(client_id)
    try:
        async with websockets.connect(url, max_size=None, open_timeout=10, ping_interval=20) as ws:
            start = time.time()
            while time.time() - start < timeout:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=30)
                except asyncio.TimeoutError:
                    continue
                if isinstance(raw, (bytes, bytearray)):
                    continue  # preview 圖 frame，略過
                try:
                    msg = json.loads(raw)
                except Exception:
                    continue
                t = msg.get("type")
                d = msg.get("data") or {}
                pid = d.get("prompt_id")
                if pid and prompt_id and pid != prompt_id:
                    continue  # 別的 job 的事件
                if t == "progress":
                    v = d.get("value", 0) or 0
                    m = d.get("max", 0) or 0
                    on_event({"type": "progress", "value": v, "max": m,
                              "pct": round(v / m * 100) if m else 0})
                elif t == "executing":
                    if d.get("node") is None and pid == prompt_id:
                        on_event({"type": "done"})
                        return
                    on_event({"type": "node", "node": d.get("node")})
                elif t == "execution_error":
                    on_event({"type": "error", "message": d.get("exception_message") or "execution error"})
                    return
                elif t == "execution_interrupted":
                    on_event({"type": "error", "message": "interrupted"})
                    return
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.info("[comfyui-ws] 進度串流停用（%s）", e)
