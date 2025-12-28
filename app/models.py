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
from sqlalchemy.dialects.postgresql import UUID, JSONB
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


class NoticeType(str, enum.Enum):
    DB_MAINTENANCE = "DB_MAINTENANCE"
    SYSTEM_MAINTENANCE = "SYSTEM_MAINTENANCE"
    WORK_SPECIAL = "WORK_SPECIAL"
    GENERAL = "GENERAL"


class NoticeChannel(str, enum.Enum):
    POPUP = "POPUP"
    BANNER = "BANNER"
    POPUP_BANNER = "POPUP_BANNER"
    NONE = "NONE"
    BOARD = "BOARD"


class NoticeScope(str, enum.Enum):
    ALL = "ALL"
    ROLE = "ROLE"
    USER = "USER"


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
    cancel_reason = Column(String)
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


class Notice(Base):
    __tablename__ = "notices"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("uuid_generate_v4()"),
    )
    title = Column(String, nullable=False)
    body = Column(String, nullable=False)
    type = Column(Enum(NoticeType), nullable=False)
    channel = Column(Enum(NoticeChannel), nullable=False)
    scope = Column(Enum(NoticeScope), nullable=False, default=NoticeScope.ALL)
    target_roles = Column(JSONB)
    priority = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    start_at = Column(DateTime(timezone=True))
    end_at = Column(DateTime(timezone=True))
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
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

    creator = relationship("User")
    targets = relationship("NoticeTarget", back_populates="notice", cascade="all, delete-orphan")
    reads = relationship("NoticeRead", back_populates="notice", cascade="all, delete-orphan")


class NoticeTarget(Base):
    __tablename__ = "notice_targets"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("uuid_generate_v4()"),
    )
    notice_id = Column(UUID(as_uuid=True), ForeignKey("notices.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )

    notice = relationship("Notice", back_populates="targets")
    user = relationship("User")


class NoticeRead(Base):
    __tablename__ = "notice_reads"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("uuid_generate_v4()"),
    )
    notice_id = Column(UUID(as_uuid=True), ForeignKey("notices.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    channel = Column(Enum(NoticeChannel), nullable=False)
    read_at = Column(DateTime(timezone=True))
    dismissed_at = Column(DateTime(timezone=True))
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )

    notice = relationship("Notice", back_populates="reads")
    user = relationship("User")
