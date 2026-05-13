class PromptBuilder:

    @staticmethod
    def build(paragraph: str, reason: str, language: str) -> str:
        if "TOO_SHORT" in reason:

            if language == "zh":
                return f"""
        你是一名專業小說編輯。

        任務：
        這段文字過於簡短。
        請在保持原意的前提下，
        適度增加 1~2 句補充內容，使節奏更自然。

        限制：
        - 必須使用中文
        - 不要誇張擴寫
        - 不要新增劇情
        - 不要解釋
        - 只輸出改寫後段落

        原文：
        {paragraph}

        改寫：
        """
            else:
                return f"""
        You are a professional fiction editor.

        Task:
        This paragraph is too short.
        Add 1-2 sentences to improve pacing while preserving meaning.

        Constraints:
        - Use English only
        - Do not exaggerate
        - Do not add new plot elements
        - Output only the rewritten paragraph

        Original:
        {paragraph}

        Rewrite:
        """


        elif "TOO_LONG" in reason:
            return f"""
你是一名專業小說編輯。

任務：
這段文字過長，請壓縮冗語，
必要時拆分句子，使節奏更流暢。

規則：
- 必須使用原文語言
- 不要解釋
- 不要評論
- 只輸出改寫後段落

原文：
{paragraph}

改寫：
"""

        elif "Consecutive long" in reason:
            return f"""
你是一名專業小說編輯。

任務：
連續出現長段落，請調整節奏變化，
使段落更有呼吸感。

規則：
- 必須使用原文語言
- 不要解釋
- 不要評論
- 只輸出改寫後段落

原文：
{paragraph}

改寫：
"""

        else:
            return f"""
你是一名專業小說編輯。
請改善以下段落節奏。

原文：
{paragraph}

改寫：
"""
