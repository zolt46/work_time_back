# File: /backend/app/schemas.py
from datetime import datetime, date, time
from typing import Optional, List
from uuid import UUID  # ✅ UUID 타입 추가

from pydantic import BaseModel, Field, ConfigDict
from .models import UserRole, RequestType, RequestStatus


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    # JWT "sub" 에는 user id(UUID)가 string으로 들어가지만,
    # Pydantic이 자동으로 UUID로 파싱해 줄 수 있음
    sub: UUID
    role: UserRole


class UserBase(BaseModel):
    name: str
    identifier: Optional[str] = None
    role: UserRole = UserRole.MEMBER
    active: bool = True


class UserCreate(UserBase):
    login_id: str
    password: str = Field(min_length=8)


class UserUpdate(BaseModel):
    name: Optional[str]
    identifier: Optional[str]
    role: Optional[UserRole]
    active: Optional[bool]


class UserOut(UserBase):
    # ORM 객체에서 바로 읽어오도록 설정 (Pydantic v2)
    model_config = ConfigDict(from_attributes=True)

    # 🔧 DB에서 UUID 컬럼이므로 UUID 타입으로 맞춰줌
    id: UUID


class PasswordChange(BaseModel):
    old_password: str
    new_password: str = Field(min_length=8)


class ShiftBase(BaseModel):
    name: str
    weekday: int
    start_time: time
    end_time: time
    location: Optional[str] = None


class ShiftCreate(ShiftBase):
    pass


class ShiftOut(ShiftBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID  # 🔧 UUID


class AssignmentCreate(BaseModel):
    # 🔧 FK 전부 UUID
    user_id: UUID
    shift_id: UUID
    valid_from: date
    valid_to: Optional[date] = None


class AssignmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    shift_id: UUID
    valid_from: date
    valid_to: Optional[date]


class RequestCreate(BaseModel):
    type: RequestType
    target_date: date
    target_shift_id: UUID  # 🔧 UUID
    reason: Optional[str] = None


class RequestAction(BaseModel):
    decision: RequestStatus


class RequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    type: RequestType
    target_date: date
    target_shift_id: UUID
    reason: Optional[str]
    status: RequestStatus
    operator_id: Optional[UUID]
    decided_at: Optional[datetime]
    created_at: datetime


class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    actor_user_id: Optional[UUID]
    action_type: str
    target_user_id: Optional[UUID]
    request_id: Optional[UUID]
    details: Optional[dict]
    created_at: datetime
