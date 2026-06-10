"""小說匯出 API（P2）。"""
from typing import Annotated, Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services import export_service

router = APIRouter(tags=["export"])
DbDep = Annotated[Session, Depends(get_db)]


def _attachment_headers(filename: str) -> dict:
    """RFC 5987：中文檔名需 filename* 編碼，附 ASCII fallback。"""
    return {
        "Content-Disposition":
            f"attachment; filename=\"export\"; filename*=UTF-8''{quote(filename)}"
    }


@router.get("/projects/{project_id}/export/markdown", summary="小說匯出（Markdown）")
def export_markdown(project_id: int, db: DbDep, format: Literal["zip", "md"] = "zip"):
    """
    format=zip（預設）→ {書名}.md + images/ 打包下載（可攜帶完整書稿）
    format=md         → 純 Markdown 文字（插圖仍以 images/ 相對路徑引用）
    """
    if format == "md":
        result = export_service.build_markdown(db, project_id)
        if result is None:
            raise HTTPException(status_code=404, detail="Project not found")
        markdown, _ = result
        return Response(content=markdown, media_type="text/markdown; charset=utf-8")

    result = export_service.export_zip(db, project_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Project not found")
    zip_bytes, filename = result
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers=_attachment_headers(filename),
    )
