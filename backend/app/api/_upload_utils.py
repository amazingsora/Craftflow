"""api 層共用的上傳檔存取 helper。

2026-09-24 重複碼整合：characters（portrait／概念圖／AI 圖，主角色＋變體）與 factions（縮圖）
原本各自展開「驗型別 → mkdir → uuid 檔名 → copyfileobj」與「檔案不在就 404 → FileResponse」，
七處逐字相同。集中於此，端點只保留各自的資料模型操作。
"""
from __future__ import annotations

import shutil
import uuid
from pathlib import Path
from typing import Optional

from fastapi import HTTPException, UploadFile
from fastapi.responses import FileResponse

ALLOWED_IMAGE_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})
_DEFAULT_SUFFIX = ".png"


def ensure_image_type(file: UploadFile) -> None:
    """不支援的圖片型別 → 400（訊息沿用原端點）。"""
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported type: {file.content_type}")


def save_upload(file: UploadFile, directory: Path, prefix: str) -> str:
    """存成 directory/<prefix><uuid hex><原副檔名>，回傳檔名（不含目錄）。"""
    directory.mkdir(parents=True, exist_ok=True)
    suffix = Path(file.filename).suffix if file.filename else _DEFAULT_SUFFIX
    filename = f"{prefix}{uuid.uuid4().hex}{suffix}"
    with (directory / filename).open("wb") as f:
        shutil.copyfileobj(file.file, f)
    return filename


def remove_file_if_exists(directory: Path, filename: Optional[str]) -> None:
    """單張圖替換時移除舊檔；filename 為空則不動作。"""
    if filename:
        (directory / filename).unlink(missing_ok=True)


def file_response_or_404(path: Path, missing_detail: str) -> FileResponse:
    if not path.exists():
        raise HTTPException(status_code=404, detail=missing_detail)
    return FileResponse(str(path))
