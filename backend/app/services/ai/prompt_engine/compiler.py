"""
Prompt Compiler — 中文描述 → 對應模型的最終 prompt

流程：
  1. 依 style 選擇 LLM template
  2. Ollama 翻譯生成 raw tags / 描述
  3. Sanitizer：移除 banned_tags
  4. 拼接 quality_prefix
  5. 回傳 (positive_prompt, negative_prompt)
"""
from __future__ import annotations

from app.services.ai import ollama_client
from app.services.ai.prompt_engine.styles import PromptStyle, STYLE_CONFIG


def compile(
    text: str,
    style: PromptStyle = PromptStyle.SDXL,
    model: str = ollama_client.DEFAULT_TEXT_MODEL,
) -> tuple[str, str]:
    """
    Compile Chinese text into (positive_prompt, negative_prompt) for the given style.

    Returns:
        (positive, negative) — both ready to inject into ComfyUI workflow
    """
    config = STYLE_CONFIG[style]

    # 1. LLM 翻譯
    llm_prompt = config["llm_template"].format(prompt=text)
    raw = ollama_client.generate(
        llm_prompt,
        model=model,
        options={
            "temperature": 0.3,
            "num_predict": 250,
            "stop": ["\nInput:", "\n\nInput"],  # 防止模型繼續輸出下一個 few-shot 範例
        },
    )

    # 2. 提取 LLM 實際回答（防止模型把 few-shot 範例一起輸出）
    extracted = _extract_output(raw)

    # 3. Sanitizer — 移除 banned_tags（Flux 主要靠這個拿掉 SD 語法）
    cleaned = _sanitize(extracted, config["banned_tags"])

    # 4. 拼接 quality_prefix
    prefix = config["quality_prefix"]
    positive = f"{prefix}, {cleaned}" if prefix and cleaned else (prefix or cleaned)

    # 5. Negative preset
    negative = config["negative"]

    return positive.strip(", "), negative


def _extract_output(raw: str) -> str:
    """
    如果 LLM 把 few-shot 範例一起輸出（例如包含 'Output:' 字樣），
    只取最後一個 'Output:' 之後的內容作為真正的答案。
    """
    if "Output:" in raw:
        return raw.split("Output:")[-1].strip()
    return raw.strip()


def _sanitize(prompt: str, banned: set[str]) -> str:
    """Remove banned tags from a comma-separated tag string."""
    if not banned:
        return prompt
    tags = [t.strip() for t in prompt.split(",")]
    filtered = [t for t in tags if t.lower() not in banned]
    return ", ".join(filtered)
