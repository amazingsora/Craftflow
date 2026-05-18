"""
Art Style API:
  GET    /api/v1/art-styles          — list all styles
  POST   /api/v1/art-styles          — create style
  GET    /api/v1/art-styles/{id}     — get style
  PUT    /api/v1/art-styles/{id}     — update style
  DELETE /api/v1/art-styles/{id}     — delete style
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.art_style import ArtStyle
from app.schemas.art_style import ArtStyleCreate, ArtStyleUpdate, ArtStyleResponse

router = APIRouter(tags=["art-styles"])
DbDep = Annotated[Session, Depends(get_db)]


@router.get("/art-styles", response_model=list[ArtStyleResponse])
def list_art_styles(db: DbDep):
    return db.query(ArtStyle).order_by(ArtStyle.created_at).all()


@router.post("/art-styles", response_model=ArtStyleResponse, status_code=status.HTTP_201_CREATED)
def create_art_style(data: ArtStyleCreate, db: DbDep):
    style = ArtStyle(
        **{k: (v if k != "loras" else [e.model_dump() for e in (v or [])])
           for k, v in data.model_dump().items()}
    )
    db.add(style)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=f"Art style name '{data.name}' already exists")
    db.refresh(style)
    return style


@router.get("/art-styles/{style_id}", response_model=ArtStyleResponse)
def get_art_style(style_id: int, db: DbDep):
    style = db.get(ArtStyle, style_id)
    if not style:
        raise HTTPException(status_code=404, detail="Art style not found")
    return style


@router.put("/art-styles/{style_id}", response_model=ArtStyleResponse)
def update_art_style(style_id: int, data: ArtStyleUpdate, db: DbDep):
    style = db.get(ArtStyle, style_id)
    if not style:
        raise HTTPException(status_code=404, detail="Art style not found")
    for field, value in data.model_dump(exclude_none=True).items():
        if field == "loras":
            setattr(style, field, [e.model_dump() for e in (value or [])])
        else:
            setattr(style, field, value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=f"Art style name '{data.name}' already exists")
    db.refresh(style)
    return style


@router.delete("/art-styles/{style_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_art_style(style_id: int, db: DbDep):
    style = db.get(ArtStyle, style_id)
    if not style:
        raise HTTPException(status_code=404, detail="Art style not found")
    db.delete(style)
    db.commit()
