"""LLM 回應中的 JSON 抽取（容忍 ```json 圍欄與前後雜訊）。"""
from __future__ import annotations

import json
import re
from typing import Optional, Union

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", flags=re.MULTILINE)
_OBJECT_RE = re.compile(r"\{[\s\S]*\}")
_ARRAY_RE = re.compile(r"\[[\s\S]*\]")


def extract_json(raw: str, expect: type) -> Optional[Union[dict, list]]:
    """先整段 json.loads；失敗則抓最外層 {...} / [...] 再試。型別不符回 None。"""
    if not raw:
        return None
    cleaned = _FENCE_RE.sub("", raw.strip())
    try:
        data = json.loads(cleaned)
        return data if isinstance(data, expect) else None
    except json.JSONDecodeError:
        pass
    m = (_OBJECT_RE if expect is dict else _ARRAY_RE).search(cleaned)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
        return data if isinstance(data, expect) else None
    except json.JSONDecodeError:
        return None
