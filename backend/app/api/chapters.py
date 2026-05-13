from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.chapter import Chapter
from app.schemas.chapter import ChapterCreate, ChapterUpdate, ChapterBrief, ChapterResponse

router = APIRouter(tags=["chapters"])
DbDep = Annotated[Session, Depends(get_db)]


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
    for key, value in data.model_dump(exclude_unset=True).items():
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


@router.patch("/chapters/{chapter_id}/reorder", response_model=ChapterResponse)
def reorder_chapter(chapter_id: int, order_index: int, db: DbDep):
    chapter = db.get(Chapter, chapter_id)
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")
    chapter.order_index = order_index
    db.commit()
    db.refresh(chapter)
    return chapter
