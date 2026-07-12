"""
Golden regression 測試（P2，2026-07-02 規劃）。

跑 tests/golden/cases.py 裡的每個案例，mock ollama_client.generate() 回傳固定
raw 文字，驗證 compiler.compile() 的輸出與 tests/golden/snapshots.json 一致。
任何 prompt / sanitizer / anchor 邏輯改動，只要影響到這些代表性輸入的輸出，
這裡就會紅——不必等實際生圖才發現壞掉。

若改動是預期內（例如刻意調整 sanitizer 規則），先跑：
    cd backend && python -m tests.golden.run_diff --update
確認 diff 合理後再讓這裡通過。

執行：cd backend && pytest tests/test_golden_regression.py
"""
import pytest
from unittest.mock import patch

from app.services.ai import ollama_client
from app.services.ai.prompt_engine import compiler

from tests.golden.cases import CASES
from tests.golden.run_diff import _load_snapshots


SNAPSHOTS = _load_snapshots()


@pytest.mark.parametrize("case", CASES, ids=[c.name for c in CASES])
def test_golden_case_matches_snapshot(case):
    assert case.name in SNAPSHOTS, (
        f"'{case.name}' 尚無 snapshot，先在 backend/ 下執行 "
        f"`python -m tests.golden.run_diff --update` 產生"
    )
    with patch.object(ollama_client, "generate", return_value=case.mock_raw):
        positive, negative = compiler.compile(
            case.text,
            style=case.style,
            anchor_text=case.anchor_text,
            quality_prefix_override=case.quality_prefix_override,
            negative_override=case.negative_override,
        )
    expected = SNAPSHOTS[case.name]
    assert positive == expected["positive"], f"[{case.name}] positive 與 snapshot 不符（{case.note}）"
    assert negative == expected["negative"], f"[{case.name}] negative 與 snapshot 不符（{case.note}）"
