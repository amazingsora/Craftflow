from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.volume import Volume
from app.models.chapter import Chapter
from app.schemas.volume import VolumeCreate, VolumeUpdate, VolumeResponse, ReorderItem
from app.schemas.chapter import ChapterCreate, ChapterResponse

router = APIRouter(tags=["volumes"])
DbDep = Annotated[Session, Depends(get_db)]


# ── Volume CRUD ────────────────────────────────────────────────────────────────

@router.get("/projects/{project_id}/volumes", response_model=list[VolumeResponse])
def list_volumes(project_id: int, db: DbDep):
    return (
        db.query(Volume)
        .filter(Volume.project_id == project_id)
        .order_by(Volume.order_index)
        .all()
    )


@router.post(
    "/projects/{project_id}/volumes",
    response_model=VolumeResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_volume(project_id: int, data: VolumeCreate, db: DbDep):
    if data.order_index is None:
        max_idx = (
            db.query(func.max(Volume.order_index))
            .filter(Volume.project_id == project_id)
            .scalar()
        )
        order_index = (max_idx or 0) + 1
    else:
        order_index = data.order_index

    volume = Volume(
        project_id=project_id,
        order_index=order_index,
        subtitle=data.subtitle,
    )
    db.add(volume)
    db.commit()
    db.refresh(volume)
    return volume


@router.put("/volumes/{volume_id}", response_model=VolumeResponse)
def update_volume(volume_id: int, data: VolumeUpdate, db: DbDep):
    volume = db.get(Volume, volume_id)
    if not volume:
        raise HTTPException(status_code=404, detail="Volume not found")
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(volume, key, value)
    db.commit()
    db.refresh(volume)
    return volume


@router.delete("/volumes/{volume_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_volume(volume_id: int, db: DbDep):
    volume = db.get(Volume, volume_id)
    if not volume:
        raise HTTPException(status_code=404, detail="Volume not found")
    db.delete(volume)
    db.commit()


# ── Reorder ────────────────────────────────────────────────────────────────────

@router.patch("/projects/{project_id}/volumes/reorder")
def reorder_volumes(project_id: int, items: list[ReorderItem], db: DbDep):
    for item in items:
        vol = db.get(Volume, item.id)
        if vol and vol.project_id == project_id:
            vol.order_index = item.order_index
    db.commit()
    return {"ok": True}


@router.patch("/volumes/{volume_id}/chapters/reorder")
def reorder_chapters(volume_id: int, items: list[ReorderItem], db: DbDep):
    for item in items:
        ch = db.get(Chapter, item.id)
        if ch and ch.volume_id == volume_id:
            ch.order_index = item.order_index
    db.commit()
    return {"ok": True}


# ── Chapters under a volume ────────────────────────────────────────────────────

@router.post(
    "/volumes/{volume_id}/chapters",
    response_model=ChapterResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_chapter_in_volume(volume_id: int, data: ChapterCreate, db: DbDep):
    volume = db.get(Volume, volume_id)
    if not volume:
        raise HTTPException(status_code=404, detail="Volume not found")

    if data.order_index is None:
        max_idx = (
            db.query(func.max(Chapter.order_index))
            .filter(Chapter.volume_id == volume_id)
            .scalar()
        )
        order_index = (max_idx or 0) + 1
    else:
        order_index = data.order_index

    chapter = Chapter(
        project_id=volume.project_id,
        volume_id=volume_id,
        order_index=order_index,
        title=data.title,
        content=data.content or "",
    )
    db.add(chapter)
    db.commit()
    db.refresh(chapter)
    return chapter
