import shutil
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.config import UPLOAD_DIR
from app.core.database import get_db
from app.models.illustration import Illustration
from app.schemas.illustration import IllustrationUpdate, IllustrationResponse

router = APIRouter(tags=["illustrations"])
DbDep = Annotated[Session, Depends(get_db)]

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}


@router.get("/projects/{project_id}/illustrations", response_model=list[IllustrationResponse])
def list_illustrations(project_id: int, db: DbDep):
    return (
        db.query(Illustration)
        .filter(Illustration.project_id == project_id)
        .order_by(Illustration.created_at)
        .all()
    )


@router.post(
    "/projects/{project_id}/illustrations",
    response_model=IllustrationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_illustration(
    project_id: int,
    file: Annotated[UploadFile, File(...)],
    db: DbDep,
):
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {file.content_type}")

    project_dir = UPLOAD_DIR / str(project_id)
    project_dir.mkdir(parents=True, exist_ok=True)

    suffix = Path(file.filename).suffix if file.filename else ".png"
    filename = f"{uuid.uuid4().hex}{suffix}"
    dest = project_dir / filename

    with dest.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    relative_path = str(Path(str(project_id)) / filename)
    illustration = Illustration(project_id=project_id, file_path=relative_path)
    db.add(illustration)
    db.commit()
    db.refresh(illustration)
    return illustration


@router.get("/illustrations/{illustration_id}", response_model=IllustrationResponse)
def get_illustration(illustration_id: int, db: DbDep):
    illustration = db.get(Illustration, illustration_id)
    if not illustration:
        raise HTTPException(status_code=404, detail="Illustration not found")
    return illustration


@router.put("/illustrations/{illustration_id}", response_model=IllustrationResponse)
def update_illustration(illustration_id: int, data: IllustrationUpdate, db: DbDep):
    illustration = db.get(Illustration, illustration_id)
    if not illustration:
        raise HTTPException(status_code=404, detail="Illustration not found")
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(illustration, key, value)
    db.commit()
    db.refresh(illustration)
    return illustration


@router.delete("/illustrations/{illustration_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_illustration(illustration_id: int, db: DbDep):
    illustration = db.get(Illustration, illustration_id)
    if not illustration:
        raise HTTPException(status_code=404, detail="Illustration not found")
    file_path = UPLOAD_DIR / illustration.file_path
    if file_path.exists():
        file_path.unlink()
    db.delete(illustration)
    db.commit()


@router.get("/illustrations/{illustration_id}/file")
def serve_illustration(illustration_id: int, db: DbDep):
    illustration = db.get(Illustration, illustration_id)
    if not illustration:
        raise HTTPException(status_code=404, detail="Illustration not found")
    file_path = UPLOAD_DIR / illustration.file_path
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")
    return FileResponse(str(file_path))
