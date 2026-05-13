import re


class LanguageDetector:

    @staticmethod
    def detect(text: str) -> str:
        """
        簡單語言偵測：
        若 CJK 字元比例 > 20% → zh
        否則 → en
        """

        if not text:
            return "en"

        total_chars = len(text)

        # CJK Unicode range
        cjk_chars = re.findall(r'[\u4e00-\u9fff]', text)

        ratio = len(cjk_chars) / total_chars

        if ratio > 0.2:
            return "zh"
        else:
            return "en"
