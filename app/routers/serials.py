# File: /backend/app/routers/serials.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import models, schemas
from ..deps import get_db
from ..core.roles import get_current_user, require_role

router = APIRouter(prefix="/serials", tags=["serials"])


def _get_publication(db: Session, publication_id) -> models.SerialPublication:
    publication = (
        db.query(models.SerialPublication)
        .filter(models.SerialPublication.id == publication_id)
        .first()
    )
    if not publication:
        raise HTTPException(status_code=404, detail="연속 간행물을 찾을 수 없습니다.")
    return publication


@router.get("", response_model=list[schemas.SerialPublicationOut])
def list_publications(
    q: str | None = None,
    issn: str | None = None,
    shelf_section: str | None = None,
    acquisition_type: models.SerialAcquisitionType | None = None,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    query = db.query(models.SerialPublication)
    if q:
        keyword = f"%{q.strip()}%"
        query = query.filter(models.SerialPublication.title.ilike(keyword))
    if issn:
        keyword = f"%{issn.strip()}%"
        query = query.filter(models.SerialPublication.issn.ilike(keyword))
    if shelf_section:
        keyword = f"%{shelf_section.strip()}%"
        query = query.filter(models.SerialPublication.shelf_section.ilike(keyword))
    if acquisition_type:
        query = query.filter(models.SerialPublication.acquisition_type == acquisition_type)
    return query.order_by(models.SerialPublication.title.asc()).all()


@router.get("/{publication_id}", response_model=schemas.SerialPublicationOut)
def get_publication(
    publication_id,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    return _get_publication(db, publication_id)


@router.post("", response_model=schemas.SerialPublicationOut, status_code=status.HTTP_201_CREATED)
def create_publication(
    payload: schemas.SerialPublicationCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_role(models.UserRole.OPERATOR)),
):
    publication = models.SerialPublication(
        title=payload.title,
        issn=payload.issn,
        acquisition_type=payload.acquisition_type,
        shelf_section=payload.shelf_section,
        shelf_row=payload.shelf_row,
        shelf_column=payload.shelf_column,
        shelf_note=payload.shelf_note,
        remark=payload.remark,
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.add(publication)
    db.commit()
    db.refresh(publication)
    return publication


@router.put("/{publication_id}", response_model=schemas.SerialPublicationOut)
def update_publication(
    publication_id,
    payload: schemas.SerialPublicationUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(require_role(models.UserRole.OPERATOR)),
):
    publication = _get_publication(db, publication_id)
    if payload.title is not None:
        publication.title = payload.title
    if payload.issn is not None:
        publication.issn = payload.issn
    if payload.acquisition_type is not None:
        publication.acquisition_type = payload.acquisition_type
    if payload.shelf_section is not None:
        publication.shelf_section = payload.shelf_section
    if payload.shelf_row is not None:
        publication.shelf_row = payload.shelf_row
    if payload.shelf_column is not None:
        publication.shelf_column = payload.shelf_column
    if payload.shelf_note is not None:
        publication.shelf_note = payload.shelf_note
    if payload.remark is not None:
        publication.remark = payload.remark
    publication.updated_by = current_user.id
    db.commit()
    db.refresh(publication)
    return publication


@router.delete("/{publication_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_publication(
    publication_id,
    db: Session = Depends(get_db),
    current_user=Depends(require_role(models.UserRole.OPERATOR)),
):
    publication = _get_publication(db, publication_id)
    db.delete(publication)
    db.commit()
    return None
