# File: /backend/app/routers/system.py
import os

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..deps import get_db
from .. import models, schemas
from ..core.roles import require_role
from ..core.security import get_password_hash

router = APIRouter(tags=["system"])


@router.get("/health")
def health_check(db: Session = Depends(get_db)):
    """간단한 DB 연결 헬스체크 엔드포인트."""
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - runtime safety
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="database_unavailable",
        ) from exc
    return {"db_status": "ok"}


def _seed_master(db: Session):
    login_id = os.getenv("MASTER_LOGIN_ID", "master")
    password = os.getenv("MASTER_PASSWORD", "Master123!")
    name = os.getenv("MASTER_NAME", "Master Admin")
    identifier = os.getenv("MASTER_IDENTIFIER", "MASTER_DEFAULT")

    master = models.User(name=name, identifier=identifier, role=models.UserRole.MASTER)
    db.add(master)
    db.flush()
    db.add(models.AuthAccount(user_id=master.id, login_id=login_id, password_hash=get_password_hash(password)))
    return master


def _delete_by_roles(db: Session, roles: list[models.UserRole]):
    users = db.query(models.User).filter(models.User.role.in_(roles)).all()
    for user in users:
        db.delete(user)


@router.post("/reset", response_model=dict)
def reset_data(payload: schemas.ResetRequest, db: Session = Depends(get_db), current=Depends(require_role(models.UserRole.OPERATOR))):
    scope = payload.scope

    if scope in (schemas.ResetScope.OPERATORS_AND_MEMBERS, schemas.ResetScope.ALL) and current.role != models.UserRole.MASTER:
        raise HTTPException(status_code=403, detail="Only masters can perform this reset")

    if scope == schemas.ResetScope.MEMBERS:
        _delete_by_roles(db, [models.UserRole.MEMBER])
        detail = "Members removed"
    elif scope == schemas.ResetScope.OPERATORS_AND_MEMBERS:
        _delete_by_roles(db, [models.UserRole.MEMBER, models.UserRole.OPERATOR])
        detail = "Operators and members removed"
    else:
        db.execute(text("TRUNCATE audit_logs, shift_requests, user_shifts, shifts, auth_accounts, users RESTART IDENTITY CASCADE"))
        _seed_master(db)
        detail = "All data cleared and master reseeded"

    db.commit()
    return {"detail": detail, "scope": scope.value}
