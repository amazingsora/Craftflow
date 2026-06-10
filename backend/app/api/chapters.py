from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import CHAPTER_REVISIONS_KEEP
from app.core.database import get_db
from app.models.chapter import Chapter
from app.models.chapter_revision import ChapterRevision
from app.schemas.chapter import (
    ChapterCreate, ChapterUpdate, ChapterBrief, ChapterResponse,
    ChapterRevisionBrief, ChapterRevisionResponse,
)

router = APIRouter(tags=["chapters"])
DbDep = Annotated[Session, Depends(get_db)]


def _snapshot_chapter(db: Session, chapter: Chapter) -> None:
    """快照章節當前內容（不 commit，由呼叫端統一 commit）。

    空內容不快照；每章保留最近 CHAPTER_REVISIONS_KEEP 版，舊的淘汰。
    """
    if not (chapter.content or "").strip():
        return
    db.add(ChapterRevision(
        chapter_id=chapter.id,
        title=chapter.title,
        content=chapter.content,
    ))
    db.flush()  # 取得新 revision id，確保下面的淘汰排序正確
    stale = (
        db.query(ChapterRevision)
        .filter(ChapterRevision.chapter_id == chapter.id)
        .order_by(ChapterRevision.id.desc())
        .offset(CHAPTER_REVISIONS_KEEP)
        .all()
    )
    for rev in stale:
        db.delete(rev)


@router.get("/projects/{project_id}/chapters", response_model=list[ChapterBrief])
def list_chapters(project_id: int, db: DbDep):
    return (
        db.query(Chapter)
        .filter(Chapter.project_id == project_id)
        .order_by(Chapter.order_index)
        .all()
    )


@router.post(
    "/projects/{project_id}/chapters",
    response_model=ChapterResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_chapter(project_id: int, data: ChapterCreate, db: DbDep):
    if data.order_index is None:
        max_idx = (
            db.query(func.max(Chapter.order_index))
            .filter(Chapter.project_id == project_id)
            .scalar()
        ) or 0
        order_index = max_idx + 1
    else:
        order_index = data.order_index

    chapter = Chapter(
        project_id=project_id,
        order_index=order_index,
        title=data.title,
        content=data.content or "",
    )
    db.add(chapter)
    db.commit()
    db.refresh(chapter)
    return chapter


@router.get("/chapters/{chapter_id}", response_model=ChapterResponse)
def get_chapter(chapter_id: int, db: DbDep):
    chapter = db.get(Chapter, chapter_id)
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")
    return chapter


@router.put("/chapters/{chapter_id}", response_model=ChapterResponse)
def update_chapter(chapter_id: int, data: ChapterUpdate, db: DbDep):
    chapter = db.get(Chapter, chapter_id)
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")
    payload = data.model_dump(exclude_unset=True)
    # 內容有變才快照舊版（覆寫前），標題/排序變更不觸發
    if "content" in payload and payload["content"] != chapter.content:
        _snapshot_chapter(db, chapter)
    for key, value in payload.items():
        setattr(chapter, key, value)
    db.commit()
    db.refresh(chapter)
    return chapter


@router.delete("/chapters/{chapter_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_chapter(chapter_id: int, db: DbDep):
    chapter = db.get(Chapter, chapter_id)
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")
    db.delete(chapter)
    db.commit()


# ── 版本歷史 ──────────────────────────────────────────────────────────────────

@router.get("/chapters/{chapter_id}/revisions", response_model=list[ChapterRevisionBrief])
def list_revisions(chapter_id: int, db: DbDep):
    if not db.get(Chapter, chapter_id):
        raise HTTPException(status_code=404, detail="Chapter not found")
    return (
        db.query(ChapterRevision)
        .filter(ChapterRevision.chapter_id == chapter_id)
        .order_by(ChapterRevision.id.desc())
        .all()
    )


@router.get("/chapters/{chapter_id}/revisions/{revision_id}", response_model=ChapterRevisionResponse)
def get_revision(chapter_id: int, revision_id: int, db: DbDep):
    rev = db.get(ChapterRevision, revision_id)
    if not rev or rev.chapter_id != chapter_id:
        raise HTTPException(status_code=404, detail="Revision not found")
    return rev


@router.post("/chapters/{chapter_id}/revisions/{revision_id}/restore", response_model=ChapterResponse)
def restore_revision(chapter_id: int, revision_id: int, db: DbDep):
    """還原至指定版本。還原前先快照當前內容，確保此操作本身可回復。"""
    chapter = db.get(Chapter, chapter_id)
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")
    rev = db.get(ChapterRevision, revision_id)
    if not rev or rev.chapter_id != chapter_id:
        raise HTTPException(status_code=404, detail="Revision not found")
    if rev.content != chapter.content:
        _snapshot_chapter(db, chapter)
        chapter.content = rev.content
    db.commit()
    db.refresh(chapter)
    return chapter


@router.patch("/chapters/{chapter_id}/reorder", response_model=ChapterResponse)
def reorder_chapter(chapter_id: int, order_index: int, db: DbDep):
    chapter = db.get(Chapter, chapter_id)
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")
    chapter.order_index = order_index
    db.commit()
    db.refresh(chapter)
    return chapter
