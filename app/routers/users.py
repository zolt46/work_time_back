# File: /backend/app/routers/users.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import schemas, models
from ..deps import get_db
from ..core.roles import require_role
from ..core.security import get_password_hash

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[schemas.UserOut])
def list_users(db: Session = Depends(get_db), current=Depends(require_role(models.UserRole.OPERATOR))):
    return db.query(models.User).all()


@router.post("", response_model=schemas.UserOut, status_code=status.HTTP_201_CREATED)
def create_user(payload: schemas.UserCreate, db: Session = Depends(get_db), current=Depends(require_role(models.UserRole.OPERATOR))):
    # Operators create members; masters can create operators too
    if current.role == models.UserRole.OPERATOR and payload.role != models.UserRole.MEMBER:
        raise HTTPException(status_code=403, detail="Operators can only create members")
    user = models.User(name=payload.name, identifier=payload.identifier, role=payload.role)
    db.add(user)
    db.flush()
    auth = models.AuthAccount(user_id=user.id, login_id=payload.login_id, password_hash=get_password_hash(payload.password))
    db.add(auth)
    db.commit()
    db.refresh(user)
    return user


@router.patch("/{user_id}", response_model=schemas.UserOut)
def update_user(user_id: str, payload: schemas.UserUpdate, db: Session = Depends(get_db), current=Depends(require_role(models.UserRole.OPERATOR))):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if current.role == models.UserRole.OPERATOR and payload.role and payload.role != user.role:
        raise HTTPException(status_code=403, detail="Operators cannot change roles")
    for field, value in payload.dict(exclude_unset=True).items():
        setattr(user, field, value)
    db.commit()
    db.refresh(user)
    return user


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(user_id: str, db: Session = Depends(get_db), current=Depends(require_role(models.UserRole.OPERATOR))):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    db.delete(user)
    db.commit()
    return None
