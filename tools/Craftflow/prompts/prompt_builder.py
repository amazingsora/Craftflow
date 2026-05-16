class PromptBuilder:

    @staticmethod
    def build(paragraph: str, reason: str, language: str) -> str:
        if "TOO_SHORT" in reason:
            if language == "zh":
                return f"""[TASK]
你是一名專業小說編輯。這段文字過於簡短，缺乏沉浸感。請在不改變情節的前提下，改善其節奏。

[CONSTRAINTS]
1. 不變性：保留所有核心動作與劇情點。嚴禁新增角色、對話或新事件。
2. 擴充方式：透過增加感官細節（視覺、聽覺、觸覺）或角色心理活動來增加沉浸感。
3. 長度約束：改寫後的長度應約為原文的 1.2 至 1.8 倍。
4. 語言：必須使用繁體中文。
5. 格式：不要解釋或評論，只輸出改寫後的段落。

[ORIGINAL]
{paragraph}

[REWRITE]
"""
            else:
                return f"""[TASK]
You are a professional fiction editor. This paragraph is too short and lacks immersion. Improve its pacing without changing the plot.

[CONSTRAINTS]
1. Invariants: Keep all core actions and plot points. Do NOT add new characters or events.
2. Pacing: Add sensory details (sight, sound, touch) or internal monologue to increase immersion.
3. Length: The rewritten version should be approximately 1.2x to 1.8x the original length.
4. Output: Return ONLY the rewritten paragraph. No explanations.

[ORIGINAL]
{paragraph}

[REWRITE]
"""

        elif "TOO_LONG" in reason:
            return f"""[TASK]
你是一名專業小說編輯。這段文字過長且冗餘，請進行壓縮與精簡，使節奏更流暢。

[CONSTRAINTS]
1. 核心保留：保留所有關鍵劇情與角色語氣。
2. 精簡方式：刪除贅字、簡化複雜長句，必要時拆分句子。
3. 語言：必須使用原文語言。
4. 格式：不要解釋，只輸出改寫後的段落。

[ORIGINAL]
{paragraph}

[REWRITE]
"""

        elif "Consecutive long" in reason:
            return f"""[TASK]
你是一名專業小說編輯。連續出現長段落會導致閱讀疲勞，請調整本段節奏，使其具備「呼吸感」。

[CONSTRAINTS]
1. 節奏變化：通過交錯使用長短句來創造節奏感。
2. 核心保留：不要刪除或改變重要的情節資訊。
3. 語言：必須使用原文語言。
4. 格式：不要解釋，只輸出改寫後的段落。

[ORIGINAL]
{paragraph}

[REWRITE]
"""

        else:
            return f"""[TASK]
你是一名專業小說編輯。請優化以下段落的文字質感與敘事節奏。

[CONSTRAINTS]
1. 忠於原文：保留原有的敘事視角與角色性格。
2. 語言：必須使用繁體中文。
3. 格式：只輸出改寫後的結果。

[ORIGINAL]
{paragraph}

[REWRITE]
"""
