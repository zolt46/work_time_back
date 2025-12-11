# File: /backend/app/routers/auth.py
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from .. import schemas, models
from ..deps import get_db
from ..core import security, roles
from ..config import get_settings

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()


@router.post("/login", response_model=schemas.Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(models.User).join(models.AuthAccount).filter(models.AuthAccount.login_id == form_data.username).first()
    if not user or not user.auth_account:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Incorrect login credentials")
    if not security.verify_password(form_data.password, user.auth_account.password_hash):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Incorrect login credentials")
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    token = security.create_access_token({"sub": str(user.id), "role": user.role.value}, access_token_expires)
    return {"access_token": token, "token_type": "bearer"}


@router.get("/me", response_model=schemas.UserOut)
def me(current_user: models.User = Depends(roles.get_current_user)):
    return current_user


@router.patch("/password")
def change_password(payload: schemas.PasswordChange, db: Session = Depends(get_db), current_user: models.User = Depends(roles.get_current_user)):
    account = current_user.auth_account
    if not account or not security.verify_password(payload.old_password, account.password_hash):
        raise HTTPException(status_code=400, detail="Invalid current password")
    account.password_hash = security.get_password_hash(payload.new_password)
    db.add(account)
    db.commit()
    return {"detail": "Password updated"}
