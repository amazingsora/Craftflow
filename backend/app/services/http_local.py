"""本機服務（ComfyUI / Ollama）共用 HTTP session：keep-alive 重用連線，
且 trust_env=False 不走系統 proxy（本機位址經 proxy 每次多約 2 秒）。僅限本機服務使用。"""
from __future__ import annotations

import requests
from requests.adapters import HTTPAdapter


def _build_session() -> requests.Session:
    s = requests.Session()
    # 本機呼叫一律不經系統 proxy（也順帶跳過 .netrc / REQUESTS_CA_BUNDLE 探測）
    s.trust_env = False
    # pool 涵蓋輪詢＋生圖前置的並發；不重試，避免對採樣中的 ComfyUI 重複施壓
    adapter = HTTPAdapter(pool_connections=4, pool_maxsize=32, max_retries=0)
    s.mount("http://", adapter)
    s.mount("https://", adapter)
    return s


#: 全域共用。requests.Session 的連線池本身是 thread-safe，本專案只讀不改
#: session 狀態（headers/cookies 皆未動），可安全跨 threadpool 使用。
SESSION = _build_session()
