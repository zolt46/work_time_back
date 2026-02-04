# File: /backend/app/deps.py
from typing import Generator
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from .config import get_settings

settings = get_settings()
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_recycle=300,
    pool_size=1,
    max_overflow=2,
    connect_args={"connect_timeout": 5},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

_request_status_enum_checked = False


def _ensure_request_status_enum(db: Session) -> None:
    """Ensure the request_status enum is aligned with application constants."""
    global _request_status_enum_checked
    if _request_status_enum_checked:
        return
    db.execute(
        text(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'request_status') THEN
                    CREATE TYPE request_status AS ENUM ('PENDING', 'APPROVED', 'REJECTED', 'CANCELLED');
                ELSIF NOT EXISTS (
                    SELECT 1
                    FROM pg_type t
                    JOIN pg_enum e ON t.oid = e.enumtypid
                    WHERE t.typname = 'request_status'
                      AND e.enumlabel = 'CANCELLED'
                ) THEN
                    ALTER TYPE request_status ADD VALUE IF NOT EXISTS 'CANCELLED';
                END IF;
            END$$;
            """
        )
    )
    db.commit()
    _request_status_enum_checked = True


def initialize_database() -> None:
    """Run startup schema checks that should not execute on every request."""
    db = SessionLocal()
    try:
        _ensure_request_status_enum(db)
        db.execute(
            text(
                """
                DO $$
                BEGIN
                    ALTER TABLE IF EXISTS shift_requests
                        ADD COLUMN IF NOT EXISTS target_start_time TIME,
                        ADD COLUMN IF NOT EXISTS target_end_time TIME,
                        ADD COLUMN IF NOT EXISTS cancelled_after_approval BOOLEAN NOT NULL DEFAULT FALSE,
                        ADD COLUMN IF NOT EXISTS cancel_reason TEXT;
                    ALTER TABLE IF EXISTS visitor_daily_counts
                        ADD COLUMN IF NOT EXISTS baseline_total INTEGER,
                        ADD COLUMN IF NOT EXISTS daily_override INTEGER;
                END$$;
                """
            )
        )
        db.commit()
    finally:
        db.close()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
