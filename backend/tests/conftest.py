"""全測試共用 fixture。

[CN-115] SYNC-007 軌 P：app.core.config 在 import 時會 load_dotenv(專案根 .env)，
使用者真實 .env 的 PERSONAL_<STYLE|NEGATIVE>_EXTRA_<家族> 會被帶進每個測試（呼叫時才讀），
導致 prompt 斷言隨本機設定漂移。這裡在每個測試前清掉這組分家族鍵；要測它的測試自行 setenv。
舊鍵 PERSONAL_STYLE_EXTRA_TAGS 是 import 時讀的模組常數，不在此處理（既有測試以 monkeypatch.setattr 控制）。
"""
import os

import pytest

from app.core.config import PERSONAL_FAMILY_KEY_PREFIXES

_LEGACY_GLOBAL_KEY = "PERSONAL_STYLE_EXTRA_TAGS"


@pytest.fixture(autouse=True)
def _isolate_personal_family_env(monkeypatch):
    for key in list(os.environ):
        if key.startswith(PERSONAL_FAMILY_KEY_PREFIXES) and key != _LEGACY_GLOBAL_KEY:
            monkeypatch.delenv(key, raising=False)


@pytest.fixture(autouse=True)
def _isolate_nsfw_guard_flag(monkeypatch):
    """[CN-118] NSFW_GUARD_ENABLED 是 import 時讀的常數；固定為預設 true，避免本機 .env 關閉 debug 時測試漂移。"""
    from app.core import config
    monkeypatch.setattr(config, "NSFW_GUARD_ENABLED", True)
