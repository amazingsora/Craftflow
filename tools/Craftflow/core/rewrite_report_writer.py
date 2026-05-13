from pathlib import Path
from utils.path_utils import get_output_path


class RewriteReportWriter:

    def write(self, input_file: Path, rewrites: list[tuple[int, str]]) -> Path:
        """
        寫入 rewrite 報告檔案
        :param input_file: 原始輸入檔案
        :param rewrites: [(paragraph_index, rewritten_text)]
        :return: 輸出路徑
        """

        output_path = get_output_path(input_file, "rewrite")

        with open(output_path, "w", encoding="utf-8") as f:
            f.write("# Rewrite Suggestions\n\n")

            for index, content in rewrites:
                f.write(f"## Paragraph {index}\n\n")
                f.write(content + "\n\n")

        return output_path
