# File: /backend/app/schemas.py
from datetime import datetime, date, time
from typing import Optional, List
from pydantic import BaseModel, Field, ConfigDict
from .models import UserRole, RequestType, RequestStatus

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

class TokenData(BaseModel):
    sub: str
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
    model_config = ConfigDict(from_attributes=True)

    id: str

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
    
    id: str

class AssignmentCreate(BaseModel):
    user_id: str
    shift_id: str
    valid_from: date
    valid_to: Optional[date] = None

class AssignmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    shift_id: str
    valid_from: date
    valid_to: Optional[date]

class RequestCreate(BaseModel):
    type: RequestType
    target_date: date
    target_shift_id: str
    reason: Optional[str] = None

class RequestAction(BaseModel):
    decision: RequestStatus

class RequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    type: RequestType
    target_date: date
    target_shift_id: str
    reason: Optional[str]
    status: RequestStatus
    operator_id: Optional[str]
    decided_at: Optional[datetime]
    created_at: datetime

class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    actor_user_id: Optional[str]
    action_type: str
    target_user_id: Optional[str]
    request_id: Optional[str]
    details: Optional[dict]
    created_at: datetime
