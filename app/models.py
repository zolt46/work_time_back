# File: /backend/app/models.py
import enum
from datetime import datetime, date, time

from sqlalchemy import (
    Column,
    String,
    Boolean,
    Enum,
    DateTime,
    Date,
    Time,
    ForeignKey,
    JSON,
    text,
    Integer,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class UserRole(str, enum.Enum):
    MASTER = "MASTER"
    OPERATOR = "OPERATOR"
    MEMBER = "MEMBER"


class RequestType(str, enum.Enum):
    ABSENCE = "ABSENCE"
    EXTRA = "EXTRA"


class RequestStatus(str, enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class User(Base):
    __tablename__ = "users"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("uuid_generate_v4()"),
    )
    name = Column(String, nullable=False)
    identifier = Column(String, unique=True)
    role = Column(Enum(UserRole), nullable=False, default=UserRole.MEMBER)
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    auth_account = relationship("AuthAccount", back_populates="user", uselist=False)

    # ★ 여기가 핵심 수정 부분
    # 여러 FK 중에서 ShiftRequest.user_id 를 사용하라고 명시
    requests = relationship(
        "ShiftRequest",
        back_populates="user",
        foreign_keys="ShiftRequest.user_id",
    )


class AuthAccount(Base):
    __tablename__ = "auth_accounts"

    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    login_id = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    last_login_at = Column(DateTime(timezone=True))

    user = relationship("User", back_populates="auth_account")


class Shift(Base):
    __tablename__ = "shifts"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("uuid_generate_v4()"),
    )
    name = Column(String, nullable=False)
    weekday = Column(Integer, nullable=False)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    location = Column(String)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    assignments = relationship("UserShift", back_populates="shift")
    requests = relationship("ShiftRequest", back_populates="target_shift")


class UserShift(Base):
    __tablename__ = "user_shifts"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("uuid_generate_v4()"),
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    shift_id = Column(
        UUID(as_uuid=True),
        ForeignKey("shifts.id", ondelete="CASCADE"),
        nullable=False,
    )
    valid_from = Column(Date, nullable=False)
    valid_to = Column(Date)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    user = relationship("User")
    shift = relationship("Shift", back_populates="assignments")


class ShiftRequest(Base):
    __tablename__ = "shift_requests"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("uuid_generate_v4()"),
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    type = Column(Enum(RequestType), nullable=False)
    target_date = Column(Date, nullable=False)
    target_shift_id = Column(
        UUID(as_uuid=True),
        ForeignKey("shifts.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_start_time = Column(Time)
    target_end_time = Column(Time)
    reason = Column(String)
    status = Column(
        Enum(RequestStatus),
        nullable=False,
        default=RequestStatus.PENDING,
    )
    operator_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
    )
    decided_at = Column(DateTime(timezone=True))
    cancelled_after_approval = Column(Boolean, nullable=False, default=False)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    # 요청 만든 유저
    user = relationship(
        "User",
        foreign_keys=[user_id],
        back_populates="requests",
    )

    # 승인/반려 처리한 운영자
    operator = relationship(
        "User",
        foreign_keys=[operator_id],
    )

    target_shift = relationship("Shift", back_populates="requests")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("uuid_generate_v4()"),
    )
    actor_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    action_type = Column(String, nullable=False)
    target_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    request_id = Column(UUID(as_uuid=True), ForeignKey("shift_requests.id"))
    details = Column(JSON)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )
