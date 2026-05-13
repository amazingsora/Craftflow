from prompts.prompt_builder import PromptBuilder
from core.language_detector import LanguageDetector


class RewriteEngine:

    def __init__(self, provider):
        self.provider = provider

    def rewrite(self, paragraph_text, reason, mode="gentle"):

        if mode == "gentle":
            instruction = (
                "Lightly revise the paragraph to improve rhythm and clarity. "
                "Preserve the author's voice and structure. "
                "Avoid major restructuring."
            )
        else:
            instruction = (
                "Rewrite the paragraph to significantly improve rhythm, flow, and impact. "
                "You may restructure sentences and enhance stylistic expression "
                "while preserving original meaning."
            )

        prompt = f"""
    You are a rewriting engine.

    TASK:
    Rewrite the paragraph according to the instruction.

    RULES:
        - Output ONLY the rewritten paragraph.
        - No introductions.
        - No explanations.
        - No quotation marks.
        - No extra text.
        - The rewritten paragraph MUST be in the same language as the original paragraph.
    Instruction:
    {instruction}

    Reason:
    {reason}

    Paragraph:
    {paragraph_text}

    Rewritten paragraph:
    """

        result = self.provider.generate(prompt)

        return result.strip()