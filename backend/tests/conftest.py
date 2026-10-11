"""全測試共用 fixture。

[CN-115] app.core.config 在 import 時會 load_dotenv(專案根 .env)，使用者真實 .env 的
PERSONAL_NEGATIVE_EXTRA_<家族> 會被帶進每個測試（呼叫時才讀），導致 prompt 斷言隨本機設定漂移。
這裡在每個測試前清掉這組分家族鍵；要測它的測試自行 setenv。
"""
import os

import pytest

from app.core.config import PERSONAL_FAMILY_KEY_PREFIXES


@pytest.fixture(autouse=True)
def _isolate_personal_family_env(monkeypatch):
    for key in list(os.environ):
        if key.startswith(PERSONAL_FAMILY_KEY_PREFIXES):
            monkeypatch.delenv(key, raising=False)


@pytest.fixture(autouse=True)
def _isolate_nsfw_guard_flag(monkeypatch):
    """[CN-118] NSFW_GUARD_ENABLED 是 import 時讀的常數；固定為預設 true，避免本機 .env 關閉 debug 時測試漂移。"""
    from app.core import config
    monkeypatch.setattr(config, "NSFW_GUARD_ENABLED", True)


@pytest.fixture(autouse=True)
def _isolate_gpu_tier(monkeypatch):
    """[CN-133] GPU 分級與 hires 開關依本機顯卡／.env 而變；固定為 16g、hires 關（＝現行行為）。"""
    from app.core import config
    monkeypatch.setattr(config, "GPU_TIER", "16g")
    monkeypatch.setattr(config, "HIRES_ENABLED", False)
