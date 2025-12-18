# File: /backend/app/routers/requests.py
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import schemas, models
from ..deps import get_db
from ..core.roles import require_role, get_current_user

router = APIRouter(prefix="/requests", tags=["requests"])


@router.post("", response_model=schemas.RequestOut, status_code=status.HTTP_201_CREATED)
def submit_request(payload: schemas.RequestCreate, current=Depends(require_role(models.UserRole.MEMBER)), db: Session = Depends(get_db)):
    target_user_id = payload.user_id or current.id
    target_user = db.query(models.User).filter(models.User.id == target_user_id).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="Target user not found")
    if current.role == models.UserRole.OPERATOR and target_user.role == models.UserRole.MASTER:
        raise HTTPException(status_code=403, detail="Operators cannot submit for masters")
    if current.role == models.UserRole.MEMBER and target_user_id != current.id:
        raise HTTPException(status_code=403, detail="Members can only submit for themselves")

    req = models.ShiftRequest(
        user_id=target_user_id,
        type=payload.type,
        target_date=payload.target_date,
        target_shift_id=payload.target_shift_id,
        reason=payload.reason,
    )
    db.add(req)
    db.commit()
    db.refresh(req)
    return req


@router.get("/my", response_model=list[schemas.RequestOut])
def my_requests(current=Depends(require_role(models.UserRole.MEMBER)), db: Session = Depends(get_db)):
    return db.query(models.ShiftRequest).filter(models.ShiftRequest.user_id == current.id).all()


@router.get("/pending", response_model=list[schemas.RequestOut])
def pending_requests(db: Session = Depends(get_db), current=Depends(require_role(models.UserRole.OPERATOR))):
    return db.query(models.ShiftRequest).filter(models.ShiftRequest.status == models.RequestStatus.PENDING).all()


@router.post("/{request_id}/approve", response_model=schemas.RequestOut)
def approve_request(request_id: str, db: Session = Depends(get_db), current=Depends(require_role(models.UserRole.OPERATOR))):
    req = db.query(models.ShiftRequest).filter(models.ShiftRequest.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    req.status = models.RequestStatus.APPROVED
    req.operator_id = current.id
    req.decided_at = datetime.utcnow()
    db.commit()
    db.refresh(req)
    return req


@router.post("/{request_id}/reject", response_model=schemas.RequestOut)
def reject_request(request_id: str, db: Session = Depends(get_db), current=Depends(require_role(models.UserRole.OPERATOR))):
    req = db.query(models.ShiftRequest).filter(models.ShiftRequest.id == request_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    req.status = models.RequestStatus.REJECTED
    req.operator_id = current.id
    req.decided_at = datetime.utcnow()
    db.commit()
    db.refresh(req)
    return req
