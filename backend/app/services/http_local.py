"""本機服務（ComfyUI / Ollama）共用的 HTTP session。

存在理由（2026-09-20 log 實證）：
  原本每個呼叫點都用 ``requests.get/post`` 的 module-level API。那是一次性
  Session —— 每呼叫一次就**新開一條 TCP 連線、重新讀一次系統 proxy 設定**。
  實測 char-gen 的 log，對本機服務的每一次呼叫固定耗時 ~2.0s（連只回傳幾百
  bytes 的 ``/system_stats`` 也一樣），單次生圖前置被吃掉約 20 秒：

      09:40:12.00 → 16.03  _can_coexist   2 次呼叫  4.03s
      09:40:16.03 → 18.04  _comfyui_vram  1 次呼叫  2.01s
      09:40:18.04 → 22.07  /free + 回讀   2 次呼叫  4.03s
      09:40:28.43 → 30.45  upload IPA     1 次呼叫  2.02s
      09:40:30.46 → 32.48  upload CN      1 次呼叫  2.02s
      09:40:32.48 → 34.50  coexist 判定   1 次呼叫  2.02s

  payload 大小差了三個數量級、耗時卻一模一樣 ⇒ 成本在**連線建立**，不在傳輸。

對策（兩項都只影響連線建立，請求內容一字未改 ⇒ 零行為變更）：
  1. 共用 Session + keep-alive：對同一個 host 重複使用既有 TCP 連線。
  2. ``trust_env = False``：requests 預設會讀 HTTP_PROXY/HTTPS_PROXY 環境變數，
     使用者若有 VPN／公司代理設定，連 127.0.0.1 都會被繞進 proxy —— 這是固定
     2 秒的頭號嫌犯。本機位址本來就不該走 proxy。

注意：只用於**本機**服務。remote_runner 等對外呼叫維持原本的 requests，
因為那些確實可能需要系統 proxy 與憑證設定。
"""
from __future__ import annotations

import requests
from requests.adapters import HTTPAdapter


def _build_session() -> requests.Session:
    s = requests.Session()
    # 本機呼叫一律不經系統 proxy（也順帶跳過 .netrc / REQUESTS_CA_BUNDLE 探測）
    s.trust_env = False
    # pool_maxsize 需涵蓋「status 輪詢 + 生圖前置」的並發；max_retries=0 維持
    # 原本 requests 預設的不重試行為，避免對已在採樣的 ComfyUI 重複施壓。
    adapter = HTTPAdapter(pool_connections=4, pool_maxsize=32, max_retries=0)
    s.mount("http://", adapter)
    s.mount("https://", adapter)
    return s


#: 全域共用。requests.Session 的連線池本身是 thread-safe，本專案只讀不改
#: session 狀態（headers/cookies 皆未動），可安全跨 threadpool 使用。
SESSION = _build_session()
