from pathlib import Path


def get_output_path(input_path: str, report_type: str) -> Path:
    """
    根據輸入檔名與報告類型產生對應輸出路徑。

    :param input_path: 原始輸入檔案路徑
    :param report_type: "rhythm", "rewrite", etc.
    :return: Path object
    """

    input_path = Path(input_path)
    base_name = input_path.stem  # english_test

    output_dir = Path("analysis")
    output_dir.mkdir(exist_ok=True)

    return output_dir / f"{base_name}_{report_type}.md"
